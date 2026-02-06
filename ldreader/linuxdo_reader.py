#!/usr/bin/env python3
"""Linux.do auto reader (Discourse timings API).

WARNING: Using automation may violate site rules and risk account restrictions.
"""
from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests


@dataclass
class Config:
    base_delay: int = 2500
    random_delay_range: int = 800
    min_req_size: int = 8
    max_req_size: int = 20
    min_read_time: int = 800
    max_read_time: int = 3000
    start_from_current: bool = False
    retry_count: int = 3
    topic_delay: int = 1500
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


CSRF_REGEX = re.compile(r'name="csrf-token" content="([^"]+)"')


class LinuxdoReaderError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Linux.do auto reader using Discourse timings API."
    )
    parser.add_argument(
        "--topic-url",
        help="Topic URL, e.g. https://linux.do/t/slug/123 (optional if using --all-new).",
    )
    parser.add_argument(
        "--base-url",
        default="https://linux.do",
        help="Base URL of the Discourse site (default: https://linux.do).",
    )
    auth_group = parser.add_mutually_exclusive_group(required=False)
    auth_group.add_argument(
        "--cookie",
        help="Full Cookie header value from your logged-in browser session.",
    )
    auth_group.add_argument(
        "--username",
        help="Account username or email for login.",
    )
    parser.add_argument("--password", help="Account password for login.")
    parser.add_argument(
        "--password-env",
        default="",
        help="Read password from environment variable (e.g. LINUXDO_PASSWORD).",
    )
    parser.add_argument(
        "--all-new",
        action="store_true",
        help="Fetch /new topics and auto-read them.",
    )
    parser.add_argument(
        "--max-topics",
        type=int,
        default=30,
        help="Max topics to read when using --all-new.",
    )
    parser.add_argument(
        "--new-pages",
        type=int,
        default=1,
        help="How many /new pages to fetch (page=N).",
    )
    parser.add_argument("--base-delay", type=int, default=Config.base_delay)
    parser.add_argument("--random-delay-range", type=int, default=Config.random_delay_range)
    parser.add_argument("--min-req-size", type=int, default=Config.min_req_size)
    parser.add_argument("--max-req-size", type=int, default=Config.max_req_size)
    parser.add_argument("--min-read-time", type=int, default=Config.min_read_time)
    parser.add_argument("--max-read-time", type=int, default=Config.max_read_time)
    parser.add_argument("--start-from-current", action="store_true")
    parser.add_argument("--retry-count", type=int, default=Config.retry_count)
    parser.add_argument(
        "--topic-delay",
        type=int,
        default=Config.topic_delay,
        help="Delay between topics in milliseconds.",
    )
    parser.add_argument("--user-agent", default=Config.user_agent)
    parser.add_argument("--dry-run", action="store_true", help="Print batches without sending requests")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> Config:
    return Config(
        base_delay=args.base_delay,
        random_delay_range=args.random_delay_range,
        min_req_size=args.min_req_size,
        max_req_size=args.max_req_size,
        min_read_time=args.min_read_time,
        max_read_time=args.max_read_time,
        start_from_current=args.start_from_current,
        retry_count=args.retry_count,
        topic_delay=args.topic_delay,
        user_agent=args.user_agent,
    )


def normalize_topic_url(topic_url: str) -> str:
    parsed = urlparse(topic_url)
    if not parsed.scheme or not parsed.netloc:
        raise LinuxdoReaderError("Invalid topic URL.")
    return topic_url.split("?")[0].rstrip("/")


def init_session(cookie: Optional[str], user_agent: str) -> requests.Session:
    session = requests.Session()
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if cookie:
        headers["Cookie"] = cookie
    session.headers.update(headers)
    return session


def fetch_csrf_token(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=20)
    if not response.ok:
        raise LinuxdoReaderError(f"Failed to load page: HTTP {response.status_code}")
    match = CSRF_REGEX.search(response.text)
    if not match:
        raise LinuxdoReaderError("CSRF token not found. Are you logged in?")
    return match.group(1)


def fetch_csrf_token_api(session: requests.Session, base_url: str) -> str:
    response = session.get(urljoin(base_url, "/session/csrf.json"), timeout=20)
    if response.ok:
        payload = response.json()
        token = payload.get("csrf")
        if token:
            return token
    return fetch_csrf_token(session, urljoin(base_url, "/login"))


def login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    csrf_token = fetch_csrf_token_api(session, base_url)
    response = session.post(
        urljoin(base_url, "/session"),
        data={"login": username, "password": password},
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-CSRF-Token": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        },
        timeout=20,
    )
    if not response.ok:
        raise LinuxdoReaderError(f"Login failed: HTTP {response.status_code}")
    payload = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else {}
    if payload.get("error") or payload.get("errors"):
        raise LinuxdoReaderError(f"Login failed: {payload.get('error') or payload.get('errors')}")


def fetch_topic_json(session: requests.Session, topic_url: str) -> Dict:
    json_url = f"{topic_url}.json"
    response = session.get(json_url, timeout=20)
    if not response.ok:
        raise LinuxdoReaderError(f"Failed to load topic JSON: HTTP {response.status_code}")
    return response.json()


def fetch_new_topics(session: requests.Session, base_url: str, pages: int) -> List[Dict]:
    topics: List[Dict] = []
    for page in range(pages):
        url = urljoin(base_url, f"/new.json?page={page}")
        response = session.get(url, timeout=20)
        if not response.ok:
            raise LinuxdoReaderError(f"Failed to load /new topics: HTTP {response.status_code}")
        payload = response.json()
        page_topics = payload.get("topic_list", {}).get("topics", [])
        topics.extend(page_topics)
    return topics


def calculate_positions(topic_json: Dict, start_from_current: bool) -> Tuple[int, int]:
    highest_post_number = topic_json.get("highest_post_number")
    posts_count = topic_json.get("posts_count")
    total_posts = highest_post_number or posts_count
    if not total_posts:
        raise LinuxdoReaderError("Unable to determine total posts from topic JSON.")
    last_read = topic_json.get("last_read_post_number") or 1
    start_position = last_read if start_from_current else 1
    return start_position, int(total_posts)


def iter_batches(start: int, end: int, min_size: int, max_size: int) -> Iterable[Tuple[int, int]]:
    cursor = start
    while cursor <= end:
        batch_size = random.randint(min_size, max_size)
        batch_end = min(cursor + batch_size - 1, end)
        yield cursor, batch_end
        cursor = batch_end + 1


def build_timings_payload(
    start_id: int,
    end_id: int,
    topic_id: int,
    min_read_time: int,
    max_read_time: int,
) -> Dict[str, str]:
    payload: Dict[str, str] = {}
    total_time = 0
    for post_id in range(start_id, end_id + 1):
        read_time = random.randint(min_read_time, max_read_time)
        payload[f"timings[{post_id}]"] = str(read_time)
        total_time += read_time
    payload["topic_time"] = str(total_time)
    payload["topic_id"] = str(topic_id)
    return payload


def parse_topic_id(topic_url: str) -> int:
    path_parts = urlparse(topic_url).path.strip("/").split("/")
    if len(path_parts) < 3:
        raise LinuxdoReaderError("Unable to parse topic ID from URL.")
    try:
        return int(path_parts[-1])
    except ValueError as exc:
        raise LinuxdoReaderError("Unable to parse topic ID from URL.") from exc


def send_batch(
    session: requests.Session,
    csrf_token: str,
    base_url: str,
    payload: Dict[str, str],
    retries: int,
) -> None:
    endpoint = urljoin(base_url, "/topics/timings")
    for attempt in range(retries + 1):
        response = session.post(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-CSRF-Token": csrf_token,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=20,
        )
        if response.ok:
            return
        if attempt < retries:
            time.sleep(2)
            continue
        raise LinuxdoReaderError(f"POST timings failed: HTTP {response.status_code}")


def read_topic(
    session: requests.Session,
    base_url: str,
    topic_url: str,
    config: Config,
    dry_run: bool,
) -> None:
    csrf_token = fetch_csrf_token(session, topic_url)
    topic_json = fetch_topic_json(session, topic_url)
    topic_id = parse_topic_id(topic_url)
    start_position, total_posts = calculate_positions(topic_json, config.start_from_current)

    print(
        "Start reading: topic_id={}, start={}, total_posts={}".format(
            topic_id, start_position, total_posts
        )
    )

    for start_id, end_id in iter_batches(
        start_position, total_posts, config.min_req_size, config.max_req_size
    ):
        payload = build_timings_payload(
            start_id,
            end_id,
            topic_id,
            config.min_read_time,
            config.max_read_time,
        )
        progress = round(end_id / total_posts * 100, 2)
        if dry_run:
            print(f"[dry-run] Would send {start_id}-{end_id} ({progress}%)")
        else:
            send_batch(session, csrf_token, base_url, payload, config.retry_count)
            print(f"Sent {start_id}-{end_id} ({progress}%)")
        delay = config.base_delay + random.randint(0, config.random_delay_range)
        time.sleep(delay / 1000)


def main() -> int:
    args = parse_args()
    config = build_config(args)
    base_url = args.base_url.rstrip("/")

    if not args.topic_url and not args.all_new:
        raise LinuxdoReaderError("Provide --topic-url or use --all-new.")

    if not args.cookie and not args.username:
        raise LinuxdoReaderError("Provide --cookie or --username/--password for login.")

    session = init_session(args.cookie, config.user_agent)

    if args.username:
        password = args.password or (os.environ.get(args.password_env) if args.password_env else "")
        if not password:
            raise LinuxdoReaderError("Password required for login.")
        login(session, base_url, args.username, password)

    if args.topic_url:
        topic_url = normalize_topic_url(args.topic_url)
        read_topic(session, base_url, topic_url, config, args.dry_run)
    if args.all_new:
        topics = fetch_new_topics(session, base_url, args.new_pages)
        if args.max_topics:
            topics = topics[: args.max_topics]
        for topic in topics:
            topic_id = topic.get("id")
            slug = topic.get("slug") or "topic"
            if not topic_id:
                continue
            topic_url = urljoin(base_url, f"/t/{slug}/{topic_id}")
            print(f"Reading topic: {topic_url}")
            read_topic(session, base_url, topic_url, config, args.dry_run)
            time.sleep(config.topic_delay / 1000)

    print("Done.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LinuxdoReaderError as exc:
        print(f"Error: {exc}")
        sys.exit(1)
