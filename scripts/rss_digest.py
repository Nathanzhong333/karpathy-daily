#!/usr/bin/env python3
"""RSS 日报的抓取/清洗脚本。只用标准库，输出精简文本，避免原始 XML/HTML 进入模型上下文。

用法：
  python3 rss_digest.py feeds [--hours 24] [--min 20] [--summary-chars 280]
      抓主源；24h 内条目少于 --min 时自动补抓补充源。输出每条一行的候选清单。
  python3 rss_digest.py article URL [URL ...] [--max-chars 3500]
      并发抓原文，抽取正文并截断。
"""
import argparse
import concurrent.futures as cf
import email.utils
import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

PRIMARY = [("Karpathy精选", "https://rssify.youmind.ai/pack/andrej-karpathy-curated-rss")]
SUPPLEMENT = [
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("Paul Graham", "http://www.paulgraham.com/rss.html"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/"),
]
UA = "Mozilla/5.0 (compatible; rss-digest/1.0)"
TIMEOUT = 20


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


class _Text(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg", "figure"}
    BLOCK = {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "blockquote", "pre", "tr", "article", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(s):
    p = _Text()
    p.feed(s or "")
    lines = (re.sub(r"[ \t ]+", " ", l).strip() for l in "".join(p.out).splitlines())
    return "\n".join(l for l in lines if l)


def one_line(s, n):
    s = re.sub(r"\s+", " ", html_to_text(html.unescape(s or ""))).strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el, *names):
    c = _child(el, *names)
    return (c.text or "").strip() if c is not None else ""


def parse_feed(xml_text):
    """返回 [(title, url, datetime|None, summary_html, item_source)]，兼容 RSS 2.0 / Atom / RDF。"""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    items = [e for e in root.iter() if _local(e.tag) in ("item", "entry")]
    out = []
    for e in items:
        title = _text(e, "title")
        link = _text(e, "link")
        if not link:
            for c in e:
                if _local(c.tag) == "link" and c.get("rel", "alternate") == "alternate" and c.get("href"):
                    link = c.get("href")
                    break
        date = parse_date(_text(e, "pubDate", "published", "updated", "date"))
        summary = _text(e, "description", "summary", "encoded", "content")
        src = _child(e, "source")
        src_name = (src.text or "").strip() if src is not None and src.text else ""
        if not src_name:
            author = _child(e, "author", "creator")
            if author is not None:
                src_name = (author.text or "").strip() or _text(author, "name")
        out.append((html.unescape(title), link.strip(), date, summary, src_name))
    return out


def collect(feeds, since):
    rows, notes = [], []
    with cf.ThreadPoolExecutor(8) as ex:
        futs = {ex.submit(fetch, url): (name, url) for name, url in feeds}
        for f in cf.as_completed(futs):
            name, url = futs[f]
            try:
                entries = parse_feed(f.result())
            except Exception as e:  # noqa: BLE001 —— 任何失败都只记录、跳过
                notes.append(f"[跳过] {name}: {type(e).__name__}: {e}")
                continue
            fresh = [x for x in entries if x[2] and x[2] >= since]
            undated = sum(1 for x in entries if not x[2])
            notes.append(f"[ok] {name}: 共 {len(entries)} 条，24h 内 {len(fresh)} 条" + (f"，{undated} 条无日期已丢弃" if undated else ""))
            rows += [(name, *x) for x in fresh]
    return rows, notes


def get_candidates(hours=24, min_items=20, summary_chars=280):
    """返回 (候选列表, 日志)。候选 = (feed, title, url, date, summary, src)，已去重、按时间倒序。"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows, notes = collect(PRIMARY, since)
    if len(rows) < min_items:
        notes.append(f"主源 {hours}h 仅 {len(rows)} 条 (<{min_items})，补抓补充源")
        more, n2 = collect(SUPPLEMENT, since)
        rows += more
        notes += n2
    seen, uniq = set(), []
    for r in sorted(rows, key=lambda r: r[3], reverse=True):
        key = r[2] or r[1]
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq, notes


def format_candidates(uniq, summary_chars=280):
    lines = []
    for i, (feed, title, url, date, summary, src) in enumerate(uniq, 1):
        lines.append(f"[{i}] {src or feed} | {date:%m-%d %H:%M}Z | {one_line(title, 160)} | {url}")
        s = one_line(summary, summary_chars)
        if s:
            lines.append(f"    {s}")
    return "\n".join(lines)


def cmd_feeds(a):
    uniq, notes = get_candidates(a.hours, a.min, a.summary_chars)
    print(f"# 今日 {datetime.now().astimezone():%Y-%m-%d}，窗口 {a.hours}h，候选 {len(uniq)} 条")
    for n in notes:
        print("# " + n)
    print(format_candidates(uniq, a.summary_chars))


def extract_article(page, max_chars):
    m = re.search(r"<article\b.*?</article>", page, re.S | re.I) or re.search(r"<main\b.*?</main>", page, re.S | re.I)
    text = html_to_text(m.group(0) if m else page)
    # 去掉过短的导航/按钮碎行
    text = "\n".join(l for l in text.splitlines() if len(l) > 40 or l.endswith((".", "。", ":", "?", "!")))
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "\n…[已截断]"


def cmd_article(a):
    with cf.ThreadPoolExecutor(6) as ex:
        res = list(ex.map(lambda u: _safe_article(u, a.max_chars), a.urls))
    for url, body in zip(a.urls, res):
        print(f"===== {url}\n{body}\n")


def _safe_article(url, n):
    try:
        return extract_article(fetch(url), n)
    except Exception as e:  # noqa: BLE001
        return f"[抓取失败] {type(e).__name__}: {e}"


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("feeds")
    f.add_argument("--hours", type=int, default=24)
    f.add_argument("--min", type=int, default=20)
    f.add_argument("--summary-chars", type=int, default=280)
    f.set_defaults(fn=cmd_feeds)
    r = sub.add_parser("article")
    r.add_argument("urls", nargs="+")
    r.add_argument("--max-chars", type=int, default=3500)
    r.set_defaults(fn=cmd_article)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
