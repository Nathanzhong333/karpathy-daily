# karpathy-daily：模型无关用法

三种用法，按需选：

## A. 一条命令（任何模型，最省事）
```bash
export LLM_API_KEY=sk-...
export LLM_BASE_URL=https://api.deepseek.com/v1   # 任意 OpenAI 兼容端点
export LLM_MODEL=deepseek-chat
python3 scripts/daily.py --out ./reports
```
全程只调用 2 次模型：① 在候选标题+摘要里选 Top10（输出一小段 JSON）；② 基于 Top3 原文节选 + 其余 7 篇摘要写完整日报。可用 `--dry-run` 只看抓取结果。
可配 cron：`0 8 * * * cd /path && python3 scripts/daily.py --out ~/reports`。

## B. 带终端/工具的 Agent（Codex CLI、Gemini CLI、Cursor、OpenClaw 等）
把 `SKILL.md` 里「步骤」一节当提示词，让它调用 `scripts/rss_digest.py`。脚本只靠 Python 3 标准库。

## C. 纯聊天窗口（ChatGPT、Gemini、Kimi 等，无工具）
1. 本机运行 `python3 scripts/rss_digest.py feeds`，复制输出。
2. 贴给模型，前面加上 `prompt_select.md`，让它选稿。
3. 对选出的 3 篇运行 `python3 scripts/rss_digest.py article URL1 URL2 URL3`，复制输出。
4. 把 `prompt_write.md` + `template.md` + 选稿结果 + 原文节选一起贴给模型。

## 模型选择提示
写作质量主要取决于第 2 步。选稿步骤要求稳定输出 JSON，太小的本地模型可能失败，脚本会重试 1 次后报错退出。
