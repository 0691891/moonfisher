#!/usr/bin/env python3
"""
入场建议（entry guidance）：基于 scan 输出的机械规则，不做主观判断。
正股建议：买入 / 小批建仓 / 观察（附依据）
LEAP call 推荐：仅在正股建议为买入/小批建仓时给出，口径与回测一致（~1年期 ATM call）。
  IV 缺失或异常（<0.05）→ 暂不推荐；IV/RV > 1.5 → IV偏贵，暂不推荐。
输出：reports/entry-YYYY-MM-DD.json + entry-YYYY-MM-DD.md，
      并把"入场建议"节写入 scan-YYYY-MM-DD.md（幂等）。
技术筛选，仅供参考，不构成买卖建议。
"""
import glob
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

BASE = Path(__file__).resolve().parent
REP = BASE / "reports"

BUY_SIGNALS = ("一买", "二买", "三买")
STOCK_ORDER = {"买入": 0, "小批建仓": 1, "观察": 2}


def latest(prefix):
    files = [f for f in glob.glob(str(REP / (prefix + "-*.json")))
             if "/_stale/" not in f]
    files.sort(key=lambda f: Path(f).stat().st_mtime, reverse=True)
    return json.loads(Path(files[0]).read_text()) if files else {}


def guidance(t, r):
    d = r.get("detail") or {}
    rating = r.get("rating") or "?"
    sig = d.get("chan_signal")
    beichi = d.get("chan_beichi") or ""
    rsi = d.get("rsi")
    iv = r.get("iv")
    iv_rv = r.get("iv_rv")
    iv_exp = r.get("iv_exp")
    close = d.get("close")

    buy_sig = sig in BUY_SIGNALS or r.get("chan_resonance") or r.get("rating_upgraded")
    bearish = (sig == "一卖") or ("顶背驰" in beichi)
    overbought = rsi is not None and rsi >= 75
    iv_bad = iv is None or iv < 0.05

    # ---- 正股建议 ----
    if rating == "?":
        stock, why = "观察", "数据缺失"
    elif bearish:
        stock, why = "观察", "等待回调（缠论一卖/顶背驰）"
    elif rating == "S":
        stock, why = "买入", "形态全过且IV不贵"
    elif rating == "A":
        if buy_sig:
            stock, why = "买入", "形态全过+缠论买点确认"
        else:
            stock, why = "小批建仓", "形态全过，缺精确买点"
    elif rating == "B":
        if buy_sig:
            stock, why = "小批建仓", "观察名单+缠论买点"
        else:
            stock, why = "观察", "观察名单，缺入场形态"
    elif rating == "C":
        stock, why = "观察", "趋势完好，缺入场形态"
    else:
        stock, why = "观察", "趋势走弱，不入场"
    if stock == "买入" and overbought:
        stock, why = "小批建仓", why + "；RSI超买，分批入场"

    # ---- LEAP call 推荐 ----
    leap, leap_why = "—", ""
    if stock in ("买入", "小批建仓"):
        if iv_bad:
            leap, leap_why = "暂不推荐", "IV数据缺失/异常"
        elif iv_rv is not None and iv_rv > 1.5:
            leap, leap_why = "暂不推荐", "IV偏贵（IV/RV %.2f）" % iv_rv
        else:
            exp = iv_exp or "约1年期"
            leap = "%s 到期｜strike≈$%s（平值）" % (exp, close)
            leap_why = "约1年期ATM call，与回测口径一致"
    return {"ticker": t, "rating": rating, "stock": stock, "stock_why": why,
            "leap": leap, "leap_why": leap_why,
            "iv": iv, "iv_rv": iv_rv, "close": close}


def main():
    stamp = datetime.now().astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    scan = latest("scan")
    results = scan.get("results") or {}
    rows = [guidance(t, results[t]) for t in results]
    rows.sort(key=lambda r: (STOCK_ORDER.get(r["stock"], 9), r["ticker"]))

    (REP / ("entry-%s.json" % stamp)).write_text(
        json.dumps({"date": stamp, "rows": rows}, ensure_ascii=False, indent=2))

    L = ["# 入场建议 %s" % stamp, "",
         "规则：买入=形态全过+IV不贵（S）或缠论买点确认（A）；小批建仓=缺精确买点 / RSI≥75超买分批 / B+缠论买点；",
         "观察=缺入场形态 / 趋势走弱 / 缠论一卖或顶背驰等回调 / 数据缺失。",
         "LEAP口径：约1年期ATM call（与回测一致）；IV缺失或异常（<5%）、IV/RV>1.5 时暂不推荐。",
         "（机械规则输出，技术筛选，仅供参考，不构成买卖建议）", "",
         "| Ticker | 评级 | 正股建议 | LEAP call 推荐 | 依据 |",
         "|---|---|---|---|---|"]
    for r in rows:
        why = r["stock_why"]
        if r["leap_why"] and r["leap"] != "—":
            why += "｜LEAP：" + r["leap_why"]
        L.append("| %s | %s | **%s** | %s | %s |"
                 % (r["ticker"], r["rating"], r["stock"], r["leap"], why))
    md = "\n".join(L) + "\n"
    (REP / ("entry-%s.md" % stamp)).write_text(md)

    # ---- 写入 scan 报告（幂等）----
    scan_md = REP / ("scan-%s.md" % stamp)
    if scan_md.exists():
        txt = scan_md.read_text()
        if "## 入场建议" in txt:
            txt = txt.split("## 入场建议")[0].rstrip() + "\n"
        scan_md.write_text(txt + "\n## 入场建议（entry guidance）\n\n" + md)

    n_buy = sum(1 for r in rows if r["stock"] == "买入")
    n_small = sum(1 for r in rows if r["stock"] == "小批建仓")
    print("entry %s: 买入 %d / 小批建仓 %d / 观察 %d"
          % (stamp, n_buy, n_small, len(rows) - n_buy - n_small))
    print(md)


if __name__ == "__main__":
    main()
