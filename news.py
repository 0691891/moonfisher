#!/usr/bin/env python3
"""
新闻抓取（v0.1）
- 每只 ticker：Yahoo 免费新闻流，取最近约10条
- 宏观：SPY / QQQ 新闻流作为市场代理
- 影响标记：命中关键词（财报/指引/评级/并购/监管/CPI/FOMC等）标为【重大】
输出 reports/news-YYYY-MM-DD.json + .md，仅供参考。
"""
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from datetime import timezone
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan import all_tickers, SECTORS  # noqa: E402

BASE = Path(__file__).resolve().parent
MACRO_TICKERS = ["SPY", "QQQ"]

IMPACT_WORDS = [
    "earnings", "results", "guidance", "outlook", "beat", "miss",
    "upgrade", "downgrade", "price target", "initiated", "merger",
    "acquisition", "buyback", "dividend", "split", "fda", "approval",
    "lawsuit", "settlement", "ceo", "cfo", "layoff", "layoffs",
    "restructuring", "bankrupt", "delist", "offering", "stake",
    "cpi", "inflation", "payrolls", "jobs report", "fomc", "fed ",
    "federal reserve", "rate cut", "rate hike", "powell", "gdp",
    "recession", "tariff", "opec",
    "财报", "业绩", "指引", "上调", "下调评级", "目标价", "收购", "合并",
    "回购", "分红", "拆股", "诉讼", "降息", "加息", "通胀", "非农",
    "美联储", "关税",
]


def is_impact(title):
    t = (title or "").lower()
    return any(w in t for w in IMPACT_WORDS)


def sector_of(ticker):
    for sec, ts in SECTORS.items():
        if ticker in ts:
            return sec
    return "宏观"


def _norm_item(n):
    """兼容 yfinance 新旧两种 news 格式。"""
    c = n.get("content") if isinstance(n.get("content"), dict) else n
    title = c.get("title", "") or ""
    prov = c.get("provider") or {}
    publisher = prov.get("displayName", "") if isinstance(prov, dict) else ""
    link = ""
    for k in ("clickThroughUrl", "canonicalUrl"):
        u = c.get(k)
        if isinstance(u, dict) and u.get("url"):
            link = u["url"]
            break
        elif isinstance(u, str) and u:
            link = u
            break
    if not link:
        link = n.get("link", "") or ""
    ts = c.get("pubDate") or n.get("providerPublishTime")
    dt = ""
    try:
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%m-%d %H:%M")
        elif isinstance(ts, str) and ts:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
    except Exception:
        dt = ""
    return {"title": title, "publisher": publisher, "link": link, "time": dt,
            "impact": is_impact(title)}


def fetch_news(ticker, limit=10):
    items = []
    for attempt in range(3):
        try:
            items = yf.Ticker(ticker).news or []
            break
        except Exception as e:
            if attempt == 2:
                print("[warn] %s 新闻获取失败: %s" % (ticker, e), file=sys.stderr)
                return []
            time.sleep(2)
    return [_norm_item(n) for n in items[:limit] if _norm_item(n)["title"]]


def main():
    stamp = datetime.now().astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    data = {"date": stamp, "tickers": {}, "macro": []}
    seen = set()
    for t in all_tickers():
        uniq = []
        for n in fetch_news(t):
            if n["title"] and n["title"] not in seen:
                seen.add(n["title"])
                uniq.append(n)
        data["tickers"][t] = {"sector": sector_of(t), "news": uniq}
        time.sleep(0.3)
    for m in MACRO_TICKERS:
        for n in fetch_news(m, limit=8):
            if n["title"] and n["title"] not in seen:
                seen.add(n["title"])
                nn = dict(n)
                nn["source"] = m
                data["macro"].append(nn)
        time.sleep(0.3)
    (BASE / "reports" / ("news-%s.json" % stamp)).write_text(
        json.dumps(data, ensure_ascii=False, indent=2))
    L = ["# 新闻扫描 " + stamp, "",
         "【重大】= 命中财报/指引/评级/并购/监管/宏观关键词，仅供参考。", "",
         "## 宏观 / 市场", ""]
    if data["macro"]:
        for n in data["macro"]:
            tag = "【重大】" if n["impact"] else ""
            L.append("- %s%s %s（%s）" % (tag, n["time"], n["title"], n["publisher"]))
    else:
        L.append("- 暂无")
    L.append("")
    for t in all_tickers():
        e = data["tickers"][t]
        if not e["news"]:
            continue
        L.append("## %s（%s）" % (t, e["sector"]))
        L.append("")
        for n in sorted(e["news"], key=lambda x: (not x["impact"], x["time"])):
            tag = "【重大】" if n["impact"] else ""
            L.append("- %s%s %s（%s）" % (tag, n["time"], n["title"], n["publisher"]))
        L.append("")
    md = "\n".join(L)
    (BASE / "reports" / ("news-%s.md" % stamp)).write_text(md)
    print(md)


if __name__ == "__main__":
    main()
