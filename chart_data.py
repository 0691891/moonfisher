#!/usr/bin/env python3
"""多周期缠论图表数据：Yahoo 批量抓取 -> 指标 -> 缠论全结构 -> charts/<T>_<tf>.json。

周期：1d(2y) / 1wk(5y) / 5m,15m,30m,1h(60d) / 4h(由1h重采样)。
JSON 供 dashboard.html「缠论图表」页签按需加载。
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

BASE = Path(__file__).resolve().parent
OUT = BASE / "charts"
sys.path.insert(0, str(BASE))
import chan
from scan import all_tickers

# (tf名, yf interval, yf period, 是否重采样)
TFS = [
    ("1d", "1d", "2y", False),
    ("1wk", "1wk", "5y", False),
    ("5m", "5m", "60d", False),
    ("15m", "15m", "60d", False),
    ("30m", "30m", "60d", False),
    ("1h", "1h", "60d", False),
    ("4h", "1h", "60d", True),
]

BUY = {"一买": "buy", "二买": "buy", "三买": "buy"}
SELL = {"一卖": "sell", "二卖": "sell", "三卖": "sell"}


def add_ind(df):
    df = df.copy()
    df["sma20"] = df["Close"].rolling(20).mean()
    df["sma50"] = df["Close"].rolling(50).mean()
    macd = (df["Close"].ewm(span=12, adjust=False).mean()
            - df["Close"].ewm(span=26, adjust=False).mean())
    df["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
    return df


def to_ts(idx):
    v = pd.Timestamp(idx)
    if v.tzinfo is None:
        v = v.tz_localize("America/New_York")
    return int(v.tz_convert("UTC").timestamp())


def signal_at(df, end_idx):
    """在第 end_idx 根 K 线处（某笔终点）重算缠论信号。"""
    sub = df.iloc[:end_idx + 1]
    fr = chan.find_fractals(sub)
    st = chan.build_strokes(fr)
    pv = chan.find_zhongshu(st)
    be = chan.detect_beichi(sub, st)
    return chan.detect_signal(sub, st, pv, be)


def build_one(ticker, tf, df):
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 40:
        return None
    df = add_ind(df)
    sub = df[["Open", "High", "Low", "Close", "macd_hist"]].dropna()
    if len(sub) < 40:
        return None
    # 用 sub 的整数位置做缠论，再映射回时间戳
    times = [to_ts(t) for t in sub.index]
    n = len(sub)
    fractals = chan.find_fractals(sub)
    strokes = chan.build_strokes(fractals)
    pivots = chan.find_zhongshu(strokes)
    beichi = chan.detect_beichi(sub, strokes)
    sig_now = chan.detect_signal(sub, strokes, pivots, beichi)

    candles = [{"t": times[i],
                "o": round(float(sub["Open"].iloc[i]), 2),
                "h": round(float(sub["High"].iloc[i]), 2),
                "l": round(float(sub["Low"].iloc[i]), 2),
                "c": round(float(sub["Close"].iloc[i]), 2)}
               for i in range(n)]

    # 笔：端点折线
    pens = []
    if strokes:
        pts = [(strokes[0]["from"], strokes[0]["start_price"])]
        for s in strokes:
            pts.append((s["to"], s["end_price"]))
        pens = [{"t0": times[a], "p0": round(float(pa), 2),
                 "t1": times[b], "p1": round(float(pb), 2),
                 "dir": s["dir"]}
                for (a, pa), (b, pb), s in
                zip(pts[:-1], pts[1:], strokes)]

    zhongshu = [{"t0": times[p["start"]], "t1": times[p["end"]],
                 "zg": round(float(p["zg"]), 2), "zd": round(float(p["zd"]), 2),
                 "n_pens": p["n_pens"]} for p in pivots[-10:]]

    fractals_j = [{"t": times[i], "p": round(float(pr), 2), "kind": k}
                  for i, k, pr in fractals[-80:]]

    # 历史买卖点：在每笔终点重算（只看最近 40 笔）
    signals = []
    for s in strokes[-40:]:
        try:
            sig = signal_at(sub, s["to"])
        except Exception:
            sig = None
        if sig:
            side = "buy" if sig in BUY else ("sell" if sig in SELL else None)
            signals.append({"t": times[s["to"]],
                            "p": round(float(s["end_price"]), 2),
                            "sig": sig, "side": side})

    # 均线（有值的部分）
    sma20 = [{"t": times[i], "v": round(float(v), 2)}
             for i, v in enumerate(df["sma20"].reindex(sub.index))
             if pd.notna(v)]
    sma50 = [{"t": times[i], "v": round(float(v), 2)}
             for i, v in enumerate(df["sma50"].reindex(sub.index))
             if pd.notna(v)]

    # 海底捞月（仅日线）：近90日高点 -> 之后低点 -> 收复
    dip = None
    if tf == "1d" and n >= 90:
        tail = sub.iloc[-90:]
        hi_i = int(tail["High"].values.argmax())
        hi = float(tail["High"].iloc[hi_i])
        hi_t = times[n - 90 + hi_i]
        base = hi_i + 1 if hi_i + 1 < len(tail) else hi_i
        after = tail.iloc[base:]
        lo = float(after["Low"].min())
        lo_pos = int(after["Low"].values.argmin())
        lo_t = times[n - 90 + base + lo_pos]
        close = float(sub["Close"].iloc[-1])
        retr = (close - lo) / (hi - lo) if hi > lo else 0
        dip = {"high_t": hi_t, "high": round(hi, 2),
               "low_t": lo_t, "low": round(lo, 2),
               "retrace_pct": round(retr * 100, 1)}

    return {
        "ticker": ticker, "tf": tf,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_bars": n,
        "candles": candles, "pens": pens, "zhongshu": zhongshu,
        "fractals": fractals_j, "signals": signals,
        "sma20": sma20, "sma50": sma50, "dip": dip,
        "last": {"close": round(float(sub["Close"].iloc[-1]), 2),
                 "signal": sig_now, "beichi": beichi,
                 "pen_dir": strokes[-1]["dir"] if strokes else None,
                 "n_pens": len(strokes)},
    }


def resample_4h(df):
    agg = {"Open": "first", "High": "max", "Low": "min",
           "Close": "last", "Volume": "sum"}
    out = df.resample("4h", origin="start_day").agg(agg).dropna()
    return out[out["Volume"] > 0]


def main():
    tickers = all_tickers()
    OUT.mkdir(exist_ok=True)
    total = 0
    for tf, interval, period, do_rs in TFS:
        print(f"[{tf}] 下载 {interval}/{period} ...", flush=True)
        try:
            raw = yf.download(tickers, period=period, interval=interval,
                              progress=False, auto_adjust=True,
                              prepost=False, threads=True)
        except Exception as e:
            print(f"[{tf}] 下载失败: {e}")
            continue
        if raw.empty:
            print(f"[{tf}] 空数据，跳过")
            continue
        # 兼容单层/多层列
        for t in tickers:
            try:
                if isinstance(raw.columns, pd.MultiIndex):
                    df = pd.DataFrame({k: raw[(k, t)]
                                       for k in ("Open", "High", "Low",
                                                 "Close", "Volume")
                                       if (k, t) in raw.columns})
                else:
                    df = raw.copy()
                if df.empty or df["Close"].dropna().empty:
                    continue
                if do_rs:
                    df = resample_4h(df)
                payload = build_one(t, tf, df)
                if payload:
                    (OUT / f"{t}_{tf}.json").write_text(
                        json.dumps(payload, ensure_ascii=False,
                                   separators=(",", ":")))
                    total += 1
            except Exception as e:
                print(f"[{tf}] {t} 失败: {e}")
        time.sleep(1)
    print(f"done: {total} 个图表数据文件 -> {OUT}")


if __name__ == "__main__":
    main()
