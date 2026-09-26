#!/usr/bin/env python3
"""
海底捞月 LEAP 候选扫描器（v0.3，对接 TMT LEAP Scan v2.1）
数据源：Yahoo 免费行情（yfinance），日线 + 期权链
板块（v2.1 三条 dependency graph）：
  Core LEAP / 2× Radar / Time-to-Power / Agent Economy / Physical AI / 大宗商品
逻辑：
  1. 海底捞月形态（日线）= v2.1 的 Price Entry 确认
  2. 技术状态机（v2.1）：趋势完好 / 正常回调 / 修正观察 / 警告 / 趋势反转
     （20/50/200DMA + 量能 + RS vs QQQ；价格破20DMA不单独构成卖出信号）
  3. IV vs RV：Jan-2028（或最远）到期 ATM call IV，对比 20/60 日已实现波动率
  4. 评级：S=形态全过且IV不贵 / A=形态全过 / B=观察名单 / C=趋势完好 / D=趋势走弱
说明：ERV（共识预期修正速度）需要 FactSet/Bloomberg point-in-time 数据库，
     免费版暂缺；Thesis Score 来自你的 v2.1 基本面研究，本扫描只给 Entry + Trend。
输出：JSON + Markdown 报告。技术形态筛选结果，不构成买卖建议。
"""
import glob
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BASE = Path(__file__).resolve().parent

# 板块配置（v2.1：三条 dependency graph；同一 ticker 只归属一个 cluster）
SECTORS = {
    "Core LEAP":     ["GOOGL", "NVDA", "MSFT", "AMD", "META", "AVGO",
                      "AMZN", "ANET", "AAPL", "BABA"],
    "2× Radar":      ["MRVL", "TER", "COHR", "LITE", "CIEN", "MU"],
    "Time-to-Power": ["GEV", "PWR", "GNRC", "ETN", "VRT", "NVT",
                      "VICR", "CEG", "VST", "HUBB"],
    "Agent Economy": ["OKTA", "PANW", "CRWD", "NOW", "DDOG",
                      "SNOW", "MDB", "NET", "ESTC"],
    "Physical AI":   ["SYM", "TSLA", "IONQ"],
    # 大宗商品：用ETF做可交易代理（含期权链，可抓IV）；期货另有 GC=F / CL=F
    "大宗商品":        ["GLD", "USO"],
}
# 排除名单：v2.1 框架明确排除；CYBR 在可交易前需先核验 corporate-action/listing 状态
EXCLUDED = ["ORCL", "CRWV", "NBIS", "IREN", "INTC"]

CFG = dict(lookback=20, dip_min=0.05, dip_max=0.15,
           retrace_min=0.50, vol_mult=1.20, sma50_slope_n=10)


def all_tickers():
    seen, out = set(), []
    for ts in SECTORS.values():
        for t in ts:
            if t not in seen and t not in EXCLUDED:
                seen.add(t); out.append(t)
    return out


def fetch(ticker):
    try:
        df = yf.download(ticker, period="1y", interval="1d",
                         progress=False, auto_adjust=True)
    except Exception as e:
        print(f"[warn] {ticker} 行情下载失败: {e}", file=sys.stderr)
        return None
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def fetch_iv(ticker, spot):
    """抓 Jan-2028（无则取最远到期）ATM call 的平均 IV。返回 (iv, expiry)。"""
    try:
        tkr = yf.Ticker(ticker)
        exps = list(tkr.options or [])
    except Exception as e:
        print(f"[warn] {ticker} 期权到期日获取失败: {e}", file=sys.stderr)
        return None, None
    jan28 = [e for e in exps if e.startswith("2028-01")]
    exp = jan28[0] if jan28 else (exps[-1] if exps else None)
    if not exp:
        return None, None
    try:
        calls = tkr.option_chain(exp).calls
    except Exception as e:
        print(f"[warn] {ticker} 期权链获取失败({exp}): {e}", file=sys.stderr)
        return None, None
    calls = calls[calls["impliedVolatility"] > 0].copy()
    if calls.empty:
        return None, None
    calls["dist"] = (calls["strike"] - spot).abs()
    atm = calls.nsmallest(5, "dist")
    return float(atm["impliedVolatility"].mean()), exp


def add_indicators(df):
    df = df.copy()
    df["sma20"] = df["Close"].rolling(20).mean()
    df["sma50"] = df["Close"].rolling(50).mean()
    df["sma200"] = df["Close"].rolling(200).mean()
    df["vol20"] = df["Volume"].rolling(20).mean()
    # ATR(14)
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(),
                    (l - c.shift()).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    d = df["Close"].diff()
    ag = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    al = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + ag / al.replace(0, np.nan))
    macd = (df["Close"].ewm(span=12, adjust=False).mean()
            - df["Close"].ewm(span=26, adjust=False).mean())
    df["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    return df


def tech_state(close, sma20, sma50, sma200, s50_up, s200_up):
    """v2.1 技术状态机（机械化，不用量模型"感觉"）。
    价格破20DMA不单独构成卖出信号，创新高不单独构成"贵"。"""
    if sma200 and close < sma200:
        return "趋势反转"
    if close < sma50:
        return "修正观察" if s200_up else "趋势反转"
    if close < sma20:
        return "正常回调" if s50_up else "警告"
    return "趋势完好"


def rs_ratio(s, q, n):
    """相对强度：ticker n日涨幅 / QQQ n日涨幅 - 1。"""
    if s is None or q is None or len(s) < n + 1 or len(q) < n + 1:
        return None
    return float((s.iloc[-1] / s.iloc[-(n + 1)])
                 / (q.iloc[-1] / q.iloc[-(n + 1)]) - 1)


def detect(df):
    out = {"ok": False, "reason": "", "score": 0, "detail": {}}
    if len(df) < 210:
        out["reason"] = "数据不足210个交易日（需200DMA）"
        return out
    df = add_indicators(df)
    # 缠论用长序列（不需要 sma200，只 drop 自身所需列的 NaN）
    try:
        import chan as chan_mod
        ch = chan_mod.analyze(df[["High", "Low", "Close", "macd_hist"]].dropna())
    except Exception as e:
        print(f"[warn] 缠论计算失败: {e}", file=sys.stderr)
        ch = {"signal": None, "beichi": None, "pen_dir": None,
              "zhongshu": None, "n_pens": 0, "n_fractals": 0}
    df = df.dropna()
    if len(df) < 35:
        out["reason"] = "指标计算后数据不足"
        return out
    last = df.iloc[-1]
    close = float(last["Close"])
    sma20, sma50 = float(last["sma20"]), float(last["sma50"])
    sma200 = float(last["sma200"])
    sma50_old = float(df["sma50"].iloc[-1 - CFG["sma50_slope_n"]])
    sma200_old = float(df["sma200"].iloc[-1 - CFG["sma50_slope_n"]])
    s50_up = sma50 > sma50_old
    s200_up = sma200 > sma200_old
    atr_pct = float(last["atr"]) / close * 100 if last["atr"] else None

    state = tech_state(close, sma20, sma50, sma200, s50_up, s200_up)

    vol_ratio = float(df["Volume"].iloc[-3:].mean()) / float(last["vol20"])
    vol_state = "放量" if vol_ratio > 1.5 else ("缩量" if vol_ratio < 0.8 else "量能正常")

    trend = close > sma50 and sma50 > sma50_old and sma20 > sma50

    win = df.iloc[-CFG["lookback"]:]
    hi_idx = win["High"].idxmax()
    hi = float(win.loc[hi_idx, "High"])
    after_hi = win.loc[hi_idx:]
    lo = float(after_hi["Low"].min())
    dip_pct = (hi - lo) / hi if hi else 0
    dip_ok = CFG["dip_min"] <= dip_pct <= CFG["dip_max"]

    seg = win.loc[hi_idx:]
    ma_intact = bool(((seg["Close"] > seg["sma20"]) &
                      (seg["Close"] > seg["sma50"])).all())

    retrace = (close - lo) / (hi - lo) if hi > lo else 0
    vol_recent = float(win["Volume"].iloc[-3:].mean())
    recovery = (retrace >= CFG["retrace_min"] and close > sma20
                and vol_recent > float(last["vol20"]) * CFG["vol_mult"])

    rsi_now, rsi_old = float(last["rsi"]), float(df["rsi"].iloc[-4])
    h_now, h_old = float(last["macd_hist"]), float(df["macd_hist"].iloc[-2])
    momentum = (rsi_now > rsi_old and rsi_now > 40) or (h_now > 0 and h_now > h_old)

    score = (25 if trend else 0) + (20 if dip_ok else 0) + \
            (20 if ma_intact else 0) + (20 if recovery else 0) + \
            (15 if momentum else 0)
    out.update({"score": score, "detail": {
        "close": round(close, 2), "sma20": round(sma20, 2),
        "sma50": round(sma50, 2), "sma200": round(sma200, 2),
        "sma50_up": s50_up, "sma200_up": s200_up,
        "tech_state": state, "vol_state": vol_state,
        "atr_pct": round(atr_pct, 1) if atr_pct else None,
        "dip_pct": round(dip_pct * 100, 1),
        "dip_high": round(hi, 2), "dip_low": round(lo, 2),
        "retrace_pct": round(retrace * 100, 1), "rsi": round(rsi_now, 1),
        "trend": trend, "dip_ok": dip_ok, "ma_intact": ma_intact,
        "recovery": recovery, "momentum": momentum}})
    # ---- 缠论结合层（确认层，不改变 100 分制）----
    d = out["detail"]
    d["chan_signal"] = ch.get("signal")
    d["chan_beichi"] = ch.get("beichi")
    d["chan_pen"] = ch.get("pen_dir")
    d["chan_zhongshu"] = ch.get("zhongshu")
    # 海底低点是否为已确认的底分型（±5天内、±2%）
    d["dip_fractal_ok"] = False
    try:
        lo_date = after_hi["Low"].idxmin()
        for b in ch.get("bottoms") or []:
            bd = pd.Timestamp(b["date"])
            if abs((bd - lo_date).days) <= 5 and abs(b["price"] - lo) / lo < 0.02:
                d["dip_fractal_ok"] = True
                break
    except Exception:
        pass
    checks = [trend, dip_ok, ma_intact, recovery, momentum]
    out["ok"] = all(checks)
    out["watch"] = trend and dip_ok and ma_intact and not out["ok"]
    if not out["ok"]:
        missing = [n for n, c in zip(
            ["趋势", "海底形态", "均线完好", "捞月反弹", "动量"], checks) if not c]
        out["reason"] = "未通过: " + "、".join(missing)
    return out


def rate(det, iv_rv, iv=None):
    """S=形态全过且IV不贵 / A=形态全过 / B=观察 / C=趋势完好 / D=趋势走弱
    IV 缺失或异常低（<0.05，多为数据源问题）时不给 S，防止误判。"""
    d = det.get("detail") or {}
    if not d.get("close"):
        return "?"
    if det["ok"]:
        iv_ok = iv_rv is not None and iv_rv <= 1.1 and (iv or 0) >= 0.05
        return "S" if iv_ok else "A"
    if det.get("watch"):
        return "B"
    if d.get("trend"):
        return "C"
    return "D"


def main():
    stamp = datetime.now().astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")  # 美东日期，防 worker 时区错乱
    qqq = fetch("QQQ")
    qqq_close = qqq["Close"] if qqq is not None else None
    # 上一份扫描：算形态分变化（对应 v2.1 的周一 re-rating 对比）
    prev_scores, prev_date = {}, None
    for f in sorted(glob.glob(str(BASE / "reports" / "scan-*.json")), reverse=True):
        if "_stale" in f:
            continue
        d = Path(f).stem.replace("scan-", "")
        if d < stamp:
            try:
                pj = json.loads(Path(f).read_text())
                prev_scores = {t: r.get("score")
                               for t, r in pj.get("results", {}).items()}
                prev_date = d
            except Exception:
                pass
            break
    results = {}
    for t in all_tickers():
        df = fetch(t)
        if df is None or df.empty:
            results[t] = {"ok": False, "reason": "行情下载失败",
                          "rating": "?", "iv": None,
                          "dq_flag": True, "dq_issues": ["行情下载失败"]}
            continue
        det = detect(df)
        spot = det["detail"].get("close")
        iv, exp = fetch_iv(t, spot) if spot else (None, None)
        rets = np.log(df["Close"] / df["Close"].shift(1)).dropna()
        rv20 = float(rets.iloc[-20:].std() * np.sqrt(252)) if len(rets) >= 20 else None
        rv60 = float(rets.iloc[-60:].std() * np.sqrt(252)) if len(rets) >= 60 else None
        iv_rv = (iv / rv60) if (iv and rv60) else None
        # 数据质量旗标：IV/RV 缺失或异常（与 rate() 的保守阈值一致）
        dq_issues = []
        if iv is None:
            dq_issues.append("IV缺失")
        elif iv < 0.05:
            dq_issues.append("IV异常(<5%)")
        if rv20 is None:
            dq_issues.append("RV20缺失")
        if rv60 is None:
            dq_issues.append("RV60缺失")
        rs20 = rs_ratio(df["Close"], qqq_close, 20)
        rs60 = rs_ratio(df["Close"], qqq_close, 60)
        chg = None
        ps = prev_scores.get(t)
        if ps is not None and det.get("score") is not None:
            chg = det["score"] - ps
        # ---- 缠论结合：共振判定 ----
        rating = rate(det, iv_rv, iv)
        d0 = det.get("detail") or {}
        sig = d0.get("chan_signal")
        resonance = bool(sig in ("一买", "二买", "三买")
                         and (det.get("ok") or det.get("watch")))
        upgraded = False
        if rating == "B" and resonance:
            # B=趋势/形态/均线都过、只差反弹确认；缠论买点即精确入场确认 -> A
            rating = "A"
            upgraded = True
        results[t] = {**det, "rating": rating,
                      "chan_resonance": resonance,
                      "rating_upgraded": upgraded,
                      "iv": round(iv, 3) if iv else None,
                      "iv_exp": exp,
                      "rv20": round(rv20, 3) if rv20 else None,
                      "rv60": round(rv60, 3) if rv60 else None,
                      "iv_rv": round(iv_rv, 2) if iv_rv else None,
                      "rs20": round(rs20 * 100, 1) if rs20 is not None else None,
                      "rs60": round(rs60 * 100, 1) if rs60 is not None else None,
                      "score_chg": chg,
                      # ---- 数据质量旗标（永久护栏）：IV/RV 缺失或异常必须显式标记，
                      #      不得静默跳过；缺 IV 的行按保守规则处理（不得 S，见 rate()）
                      "dq_flag": bool(dq_issues),
                      "dq_issues": dq_issues}

    payload = {"date": stamp, "config": CFG, "sectors": SECTORS,
               "excluded": EXCLUDED, "results": results,
               "prev_date": prev_date}

    def _clean(o):
        if isinstance(o, float) and o != o:
            return None
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o

    (BASE / "reports" / f"scan-{stamp}.json").write_text(
        json.dumps(_clean(payload), ensure_ascii=False, indent=2))

    L = [f"# 海底捞月 + IV/RV 扫描 {stamp}（TMT LEAP v2.1）",
         "", "（技术形态筛选，仅供参考，不构成买卖建议）",
         "", "评级：S=形态全过且IV不贵 / A=形态全过 / B=观察 / C=趋势完好 / D=趋势走弱",
         "状态机：趋势完好 / 正常回调 / 修正观察 / 警告 / 趋势反转｜RS=相对QQQ强度",
         "缠论（简化版：分型→笔→中枢→背驰→买卖点）：一买=下跌笔底分型+底背驰 / 二买=回踩不破前低 / 三买=突破中枢回踩不进；✦共振=海底捞月通过+缠论买点（B+买点→A）",
         (f"形态分变化 vs {prev_date}" if prev_date else "无历史评分对比"), ""]
    order = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4, "?": 5}
    for sec, ts in SECTORS.items():
        L += [f"## {sec}", ""]
        for t in sorted(ts, key=lambda x: order.get(results[x]["rating"], 5)):
            r = results[t]
            if r["rating"] == "?":
                dq_m = ("｜⚠数据质量：" + "/".join(r.get("dq_issues") or "")
                        if r.get("dq_flag") else "")
                L.append(f"- {t}: {r['reason']}{dq_m}")
                continue
            d = r["detail"]
            dq_s = ("｜⚠数据质量：" + "/".join(r.get("dq_issues") or "")
                    if r.get("dq_flag") else "")
            ivs = (f"IV{round(r['iv'], 2)}"
                   if r["iv"] else "IV缺失")
            chg = r.get("score_chg")
            chg_s = (f"({'▲' if chg > 0 else '▼'}{abs(chg)})"
                     if chg else "")
            # 缠论结合展示
            chan_s = ""
            csig = d.get("chan_signal")
            if csig:
                chan_s = f"｜缠论{csig}"
                if d.get("chan_beichi"):
                    chan_s += f"·{d['chan_beichi']}"
                if r.get("chan_resonance"):
                    chan_s += "✦共振"
            if d.get("dip_fractal_ok"):
                chan_s += "｜底分型确认"
            if r.get("rating_upgraded"):
                chan_s += "（B→A缠论升级）"
            L.append(
                f"- **{t}** 评级{r['rating']} 形态分{r['score']}{chg_s}｜${d['close']} "
                f"｜{d.get('tech_state', '')} {d.get('vol_state', '')}｜"
                f"回调{d['dip_pct']}% 收复{d['retrace_pct']}%｜"
                f"20天线${d['sma20']} 50天线${d['sma50']} 200天线${d.get('sma200')}｜"
                f"RSI{d['rsi']} ATR{d.get('atr_pct')}%｜"
                f"RS20 {r['rs20']}% RS60 {r['rs60']}%｜"
                f"{ivs} RV20 {r['rv20']} RV60 {r['rv60']} IV/RV {r['iv_rv']}"
                + (f"（{r['iv_exp']}）" if r.get("iv_exp") else "")
                + chan_s + dq_s)
        L.append("")
    # ---- 数据质量汇总（永久护栏：缺失/异常必须显式列出）----
    flagged = {t: r for t, r in results.items() if r.get("dq_flag")}
    if flagged:
        L += ["## 数据质量告警（DQ flag）", "",
              "以下 ticker 存在 IV/RV 数据缺失或异常，已按保守规则处理（缺 IV 不得 S）。评级为技术筛选，仅供参考：", ""]
        for t in sorted(flagged):
            r = flagged[t]
            L.append("- **%s**（评级%s）：%s"
                     % (t, r["rating"], "、".join(r.get("dq_issues") or [])))
        L += [""]
    else:
        L += ["## 数据质量", "", "全部 ticker 的 IV/RV 数据完整，无缺失或异常。", ""]
    if EXCLUDED:
        L += ["## 排除名单（来自你的框架，不扫描）",
              "", ", ".join(EXCLUDED), ""]
    md = "\n".join(L)
    (BASE / "reports" / f"scan-{stamp}.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
