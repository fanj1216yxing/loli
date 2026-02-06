# Linux.do Auto Reader (Python)

> ⚠️ 风险提示：自动化脚本可能违反论坛规则并带来账号风险（封禁/限制等）。
> 使用前请自行评估风险，本项目不承担责任。

这个脚本使用 Discourse 的 `/topics/timings` 接口模拟阅读，逻辑参考了同目录下的油猴脚本。

## 前置条件

- 账号密码登录（脚本自动登录获取 Cookie）
  - 推荐通过 `--password-env` 读取环境变量，避免明文写入命令行。
- 或者提供已经登录的 `Cookie`（可选）

## 使用方式

```bash
export LINUXDO_PASSWORD="your_password"
python3 linuxdo_reader.py \
  --topic-url "https://linux.do/t/帖子标题/12345" \
  --username "your_username_or_email" \
  --password-env LINUXDO_PASSWORD
```

全站读取新帖子（/new）：  

```bash
export LINUXDO_PASSWORD="your_password"
python3 linuxdo_reader.py \
  --all-new \
  --base-url "https://linux.do" \
  --username "your_username_or_email" \
  --password-env LINUXDO_PASSWORD \
  --max-topics 30 \
  --new-pages 1
```

### 常用参数

- `--start-from-current`：从当前阅读进度开始（依赖 topic JSON 的 `last_read_post_number`）
- `--min-req-size` / `--max-req-size`：每次请求的帖子数量范围
- `--min-read-time` / `--max-read-time`：每个帖子的阅读时间范围（毫秒）
- `--base-delay` / `--random-delay-range`：批次间隔基础值+随机值（毫秒）
- `--topic-delay`：不同 topic 之间的延迟（毫秒）
- `--all-new`：读取 /new 列表的帖子
- `--max-topics` / `--new-pages`：控制 /new 的抓取范围
- `--dry-run`：不发送请求，仅打印执行计划

示例：

```bash
python3 linuxdo_reader.py \
  --topic-url "https://linux.do/t/帖子标题/12345" \
  --username "your_username_or_email" \
  --password-env LINUXDO_PASSWORD \
  --start-from-current \
  --min-req-size 5 \
  --max-req-size 12 \
  --min-read-time 1000 \
  --max-read-time 2800
```

## 常见问题

- **CSRF token 找不到**：通常表示未登录或登录失败。
- **HTTP 403/429**：可能被风控或触发限流，请降低速度或暂停使用。

## 文件说明

- `linuxdo_reader.py`：Python 脚本
- `LINUXDO ReadBoost.js`、`Linuxdo活跃-2.0.1.user.js`：参考的油猴脚本
