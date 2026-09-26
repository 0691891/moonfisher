#!/usr/bin/env python3
"""缠论简化版技术模块（与海底捞月结合）。
流程：分型 -> 笔 -> 中枢 -> 背驰 -> 买卖点。

简化说明（完整缠论含 K 线包含处理、严格线段划分，此处为可程序化的简化版）：
- 分型：标准 3 根 K 线分型；相邻同向分型保留更极值者
- 笔：异向分型、间隔 >= 5 根 K 线
- 中枢：连续 3 笔的高低点重叠区间 [ZD, ZG]；后续与之重叠的笔延伸中枢
- 背驰：相邻两同向笔，价格新低（高）但 MACD 柱面积缩小 -> 底背驰（顶背驰）
- 买卖点：一买=下跌笔底分型+底背驰；二买=回踩不破前低；三买=突破中枢回踩不进
"""


def find_fractals(df):
    """返回 [(idx, 'top'|'bottom', price)]，已合并相邻同向分型。"""
    highs = df["High"].values
    lows = df["Low"].values
    raw = []
    for i in range(1, len(df) - 1):
        if (highs[i] > highs[i - 1] and highs[i] > highs[i + 1]
                and lows[i] > lows[i - 1] and lows[i] > lows[i + 1]):
            raw.append((i, "top", float(highs[i])))
        elif (lows[i] < lows[i - 1] and lows[i] < lows[i + 1]
              and highs[i] < highs[i - 1] and highs[i] < highs[i + 1]):
            raw.append((i, "bottom", float(lows[i])))
    merged = []
    for idx, typ, price in raw:
        if merged and merged[-1][1] == typ:
            prev = merged[-1]
            if (typ == "top" and price > prev[2]) or \
               (typ == "bottom" and price < prev[2]):
                merged[-1] = (idx, typ, price)
        else:
            merged.append((idx, typ, price))
    return merged


def build_strokes(fractals):
    """由异向分型构笔。返回 [{'from','to','dir','high','low',...}]。"""
    strokes = []
    i = 0
    while i < len(fractals) - 1:
        a = fractals[i]
        j = i + 1
        while j < len(fractals) and fractals[j][1] == a[1]:
            j += 1
        if j >= len(fractals):
            break
        b = fractals[j]
        if b[0] - a[0] >= 5:
            strokes.append({
                "from": a[0], "to": b[0],
                "dir": "up" if b[1] == "top" else "down",
                "high": max(a[2], b[2]), "low": min(a[2], b[2]),
                "start_price": a[2], "end_price": b[2],
            })
            i = j
        else:
            i += 1  # 间隔不够，不成笔，继续找
    return strokes


def find_zhongshu(strokes):
    """三笔重叠 -> 中枢；后续重叠的笔延伸。返回 [{'zg','zd','start','end','n_pens'}]。"""
    pivots = []
    i = 0
    while i + 2 < len(strokes):
        s1, s2, s3 = strokes[i], strokes[i + 1], strokes[i + 2]
        zg = min(s1["high"], s2["high"], s3["high"])
        zd = max(s1["low"], s2["low"], s3["low"])
        if zd < zg:
            j = i + 3
            while j < len(strokes):
                s = strokes[j]
                if s["low"] < zg and s["high"] > zd:
                    j += 1
                else:
                    break
            pivots.append({"zg": zg, "zd": zd, "start": s1["from"],
                           "end": strokes[j - 1]["to"], "n_pens": j - i})
            i = j
        else:
            i += 1
    return pivots


def detect_beichi(df, strokes):
    """相邻两同向笔：价格新低但 MACD 柱面积缩小 -> 底背驰；反之顶背驰。"""
    if "macd_hist" not in df.columns:
        return None
    hist = df["macd_hist"]
    beichi = None
    downs = [s for s in strokes if s["dir"] == "down"]
    ups = [s for s in strokes if s["dir"] == "up"]
    if len(downs) >= 2:
        d1, d2 = downs[-2], downs[-1]
        a1 = float(hist.iloc[d1["from"]:d1["to"] + 1].sum())
        a2 = float(hist.iloc[d2["from"]:d2["to"] + 1].sum())
        if d2["low"] < d1["low"] and a2 > a1:
            beichi = "底背驰"
    if len(ups) >= 2:
        u1, u2 = ups[-2], ups[-1]
        a1 = float(hist.iloc[u1["from"]:u1["to"] + 1].sum())
        a2 = float(hist.iloc[u2["from"]:u2["to"] + 1].sum())
        if u2["high"] > u1["high"] and a2 < a1:
            beichi = "顶背驰" if beichi is None else beichi + "+顶背驰"
    return beichi


def detect_signal(df, strokes, pivots, beichi):
    """机械判定买卖点。只看当前结构：最后一笔终点须在最近 8 根 K 线内。"""
    if len(strokes) < 2:
        return None
    last = strokes[-1]
    n = len(df)
    if n - 1 - last["to"] > 8:
        return None
    zg = pivots[-1]["zg"] if pivots else None
    zd = pivots[-1]["zd"] if pivots else None

    # ---- 买点 ----
    if zg and len(strokes) >= 3 and last["dir"] == "up":
        prev = strokes[-2]
        broke = any(s["high"] > zg for s in strokes[-4:])
        if prev["dir"] == "down" and prev["low"] > zg and broke:
            return "三买"
    if len(strokes) >= 4 and last["dir"] == "up":
        a, b, c = strokes[-4], strokes[-3], strokes[-2]
        if a["dir"] == "down" and b["dir"] == "up" and c["dir"] == "down":
            if c["low"] >= a["low"] * 0.99:
                return "二买"
    if last["dir"] == "down" and beichi and "底背驰" in beichi:
        return "一买"
    # ---- 卖点 ----
    if zd and len(strokes) >= 3 and last["dir"] == "down":
        prev = strokes[-2]
        broke = any(s["low"] < zd for s in strokes[-4:])
        if prev["dir"] == "up" and prev["high"] < zd and broke:
            return "三卖"
    if len(strokes) >= 4 and last["dir"] == "down":
        a, b, c = strokes[-4], strokes[-3], strokes[-2]
        if a["dir"] == "up" and b["dir"] == "down" and c["dir"] == "up":
            if c["high"] <= a["high"] * 1.01:
                return "二卖"
    if last["dir"] == "up" and beichi and "顶背驰" in beichi:
        return "一卖"
    return None


def analyze(df):
    """主入口。df 需含 High/Low/Close/macd_hist。返回 JSON-safe dict。"""
    out = {"signal": None, "beichi": None, "pen_dir": None,
           "zhongshu": None, "n_pens": 0, "n_fractals": 0, "bottoms": []}
    if df is None or len(df) < 40 or "macd_hist" not in df.columns:
        return out
    fractals = find_fractals(df)
    strokes = build_strokes(fractals)
    out["n_fractals"] = len(fractals)
    out["n_pens"] = len(strokes)
    if strokes:
        out["pen_dir"] = strokes[-1]["dir"]
    # 最近 5 个底分型（日期+价格），供"海底低点是否为分型底"验证
    out["bottoms"] = [{"date": str(df.index[i].date()), "price": round(float(p), 2)}
                      for i, _, p in [f for f in fractals if f[1] == "bottom"][-5:]]
    pivots = find_zhongshu(strokes)
    if pivots:
        p = pivots[-1]
        out["zhongshu"] = {"zg": round(float(p["zg"]), 2),
                           "zd": round(float(p["zd"]), 2),
                           "n_pens": p["n_pens"]}
    beichi = detect_beichi(df, strokes)
    out["beichi"] = beichi
    out["signal"] = detect_signal(df, strokes, pivots, beichi)
    return out
