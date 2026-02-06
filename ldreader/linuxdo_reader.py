#!/usr/bin/env python3
import argparse
import random
import re
import sys
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_BASE_URL = "https://linux.do"


class ReaderError(Exception):
    pass


@dataclass(frozen=True)
class ReadConfig:
    base_delay: int
    random_delay: int
    min_req_size: int
    max_req_size: int
    min_read_time: int
    max_read_time: int
    max_retries: int
    start_from_current: bool
    dry_run: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Linux.do 自动阅读程序（基于 Discourse /topics/timings）",
    )
    parser.add_argument(
        "--topic-url",
        help="单个帖子地址，例如 https://linux.do/t/xxx/12345",
    )
    parser.add_argument(
        "--scan-new",
        action="store_true",
        help="遍览全站新帖子并循环阅读",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="站点根地址（默认 https://linux.do）",
    )
    parser.add_argument(
        "--cookie",
        help="浏览器登录后的 Cookie 字符串（会用于请求头 Cookie）",
    )
    parser.add_argument(
        "--cookie-file",
        help="包含 Cookie 字符串的文件路径",
    )
    parser.add_argument("--username", help="账号用户名")
    parser.add_argument("--password", help="账号密码")
    parser.add_argument(
        "--proxy",
        help="代理地址，例如 http://user:pass@host:port",
    )
    parser.add_argument("--base-delay", type=int, default=2500, help="基础延迟毫秒")
    parser.add_argument("--random-delay", type=int, default=800, help="随机延迟范围毫秒")
    parser.add_argument("--min-req-size", type=int, default=8, help="每次请求最小回复数")
    parser.add_argument("--max-req-size", type=int, default=20, help="每次请求最大回复数")
    parser.add_argument("--min-read-time", type=int, default=800, help="最小阅读时间毫秒")
    parser.add_argument("--max-read-time", type=int, default=3000, help="最大阅读时间毫秒")
    parser.add_argument(
        "--start-from-current",
        action="store_true",
        help="从当前阅读位置开始，而不是从 1 开始",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅打印请求计划，不发送 POST 请求",
    )
    parser.add_argument("--max-retries", type=int, default=3, help="失败重试次数")
    parser.add_argument("--loop-delay", type=int, default=60, help="循环间隔秒数")
    parser.add_argument("--max-cycles", type=int, default=0, help="最大循环次数（0=无限）")
    parser.add_argument("--max-topics", type=int, default=50, help="每轮最多读取的新帖子数")
    return parser.parse_args()


def load_cookie(args: argparse.Namespace) -> str | None:
    if args.cookie and args.cookie_file:
        raise ReaderError("不能同时指定 --cookie 和 --cookie-file")
    if args.cookie:
        return args.cookie.strip()
    if args.cookie_file:
        with open(args.cookie_file, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    return None


def ensure_topic_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ReaderError("topic_url 不是有效的 URL")
    if not re.search(r"/t/[^/]+/\d+", parsed.path):
        raise ReaderError("topic_url 不是标准的帖子地址（应包含 /t/xxx/123）")


def extract_csrf(html: str) -> str:
    match = re.search(r"<meta\s+name=\"csrf-token\"\s+content=\"([^\"]+)\"", html)
    if not match:
        raise ReaderError("未找到 csrf-token，请确认已登录或页面正常加载")
    return match.group(1)


def extract_replies_info(html: str) -> tuple[int, int]:
    match = re.search(
        r"timeline-replies[^>]*>\s*([^<]+)",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise ReaderError("未找到 timeline-replies 信息，请确认在帖子页面")
    numbers = [int(value) for value in re.findall(r"\d+", match.group(1))]
    if len(numbers) < 2:
        raise ReaderError("无法解析回复数量信息")
    return numbers[0], numbers[1]


def build_timings_payload(
    start_id: int,
    end_id: int,
    min_read: int,
    max_read: int,
    topic_id: str,
) -> dict[str, str]:
    payload: dict[str, str] = {}
    for index in range(start_id, end_id + 1):
        payload[f"timings[{index}]"] = str(random.randint(min_read, max_read))
    topic_time = random.randint(min_read * (end_id - start_id + 1), max_read * (end_id - start_id + 1))
    payload["topic_time"] = str(topic_time)
    payload["topic_id"] = topic_id
    return payload


def request_page(session: requests.Session, url: str) -> str:
    response = session.get(url)
    if not response.ok:
        raise ReaderError(f"获取页面失败: HTTP {response.status_code}")
    return response.text


def send_timings(
    session: requests.Session,
    csrf_token: str,
    base_url: str,
    payload: dict[str, str],
    retries: int,
) -> None:
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
    }
    timings_url = urljoin(base_url.rstrip("/") + "/", "topics/timings")
    for attempt in range(retries + 1):
        response = session.post(timings_url, data=payload, headers=headers)
        if response.ok:
            return
        if attempt < retries:
            time.sleep(2)
            continue
        raise ReaderError(f"发送 timings 失败: HTTP {response.status_code}")


def create_session(args: argparse.Namespace) -> requests.Session:
    session = requests.Session()
    cookie = load_cookie(args)
    if cookie:
        session.headers.update({"Cookie": cookie})
    if args.proxy:
        session.proxies.update({"http": args.proxy, "https": args.proxy})
    return session


def login_if_needed(session: requests.Session, base_url: str, args: argparse.Namespace) -> None:
    if not args.username and not args.password:
        return
    if not args.username or not args.password:
        raise ReaderError("必须同时提供 --username 与 --password")
    login_url = urljoin(base_url.rstrip("/") + "/", "login")
    html = request_page(session, login_url)
    csrf_token = extract_csrf(html)
    session_url = urljoin(base_url.rstrip("/") + "/", "session")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest",
    }
    payload = {
        "login": args.username,
        "password": args.password,
    }
    response = session.post(session_url, data=payload, headers=headers)
    if not response.ok:
        raise ReaderError(f"登录失败: HTTP {response.status_code}")


def read_topic(
    session: requests.Session,
    topic_url: str,
    base_url: str,
    config: ReadConfig,
) -> None:
    ensure_topic_url(topic_url)
    html = request_page(session, topic_url)
    csrf_token = extract_csrf(html)
    current_position, total_replies = extract_replies_info(html)
    topic_id = topic_url.rstrip("/").split("/")[-1]
    start_position = current_position if config.start_from_current else 1
    if start_position > total_replies:
        raise ReaderError("起始位置超过总回复数")

    print(
        "读取计划: topic_id={}, 起始位置={}, 总回复={}"
        .format(topic_id, start_position, total_replies)
    )

    next_position = start_position
    while next_position <= total_replies:
        batch_size = random.randint(config.min_req_size, config.max_req_size)
        start_id = next_position
        end_id = min(next_position + batch_size - 1, total_replies)
        payload = build_timings_payload(
            start_id,
            end_id,
            config.min_read_time,
            config.max_read_time,
            topic_id,
        )
        progress = round(end_id / total_replies * 100, 2)
        if config.dry_run:
            print(f"[DryRun] {start_id}-{end_id} ({progress}%)")
        else:
            print(f"发送 {start_id}-{end_id} ({progress}%)")
            send_timings(session, csrf_token, base_url, payload, config.max_retries)
        delay_ms = config.base_delay + random.randint(0, config.random_delay)
        time.sleep(delay_ms / 1000)
        next_position = end_id + 1


def fetch_new_topics(session: requests.Session, base_url: str, limit: int) -> list[str]:
    new_url = urljoin(base_url.rstrip("/") + "/", "new.json")
    response = session.get(new_url)
    if not response.ok:
        raise ReaderError(f"获取新帖子失败: HTTP {response.status_code}")
    data = response.json()
    topics = data.get("topic_list", {}).get("topics", [])
    urls: list[str] = []
    for topic in topics[:limit]:
        slug = topic.get("slug")
        topic_id = topic.get("id")
        if slug and topic_id:
            urls.append(urljoin(base_url.rstrip("/") + "/", f"t/{slug}/{topic_id}"))
    return urls


def iter_topic_urls(args: argparse.Namespace, session: requests.Session) -> Iterable[str]:
    if args.topic_url:
        yield args.topic_url
        return
    if not args.scan_new:
        return
    visited: set[str] = set()
    cycles = 0
    while True:
        if args.max_cycles and cycles >= args.max_cycles:
            break
        urls = fetch_new_topics(session, args.base_url, args.max_topics)
        for url in urls:
            if url in visited:
                continue
            visited.add(url)
            yield url
        cycles += 1
        time.sleep(args.loop_delay)


def build_config(args: argparse.Namespace) -> ReadConfig:
    return ReadConfig(
        base_delay=args.base_delay,
        random_delay=args.random_delay,
        min_req_size=args.min_req_size,
        max_req_size=args.max_req_size,
        min_read_time=args.min_read_time,
        max_read_time=args.max_read_time,
        max_retries=args.max_retries,
        start_from_current=args.start_from_current,
        dry_run=args.dry_run,
    )


def validate_args(args: argparse.Namespace) -> None:
    if not args.topic_url and not args.scan_new:
        raise ReaderError("请提供 --topic-url 或 --scan-new")
    if args.topic_url and args.scan_new:
        raise ReaderError("--topic-url 与 --scan-new 不能同时使用")
    if args.base_url:
        parsed = urlparse(args.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ReaderError("--base-url 必须是有效的 http(s) URL")


def main() -> int:
    args = parse_args()
    try:
        validate_args(args)
        session = create_session(args)
        login_if_needed(session, args.base_url, args)
        config = build_config(args)
        for topic_url in iter_topic_urls(args, session):
            read_topic(session, topic_url, args.base_url, config)
        print("完成")
        return 0
    except KeyboardInterrupt:
        print("用户中断")
        return 1
    except ReaderError as error:
        print(f"错误: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
