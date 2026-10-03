#!/usr/bin/env python3
"""模型无关的日报生成器：任何兼容 OpenAI Chat Completions 的服务都能用。只用标准库。

环境变量：
  LLM_API_KEY   必填（本地 Ollama 可随便填）
  LLM_BASE_URL  默认 https://api.openai.com/v1
  LLM_MODEL     必填，如 gpt-4.1 / deepseek-chat / gemini-2.5-flash / qwen-plus
常见 BASE_URL：
  DeepSeek  https://api.deepseek.com/v1
  Gemini    https://generativelanguage.googleapis.com/v1beta/openai
  Ollama    http://localhost:11434/v1
  Moonshot  https://api.moonshot.cn/v1
用法：python3 daily.py [--out DIR] [--hours 24] [--dry-run]
流程：抓候选 →(LLM 调用 1: 评分选 Top10) → 抓 Top3 原文 →(LLM 调用 2: 写报告) → 存 md
"""
import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import rss_digest as rd

ROOT = pathlib.Path(__file__).resolve().parents[1]


def chat(system, user, temperature=0.3):
    base = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    body = json.dumps({
        "model": os.environ["LLM_MODEL"], "temperature": temperature,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(base + "/chat/completions", body, {
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def select(cands, llm=chat):
    prompt = (ROOT / "prompt_select.md").read_text()
    listing = rd.format_candidates(cands)
    for attempt in range(2):
        try:
            sel = parse_json(llm(prompt, listing, 0.2))
            ids = [x["id"] for x in sel["top10"]]
            if all(1 <= i <= len(cands) for i in ids) and len(sel["top3_ids"]) >= 1:
                return sel
        except (ValueError, KeyError, TypeError):
            pass
    raise SystemExit("选稿结果无法解析为合法 JSON，请换更强的模型或重试")


def build_materials(cands, sel, articles):
    meta = {x["id"]: x for x in sel["top10"]}
    top3 = sel["top3_ids"][:3]
    out = ["## Top 3（含原文节选）"]
    for i in top3:
        feed, title, url, date, summary, src = cands[i - 1]
        out += [f"### id={i} | {src or feed} | {meta.get(i, {}).get('category', '')} | 交叉标签：{meta.get(i, {}).get('cross_tag', '无')}",
                f"标题：{title}", f"链接：{url}", "原文节选：", articles.get(url, "[无原文]" ), ""]
    out.append("## 其余入选（仅 RSS 摘要）")
    for x in sel["top10"]:
        i = x["id"]
        if i in top3:
            continue
        feed, title, url, date, summary, src = cands[i - 1]
        out += [f"- id={i} | {src or feed} | {x['category']} | 交叉标签：{x.get('cross_tag', '无')}",
                f"  标题：{title}", f"  链接：{url}", f"  摘要：{rd.one_line(summary, 400)}"]
    return "\n".join(out)


def main(argv=None, llm=chat):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=".")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--dry-run", action="store_true", help="只抓取并打印候选，不调用模型")
    a = ap.parse_args(argv)

    cands, notes = rd.get_candidates(a.hours)
    print("\n".join("# " + n for n in notes), file=sys.stderr)
    if not cands:
        raise SystemExit("过去 24 小时没有可用条目，已停止（不编造内容）")
    if a.dry_run:
        print(rd.format_candidates(cands))
        return
    sel = select(cands, llm)
    urls = [cands[i - 1][2] for i in sel["top3_ids"][:3]]
    articles = {u: rd._safe_article(u, 3500) for u in urls}
    stats = f"{len(cands)} 条 RSS 更新（来自 {len({c[0] for c in cands})} 个信源），精选 {len(sel['top10'])} 篇，Top3 精读 {len(urls)} 篇"
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    user = (f"日期：{today}\n统计：{stats}\n选稿备注：{sel.get('note') or '无'}\n抓取日志：\n"
            + "\n".join(notes) + "\n\n【模板】\n" + (ROOT / "template.md").read_text()
            + "\n\n【材料】\n" + build_materials(cands, sel, articles))
    report = llm((ROOT / "prompt_write.md").read_text(), user, 0.4)
    path = pathlib.Path(a.out) / f"{today} - Karpathy 精选 RSS 日报.md"
    path.write_text(report.strip() + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
