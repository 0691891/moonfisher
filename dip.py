#!/usr/bin/env python3
"""抄底评级：技术形态（对齐 scan.py 海底捞月框架）x 基本面的机械打分。

100分制（detail 字段来自 scan.py）：
  技术状态 35分：正常回调=35 / 修正观察=20 / 趋势完好=8 / 警告=5 / 趋势反转=0
  回调形态 25分：dip_ok（近20日高点回调 5%~15%）=25；
                回调 0%~22.5%（非理想但可接受）=10；无回调或超跌=0
  趋势保护 20分：trend（收盘>50日线且50日线向上且20日线>50日线）=20；
                收盘>50日线=10；收盘>200日线=5；200日线下=0
  基本面   20分：checks(0-5)/5 * 20
硬门槛：趋势反转→强制D；警告→最高C；回调超 22.5%（接飞刀区）→最高C。
评级：A>=75（抄底信号强）/ B>=60（可分批观察）/ C>=40（观望）/ D<40（不建议抄底）
"""


def rate_dip(detail, checks):
    reasons = []
    score = 0
    d = detail or {}
    ts = d.get("tech_state", "")

    ts_pts = {"正常回调": 35, "修正观察": 20, "趋势完好": 8,
              "警告": 5, "趋势反转": 0}
    p = ts_pts.get(ts, 0)
    score += p
    reasons.append("技术状态%s+%d" % (ts or "未知", p))

    dip_pct = d.get("dip_pct")  # 百分比数值，如 8.5 表示 8.5%
    dp_frac = dip_pct / 100 if dip_pct is not None else None
    if d.get("dip_ok"):
        dp, msg = 25, "回调%.1f%%（理想区5%%~15%%）+25" % dip_pct
    elif dp_frac is not None and 0 < dp_frac <= 0.225:
        dp, msg = 10, "回调%.1f%%（非理想区）+10" % dip_pct
    else:
        dp, msg = 0, "无回调或超跌+0"
    score += dp
    reasons.append(msg)

    close, sma50, sma200 = d.get("close"), d.get("sma50"), d.get("sma200")
    if d.get("trend"):
        tp, msg = 20, "均线多头完好+20"
    elif close and sma50 and close > sma50:
        tp, msg = 10, "站上50日线+10"
    elif close and sma200 and close > sma200:
        tp, msg = 5, "50日线下、200日线上+5"
    else:
        tp, msg = 0, "200日线下或缺数据+0"
    score += tp
    reasons.append(msg)

    f = round((checks or 0) / 5 * 20)
    score += f
    reasons.append("基本面勾选%d/5+%d" % (checks or 0, f))

    # 回调深度（相对20日线），供展示
    sma20 = d.get("sma20")
    depth = ((close - sma20) / sma20
             if (close and sma20) else None)

    rating = ("A" if score >= 75 else "B" if score >= 60
              else "C" if score >= 40 else "D")
    if ts == "趋势反转":
        rating = "D"
        reasons.append("趋势反转→强制D")
    elif ts == "警告" or (dp_frac is not None and dp_frac > 0.225):
        if rating in ("A", "B"):
            rating = "C"
        reasons.append("警告/超跌→最高C")
    return score, rating, depth, reasons


RATING_LABEL = {"A": "抄底信号强", "B": "可分批观察", "C": "观望", "D": "不建议抄底"}
