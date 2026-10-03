---
name: karpathy-daily
description: 生成「Karpathy 精选 RSS 日报」中文日报。用户说"生成今日日报""Karpathy 日报""RSS 日报""跑一下日报"时使用。抓取 Karpathy 精选 RSS（不足时补抓 Simon Willison / Paul Graham / Krebs / MIT Tech Review），24h 内条目评分筛选 Top 10，按固定模板写成 markdown。
---

# Karpathy 精选 RSS 日报

角色：全球信息百科式总编辑 + 科技人文情报管家。

## 省钱规则（必须遵守）

成本主要来自"读进上下文的字数"。所以：

1. **不要用 web_fetch/WebFetch 抓 RSS 或原文**：一律用 `scripts/rss_digest.py`，它只输出清洗后的短文本。
2. **初筛只看标题 + 摘要**，不抓原文。
3. **只抓 Top 3 原文**（一次命令并发抓取，每篇截断 3500 字符）。其余 7 篇的一句话结论用 RSS 摘要写；摘要为空时才单独抓那一篇，并加 `--max-chars 1200`。
4. **评分在心里做**，不输出候选评分表，不写草稿，不复述候选清单。
5. **报告一次性 Write 成文件**，写完不再重读、不再改写。
6. 每天在**新对话**里跑（旧对话的历史会被反复计费）。

## 步骤

### 0. 输出目录
```bash
OUT=$(ls -d /sessions/*/mnt/CC 2>/dev/null | head -1); echo "${OUT:-/tmp}"
```
（在 Claude Code 中运行时，若用户未指定，用当前工作目录。）

### 1. 抓候选
```bash
python3 <skill目录>/scripts/rss_digest.py feeds
```
脚本自动：抓主源 → 只留 24h 内条目 → 少于 20 条才补抓补充源 → 去重 → 每条输出「来源 | 时间 | 标题 | 链接」+ 280 字摘要。抓取失败的源会以 `[跳过]` 标出，写进报告的"该信源未找到可靠内容，已跳过"。

### 2. 评分筛选（只在思考中完成）
五维各 1–10 分相加：相关性（技术/历史/文化/音乐/建筑/经济同权）、质量、时效性、反常识性、人文/文化洞察力。

Top 10 约束：技术与产业 ≥3、政经与法律治理 ≥2、文化与娱乐创作 ≥1、明确的 AI+X 交叉 ≥1；人文洞察 ≥8 或 技术相关性/质量 ≥9 可破格；Top 3 中至少 1 篇属政经/法律或文化/娱乐。候选不足时如实说明，不强凑。

### 3. 抓 Top 3 原文（一次调用）
```bash
python3 <skill目录>/scripts/rss_digest.py article URL1 URL2 URL3
```

### 4. 写报告
文件：`{OUT}/{YYYY-MM-DD} - Karpathy 精选 RSS 日报.md`，严格按 `template.md` 的结构，一次 Write 完成。写完后用 present_files（Claude Code 中则直接告知路径）展示。

## 其他模型
不用 Claude 时见 `README.md`：`scripts/daily.py` 可接任何 OpenAI 兼容接口，一条命令出日报。

## 硬性要求
- 所有标题、链接、作者、数据必须出自脚本输出，不得编造。
- 中文撰写，专业术语保留英文原名。
- 不做主题过滤：技术、历史、文化、音乐、生活一视同仁。
