import sys, pathlib
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import rss_digest as rd

NOW = datetime.now(timezone.utc)
RSS = f"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Fresh &amp; new</title><link>https://a.example/1</link>
<pubDate>{(NOW - timedelta(hours=2)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
<description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description><source>Blog A</source></item>
<item><title>Old</title><link>https://a.example/2</link>
<pubDate>{(NOW - timedelta(hours=50)).strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate></item>
</channel></rss>"""
ATOM = f"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Atom post</title><link rel="alternate" href="https://b.example/x"/>
<published>{(NOW - timedelta(hours=1)).isoformat()}</published><summary>sum</summary></entry></feed>"""


def test_parse_rss_and_atom():
    r = rd.parse_feed(RSS)
    assert r[0][0] == "Fresh & new" and r[0][1] == "https://a.example/1" and r[0][4] == "Blog A"
    a = rd.parse_feed(ATOM)
    assert a[0][1] == "https://b.example/x" and a[0][2] is not None


def test_feeds_filters_and_supplements(capsys):
    pages = {rd.PRIMARY[0][1]: RSS, **{u: ATOM for _, u in rd.SUPPLEMENT}}
    with mock.patch.object(rd, "fetch", side_effect=lambda u: pages[u]):
        rd.main(["feeds", "--min", "5"])
    out = capsys.readouterr().out
    assert "Fresh & new" in out and "Old" not in out
    assert "Hello world" in out
    assert out.count("Atom post") == 1  # 去重


def test_article_extracts_and_truncates():
    page = "<html><nav>menu menu</nav><article><p>" + "Sentence here. " * 400 + "</p><script>x()</script></article></html>"
    t = rd.extract_article(page, 500)
    assert "menu" not in t and "x()" not in t and t.endswith("[已截断]") and len(t) < 520


def test_daily_pipeline_with_fake_llm(tmp_path):
    import json, daily
    pages = {rd.PRIMARY[0][1]: RSS, **{u: ATOM for _, u in rd.SUPPLEMENT}}
    calls = []

    def fake_llm(system, user, temp=0.3):
        calls.append(user)
        if len(calls) == 1:
            return "```json\n" + json.dumps({"top10": [{"id": 1, "category": "技术与产业", "cross_tag": "无"},
                                                      {"id": 2, "category": "人文与思想", "cross_tag": "无"}],
                                            "top3_ids": [1], "note": ""}) + "\n```"
        return "# 日报\n"

    with mock.patch.object(rd, "fetch", side_effect=lambda u: pages.get(u, "<article><p>body body body body body body body body body body.</p></article>")):
        daily.main(["--out", str(tmp_path)], llm=fake_llm)
    assert len(calls) == 2 and "原文节选" in calls[1] and "https://a.example/1" in calls[1]
    assert list(tmp_path.glob("* - Karpathy 精选 RSS 日报.md"))
