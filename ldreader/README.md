# Linux.do 自动阅读程序（Python）

该脚本基于 Discourse 的 `/topics/timings` 接口，模拟阅读帖子的回复数量。支持遍览新帖子循环阅读，并可通过账号密码登录与代理访问。

## 安装依赖

```bash
pip install requests
```

## 使用方式

### 单个帖子

```bash
python ldreader/linuxdo_reader.py \
  --topic-url "https://linux.do/t/帖子标题/12345" \
  --cookie "_forum_session=...; ..."
```

### 遍览新帖子循环阅读

```bash
python ldreader/linuxdo_reader.py \
  --scan-new \
  --base-url "https://linux.do" \
  --username "your_user" \
  --password "your_pass" \
  --proxy "http://user:pass@host:port" \
  --loop-delay 60 \
  --max-topics 50
```

如果代理不可用（例如本地代理端口未开启），程序会提示“代理连接失败”。此时请检查代理地址或去掉 `--proxy` 参数。

如果返回 403，可能触发了 Cloudflare 验证。请先在浏览器手动通过验证并登录后，再将浏览器 Cookie 传给脚本（`--cookie` 或 `--cookie-file`），或直接移除 `--username/--password` 并仅使用 Cookie。

如果希望在遇到 403 时自动弹出页面以便手动验证，可以使用 `--open-403`，程序会打开浏览器并等待你完成验证后继续。

### 可选参数示例

```bash
python ldreader/linuxdo_reader.py \
  --topic-url "https://linux.do/t/帖子标题/12345" \
  --cookie-file ./cookie.txt \
  --base-delay 2500 \
  --random-delay 800 \
  --min-req-size 8 \
  --max-req-size 20 \
  --min-read-time 800 \
  --max-read-time 3000 \
  --start-from-current
```

如果只想查看执行计划、不发送请求，可以添加 `--dry-run`。
