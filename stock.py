#!/usr/bin/env python3
"""正股小额买入 + 基本面快照（v2.1 配套页）
抓取全 universe 的 Yahoo 基本面：估值/增长/盈利/分红/分析师目标价，
算"每$100/$500可买股数"等超低投资视角指标。仅展示数据，不构成买卖建议。
"""
import glob
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import yfinance as yf

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from scan import SECTORS, all_tickers  # noqa: E402
from dip import rate_dip, RATING_LABEL  # noqa: E402

FIELDS = ["longName", "sector", "industry", "currentPrice",
          "regularMarketPrice", "marketCap", "trailingPE", "forwardPE",
          "pegRatio", "priceToBook", "grossMargins", "operatingMargins",
          "profitMargins", "revenueGrowth", "earningsGrowth",
          "earningsQuarterlyGrowth", "returnOnEquity", "returnOnAssets",
          "debtToEquity", "dividendYield", "dividendRate", "beta",
          "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
          "targetMeanPrice", "targetHighPrice", "targetLowPrice",
          "numberOfAnalystOpinions", "recommendationKey"]


def fetch_info(ticker, tries=3):
    for i in range(tries):
        try:
            info = yf.Ticker(ticker).info or {}
            if info.get("currentPrice") or info.get("regularMarketPrice"):
                return {k: info.get(k) for k in FIELDS}
        except Exception as e:
            print(f"[warn] {ticker} info 失败(第{i+1}次): {e}", file=sys.stderr)
        time.sleep(1.5)
    return None


def checklist(f, price):
    """机械勾选（非推荐）：PEG/增长/盈利/ROE/分析师目标价。"""
    items = []
    peg = f.get("pegRatio")
    items.append(("PEG<2", peg is not None and 0 < peg < 2))
    rg = f.get("revenueGrowth")
    items.append(("营收增长>15%", rg is not None and rg > 0.15))
    pm = f.get("profitMargins")
    items.append(("净利率>15%", pm is not None and pm > 0.15))
    roe = f.get("returnOnEquity")
    items.append(("ROE>12%", roe is not None and roe > 0.12))
    tp = f.get("targetMeanPrice")
    items.append(("目标价>现价", tp is not None and price and tp > price))
    return [{"name": n, "pass": bool(p)} for n, p in items]


def latest_scan_detail():
    """读取最新 scan-*.json 的 detail 映射（供抄底评级用）。
    按修改时间取最新，且要求含 v2.1 的 tech_state 字段，跳过 _stale。"""
    cands = [f for f in glob.glob(str(BASE / "reports" / "scan-*.json"))
             if "/_stale/" not in f]
    cands.sort(key=lambda f: Path(f).stat().st_mtime, reverse=True)
    for f in cands:
        try:
            d = json.loads(Path(f).read_text())
            det = {t: (r.get("detail") or {})
                   for t, r in d.get("results", {}).items()}
            if any(v.get("tech_state") for v in det.values()):
                return det
        except Exception:
            continue
    return {}


def main():
    stamp = datetime.now().astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    scan_detail = latest_scan_detail()
    results = {}
    for t in all_tickers():
        f = fetch_info(t)
        if not f:
            results[t] = {"ok": False, "reason": "基本面获取失败"}
            continue
        price = f.get("currentPrice") or f.get("regularMarketPrice")
        tp = f.get("targetMeanPrice")
        hi52 = f.get("fiftyTwoWeekHigh")
        cl = checklist(f, price)
        checks_pass = sum(1 for c in cl if c["pass"])
        dip_score, dip_rating, dip_depth, dip_reasons = rate_dip(
            scan_detail.get(t), checks_pass)
        results[t] = {
            "ok": True, "price": price,
            "per_100": round(100 / price, 2) if price else None,
            "per_500": round(500 / price, 2) if price else None,
            "upside": round(tp / price - 1, 3) if (tp and price) else None,
            "dist_52w_high": round(price / hi52 - 1, 3)
                             if (price and hi52) else None,
            "checks": cl,
            "checks_pass": checks_pass,
            "dip_score": dip_score,
            "dip_rating": dip_rating,
            "dip_depth": round(dip_depth, 4) if dip_depth is not None else None,
            "dip_reasons": dip_reasons,
            "fields": {k: (round(v, 4) if isinstance(v, float) else v)
                       for k, v in f.items()},
        }
        time.sleep(0.4)

    payload = {"date": stamp, "sectors": SECTORS, "results": results}

    def _clean(o):
        if isinstance(o, float) and o != o:
            return None
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o

    (BASE / "reports" / f"stock-{stamp}.json").write_text(
        json.dumps(_clean(payload), ensure_ascii=False, indent=2))

    L = [f"# 正股小额买入 + 基本面快照 {stamp}",
         "", "（Yahoo 基本面数据，仅供参考，不构成买卖建议）",
         "", "## 抄底评级 A/B（技术形态×基本面，机械打分）", ""]
    ok = [(t, r) for t, r in results.items() if r.get("ok")]
    dip = [(t, r) for t, r in ok if r.get("dip_rating") in ("A", "B")]
    dip.sort(key=lambda x: x[1]["dip_score"] or 0, reverse=True)
    for t, r in dip:
        L.append(
            f"- **{t}** 抄底{r['dip_rating']}({r['dip_score']}分,{RATING_LABEL[r['dip_rating']]})｜"
            f"${r['price']}｜回调{r['dip_depth']}｜勾选{r['checks_pass']}/5")
    L += ["", "## 按现价排序（超低投资视角：1股成本）", ""]
    for t, r in sorted(ok, key=lambda x: x[1]["price"] or 1e18):
        f = r["fields"]
        L.append(
            f"- **{t}** ${r['price']}｜抄底{r['dip_rating']}({r['dip_score']})｜"
            f"$100可买{r['per_100']}股｜"
            f"市值{f['marketCap']}｜TTM P/E {f['trailingPE']}｜"
            f"PEG {f['pegRatio']}｜营收增长{f['revenueGrowth']}｜"
            f"目标价隐含{r['upside']}｜勾选{r['checks_pass']}/5")
    (BASE / "reports" / f"stock-{stamp}.md").write_text("\n".join(L))
    print(f"stock done: {len(ok)}/{len(results)} ok")


if __name__ == "__main__":
    main()
