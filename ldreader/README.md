# Linux.do 自动阅读程序（Python）

该脚本基于 Discourse 的 `/topics/timings` 接口，模拟阅读帖子的回复数量。它需要登录后的 Cookie 才能正常提交请求。

## 安装依赖

```bash
pip install requests
```

## 使用方式

```bash
python ldreader/linuxdo_reader.py \
  "https://linux.do/t/帖子标题/12345" \
  --cookie "_forum_session=...; ..."
```

可选参数示例：

```bash
python ldreader/linuxdo_reader.py \
  "https://linux.do/t/帖子标题/12345" \
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
