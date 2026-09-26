#!/usr/bin/env python3
"""
多到期期权链抓取（v0.2）
到期：2027-01 / 2027-03 / 2027-06 / 2027-09 / 2027-12 / 2028-01
  （每月取最接近18号的到期，即标准月度期权）
每个到期取 OTM call 六档：moneyness 105% / 110% / 115% / 120% / 125% / 130%
  （+5% 步长，strike/现价），列头直接显示实际行权价：
  strike、IV、last/bid/ask/mid、OI、volume
RV20 / RV60 一并显示，便于 implied vs realized 对比。
数据来自 Yahoo 免费行情，仅供参考，不构成买卖建议。
"""
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan import all_tickers, fetch, SECTORS  # noqa: E402

BASE = Path(__file__).resolve().parent
EXPIRY_PREFIXES = ["2027-01", "2027-03", "2027-06", "2027-09", "2027-12", "2028-01"]
MONEYNESS_TARGETS = [1.05, 1.10, 1.15, 1.20, 1.25, 1.30]


def _num(x, nd=2):
    """NaN-safe float，失败/NaN 返回 None。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return round(v, nd)


def _int(x):
    v = _num(x, 0)
    return int(v) if v is not None else 0


def clean(o):
    """递归把 NaN 换成 None，保证 JSON 合法。"""
    if isinstance(o, float) and o != o:
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    return o


def sector_of(ticker):
    for sec, ts in SECTORS.items():
        if ticker in ts:
            return sec
    return ""


def pick_monthly(exps, prefix):
    """取该月最接近18号的到期（月度期权通常是第三个周五，落在15~21号）。"""
    cands = [e for e in exps if e.startswith(prefix)]
    if not cands:
        return None
    return min(cands, key=lambda e: abs(int(e.split("-")[2]) - 18))


def fetch_calls(ticker, exp):
    """抓取某到期的 call 链，返回清洗后的 DataFrame，失败返回 None。"""
    for attempt in range(3):
        try:
            calls = yf.Ticker(ticker).option_chain(exp).calls
            break
        except Exception as e:
            if attempt == 2:
                print(f"[warn] {ticker} {exp} 期权链失败: {e}", file=sys.stderr)
                return None
            time.sleep(2)
    calls = calls.copy()
    calls["strike"] = pd.to_numeric(calls["strike"], errors="coerce")
    calls = calls[calls["strike"].notna()]
    return calls if not calls.empty else None


def row_of(calls, strike):
    """取最接近目标行权价的一档，格式化为 dict。"""
    row = calls.iloc[((calls["strike"] - strike).abs()).argsort()[:1]].iloc[0]
    bid = _num(row.get("bid"), 2) or 0
    ask = _num(row.get("ask"), 2) or 0
    last = _num(row.get("lastPrice"), 2) or 0
    mid = round((bid + ask) / 2, 2) if (bid and ask) else last
    return {
        "strike": _num(row["strike"], 1),
        "iv": _num(row.get("impliedVolatility"), 4),
        "last": last,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "oi": _int(row.get("openInterest")),
        "volume": _int(row.get("volume")),
    }


def main():
    stamp = datetime.now().astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    data = {}
    tickers = all_tickers()
    for i, t in enumerate(tickers):
        df = fetch(t)
        if df is None or df.empty:
            data[t] = {"error": "行情下载失败"}
            continue
        spot = float(df["Close"].iloc[-1])
        rets = np.log(df["Close"] / df["Close"].shift(1)).dropna()
        rv20 = _num(rets.iloc[-20:].std() * np.sqrt(252), 4) if len(rets) >= 20 else None
        rv60 = _num(rets.iloc[-60:].std() * np.sqrt(252), 4) if len(rets) >= 60 else None
        entry = {"sector": sector_of(t), "spot": _num(spot, 2),
                 "rv20": rv20, "rv60": rv60, "chains": {}}
        try:
            exps = list(yf.Ticker(t).options or [])
        except Exception as e:
            entry["error"] = f"到期日获取失败: {e}"
            data[t] = entry
            continue
        ladder = None  # [(moneyness_label, strike)]，以首个成功到期的实际行权价为准
        for px in EXPIRY_PREFIXES:
            exp = pick_monthly(exps, px)
            if not exp:
                entry["chains"][px] = {"error": "无该月到期"}
                continue
            calls = fetch_calls(t, exp)
            if calls is None:
                entry["chains"][px] = {"expiry": exp, "error": "期权链获取失败"}
                continue
            if ladder is None:
                ladder = []
                for m in MONEYNESS_TARGETS:
                    tgt = spot * m
                    st = float(calls.iloc[((calls["strike"] - tgt).abs())
                                          .argsort()[:1]].iloc[0]["strike"])
                    ladder.append((f"{round(m * 100)}%", st))
                entry["ladder"] = [{"moneyness": k, "strike": s}
                                   for k, s in ladder]
            entry["chains"][px] = {"expiry": exp}
            for k, st in ladder:
                entry["chains"][px][k] = row_of(calls, st)
            time.sleep(0.4)
        data[t] = entry
        print(f"[{i + 1}/{len(tickers)}] {t} done", file=sys.stderr)

    (BASE / "reports" / f"chains-{stamp}.json").write_text(
        json.dumps(clean(data), ensure_ascii=False, indent=2))

    L = [f"# 多到期期权链 {stamp}",
         "",
         "到期：2027-01 / 03 / 06 / 09 / 12、2028-01（标准月度到期）｜"
         "OTM call 按现价 +5% 步长取 105%~130% 六档，列头为实际行权价｜"
         "IV = 该档 call 的隐含波动率",
         "（Yahoo 免费数据，仅供参考，不构成买卖建议）", ""]
    for t in tickers:
        e = data[t]
        if "error" in e and "chains" not in e:
            L += [f"## {t}", "", f"- {e['error']}", ""]
            continue
        rv = f"RV20 {e['rv20'] * 100:.1f}%｜RV60 {e['rv60'] * 100:.1f}%" \
            if e["rv20"] and e["rv60"] else "RV缺失"
        ladder = e.get("ladder") or []
        keys = [s["moneyness"] for s in ladder] if ladder else \
            [f"{round(m * 100)}%" for m in MONEYNESS_TARGETS]
        hdr = " | ".join(f"${s['strike']:.1f}" for s in ladder) if ladder else \
            " | ".join(keys)
        L += [f"## {t}（{e['sector']}）现价 ${e['spot']}｜{rv}", ""]
        if ladder:
            L.append("行权价对应 moneyness：" +
                     " / ".join(f"${s['strike']:.1f}≈{s['moneyness']}"
                                for s in ladder))
            L.append("")
        L += [f"| 到期 | {hdr} |",
              "|" + "---|" * (len(keys) + 1)]
        for px in EXPIRY_PREFIXES:
            c = e["chains"].get(px, {})
            if keys[0] not in c:
                L.append(f"| {px} |" + " — |" * len(keys))
                continue

            def cell(k):
                d = c[k]
                ivs = f"IV {d['iv'] * 100:.1f}%" if d["iv"] else "IV —"
                return f"{ivs}｜mid ${d['mid']:.2f}｜OI {d['oi']}"
            L.append(f"| {c.get('expiry', px)} | " +
                     " | ".join(cell(k) for k in keys) + " |")
        L.append("")
    md = "\n".join(L)
    (BASE / "reports" / f"chains-{stamp}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
