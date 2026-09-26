#!/usr/bin/env python3
"""海底捞月策略回测。

把扫描器的 ok（趋势/海底形态/均线完好/捞月反弹/动量 五条件全过）翻译成可交易规则，
用过去 3 年日线（没有 3 年的 ticker 就用现有全部数据）做回测：
  入场：信号日 t 收盘后判定，t+1 开盘买入
  出场：持有 hold 天收盘卖出，或盘中跌破 -10% 止损
  仓位：等权，最多同时持有 10 只
输出 backtest/results.json + backtest/equity.json，供 dashboard 回测页签使用。
"""
import json
import math
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
from scan import all_tickers, add_indicators
import chan

ROOT = Path(__file__).parent
OUT = ROOT / "backtest"
OUT.mkdir(exist_ok=True)

PERIOD = "3y"
LB = 20            # 扫描器 lookback
MAX_POS = 10
STOP = 0.10        # 止损 -10%
COST = 0.0005      # 单边手续费
BASE = dict(dip_lo=0.05, dip_hi=0.15, retrace_min=0.50, hold=60)
GRID = dict(dip_lo=[0.03, 0.05, 0.08], dip_hi=[0.12, 0.15, 0.20],
            retrace_min=[0.40, 0.50, 0.60], hold=[40, 60, 90])
BUY_SIGNS = ("一买", "二买", "三买")
LEAP = dict(top_k=5, alloc=0.10, max_pos=5, hold=60, stop=0.50,
            ttm=1.0, r=0.0425, iv_mult=1.15, cost=0.01)


def download():
    tickers = all_tickers()
    all_syms = tickers + ["SPY", "QQQ"]
    print(f"[backtest] 下载 {len(all_syms)} 个标的 {PERIOD} 日线 ...", flush=True)
    raw = yf.download(all_syms, period=PERIOD, interval="1d",
                      auto_adjust=True, progress=False, group_by="ticker")
    out = {}
    for t in all_syms:
        try:
            df = raw[t].dropna(how="all")
        except Exception:
            continue
        if df is None or len(df) < 60:
            print(f"  [skip] {t}: 数据不足 ({0 if df is None else len(df)} 天)")
            continue
        df = add_indicators(df)
        out[t] = df
    print(f"[backtest] 可用标的: {len(out)}（含SPY: {'SPY' in out}，含QQQ: {'QQQ' in out}）", flush=True)
    return out


def features(df):
    """逐日计算扫描器五条件的原始特征（numpy 循环，约 750 天很快）。"""
    n = len(df)
    close = df["Close"].to_numpy(float)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    vol = df["Volume"].to_numpy(float)
    s20 = df["sma20"].to_numpy(float)
    s50 = df["sma50"].to_numpy(float)
    s200 = df["sma200"].to_numpy(float)
    rsi = df["rsi"].to_numpy(float)
    mh = df["macd_hist"].to_numpy(float)
    v20 = df["vol20"].to_numpy(float)

    dip = np.full(n, np.nan)
    ret = np.full(n, np.nan)
    trend = np.zeros(n, bool)
    maint = np.zeros(n, bool)
    recvol = np.zeros(n, bool)
    mom = np.zeros(n, bool)
    ok_sma = np.zeros(n, bool)

    for t in range(LB - 1, n):
        w0 = t - LB + 1
        h = high[w0:t + 1]
        s20w = s20[w0:t + 1]
        s50w = s50[w0:t + 1]
        if np.isnan(s20w).any() or np.isnan(s50w).any():
            continue
        ok_sma[t] = True
        hi = float(np.max(h))
        hip = w0 + int(np.argmax(h))  # 窗口内最高点（首次）
        lo = float(np.min(low[hip:t + 1]))  # 高点之后的最低点
        if not (hi > lo > 0):
            continue
        dip[t] = (hi - lo) / hi
        cseg = close[hip:t + 1]
        maint[t] = bool((cseg > s20w[hip - w0:]).all()
                        and (cseg > s50w[hip - w0:]).all())
        ret[t] = (close[t] - lo) / (hi - lo)
        if t >= 10 and not np.isnan(s50[t - 10]):
            trend[t] = (close[t] > s50[t] and s50[t] > s50[t - 10]
                        and s20[t] > s50[t])
        if not np.isnan(v20[t]):
            recvol[t] = float(np.mean(vol[t - 2:t + 1])) > float(v20[t]) * 1.2
        rsi_ok = (not np.isnan(rsi[t])) and (not np.isnan(rsi[t - 3])) \
            and rsi[t] > rsi[t - 3] and rsi[t] > 40
        mh_ok = (not np.isnan(mh[t])) and (not np.isnan(mh[t - 1])) \
            and mh[t] > 0 and mh[t] > mh[t - 1]
        mom[t] = bool(rsi_ok or mh_ok)
    return dict(dip=dip, ret=ret, trend=trend, maint=maint,
                recvol=recvol, mom=mom, ok_sma=ok_sma, s20=s20, s50=s50,
                s200=s200, close=close)


def signals(feat, p):
    """给定参数组合，生成入场信号（boolean 数组）。"""
    return (feat["trend"] & feat["maint"] & feat["recvol"] & feat["mom"]
            & feat["ok_sma"]
            & (feat["dip"] >= p["dip_lo"]) & (feat["dip"] <= p["dip_hi"])
            & (feat["ret"] >= p["retrace_min"])
            & (feat["close"] > feat["s20"]))


def tech_scores(feat):
    """逐日技术评分（0-80，对齐 dip.py 的技术三项：状态35+形态25+趋势保护20，
    去掉基本面 20 分；全部用当日及之前数据，无未来函数）。"""
    close, s20, s50, s200 = feat["close"], feat["s20"], feat["s50"], feat["s200"]
    dip, trend, ok = feat["dip"], feat["trend"], feat["ok_sma"]
    n = len(close)
    score = np.zeros(n)
    for t in range(n):
        if not ok[t]:
            continue
        c = close[t]
        a20, a50, a200 = s20[t], s50[t], s200[t]
        s50_up = t >= 10 and not np.isnan(s50[t - 10]) and s50[t] > s50[t - 10]
        s200_up = (t >= 10 and not np.isnan(a200) and not np.isnan(s200[t - 10])
                   and a200 > s200[t - 10])
        # 技术状态（对齐 scan.tech_state）
        if not np.isnan(a200) and c < a200:
            ts_p = 0
        elif c < a50:
            ts_p = 20 if s200_up else 0
        elif c < a20:
            ts_p = 35 if s50_up else 5
        else:
            ts_p = 8
        # 回调形态（理想区 5%~15%）
        d = dip[t]
        if not np.isnan(d) and 0.05 <= d <= 0.15:
            d_p = 25
        elif not np.isnan(d) and 0 < d <= 0.225:
            d_p = 10
        else:
            d_p = 0
        # 趋势保护
        if trend[t]:
            t_p = 20
        elif c > a50:
            t_p = 10
        elif not np.isnan(a200) and c > a200:
            t_p = 5
        else:
            t_p = 0
        score[t] = ts_p + d_p + t_p
    return score


def _ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S, K, T, r, sigma):
    """Black-Scholes 欧式看涨期权理论价（无历史期权链时的合成定价）。"""
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _ncdf(d1) - K * math.exp(-r * T) * _ncdf(d2)


def trail_sigma(closes, window=60, mult=1.15):
    """逐 ticker 逐日 trailing 实现波动率 ×1.15（年化，clip 到 [0.15, 1.20]）。"""
    out = {}
    for t, c in closes.items():
        s = pd.Series(c)
        lr = np.log(s / s.shift(1))
        rv = lr.rolling(window, min_periods=30).std() * np.sqrt(252)
        sig = rv.mul(mult).clip(0.15, 1.20).bfill().fillna(0.40).to_numpy(float)
        out[t] = sig
    return out


def simulate_leap(master, opens, closes, sig_master, score_master, chan_buy, sigma, p):
    """LEAP call swing：信号日按技术评分取 TopK + 缠论买点确认，
    次日开盘买入 1 年期平值 call；持有 hold 天或期权价值 -stop 止损。
    每笔投入权益 alloc 买期权费，最多同时 max_pos 只。"""
    n_days = len(master)
    tickers = [t for t in sig_master]
    cal_days = np.array([(d - master[0]).days for d in master])
    cash = 1.0
    positions = {}
    equity = np.zeros(n_days)
    trades = []

    def opt_val(tkr, ps, i):
        S = closes[tkr][i]
        if np.isnan(S) or S <= 0:
            return ps["last_v"]
        T = p["ttm"] - (cal_days[i] - ps["entry_cal"]) / 365.0
        v = bs_call(S, ps["K"], T, p["r"], sigma[tkr][i])
        ps["last_v"] = v
        return v

    def mark(i):
        v = cash
        for tkr, ps in positions.items():
            v += ps["units"] * opt_val(tkr, ps, i)
        return v

    for i in range(n_days):
        # --- 出场（先出后进） ---
        for tkr in list(positions.keys()):
            ps = positions[tkr]
            v = opt_val(tkr, ps, i)
            held = i - ps["entry_i"]
            px_exit, why = None, ""
            if v <= ps["entry_v"] * (1 - p["stop"]):
                px_exit, why = v, "期权止损-%d%%" % int(p["stop"] * 100)
            elif held >= p["hold"]:
                px_exit, why = v, "持有到期"
            if px_exit is None:
                continue
            proceeds = ps["units"] * px_exit * (1 - p["cost"])
            cash += proceeds
            r = (px_exit * (1 - p["cost"]) - ps["entry_v"] * (1 + p["cost"]))
            r = r / (ps["entry_v"] * (1 + p["cost"]))
            trades.append(dict(
                ticker=tkr,
                entry=master[ps["entry_i"]].strftime("%Y-%m-%d"),
                exit=master[i].strftime("%Y-%m-%d"),
                entry_px=round(ps["entry_v"], 2), exit_px=round(px_exit, 2),
                ret=round(float(r), 4), days=int(held), why=why))
            del positions[tkr]
        # --- 入场：i-1 日信号 → 按评分 TopK → i 日开盘买入 ---
        if i > 0:
            eq_prev = equity[i - 1] if equity[i - 1] > 0 else mark(i - 1)
            cands = []
            for tkr in tickers:
                if tkr in positions:
                    continue
                if not sig_master[tkr][i - 1]:
                    continue
                if not chan_buy[tkr][i - 1]:
                    continue
                sc = score_master[tkr][i - 1]
                if sc <= 0:
                    continue
                cands.append((sc, tkr))
            cands.sort(reverse=True)
            for sc, tkr in cands[:p["top_k"]]:
                if len(positions) >= p["max_pos"] or tkr in positions:
                    continue
                S = opens[tkr][i]
                if np.isnan(S) or S <= 0:
                    continue
                prem = bs_call(S, S, p["ttm"], p["r"], sigma[tkr][i])
                if prem <= 0:
                    continue
                units = (eq_prev * p["alloc"]) / (prem * (1 + p["cost"]))
                need = units * prem * (1 + p["cost"])
                if cash < need or units <= 0:
                    continue
                cash -= need
                positions[tkr] = dict(entry_i=i, entry_cal=int(cal_days[i]),
                                      K=float(S), entry_v=float(prem),
                                      units=float(units), last_v=float(prem))
        equity[i] = mark(i)
    return equity, trades


def chan_confirm(raw, feats, sig_master, master_dates):
    """对 base 信号日的缠论买点确认（只算有信号的日子，省时间）。"""
    out = {}
    for tkr, df in raw.items():
        if tkr in ("SPY", "QQQ"):
            continue
        cb = np.zeros(len(master_dates), dtype=bool)
        idx = df.index
        for mi in np.where(sig_master[tkr])[0]:
            d = master_dates[mi]
            try:
                pos = idx.get_loc(d)
            except KeyError:
                continue
            if isinstance(pos, slice):
                pos = pos.stop - 1
            if pos < 40:
                continue
            try:
                s = chan.analyze(df.iloc[:pos + 1])["signal"]
            except Exception:
                continue
            cb[mi] = s in BUY_SIGNS
        out[tkr] = cb
        n = int(cb.sum())
        if n:
            print(f"  [chan] {tkr}: {n} 个缠论买点确认", flush=True)
    return out


def simulate(master_dates, opens, closes, lows, sig_master, p, chan_buy=None):
    n_days = len(master_dates)
    tickers = [t for t in sig_master]
    cash = 1.0
    positions = {}
    equity = np.zeros(n_days)
    trades = []

    def mark(i):
        v = cash
        for tkr, ps in positions.items():
            px = closes[tkr][i]
            if not np.isnan(px):
                v += ps["shares"] * px
        return v

    for i in range(n_days):
        # --- 出场（先出后进） ---
        for tkr in list(positions.keys()):
            ps = positions[tkr]
            held = i - ps["entry_i"]
            px_exit, why = None, ""
            lo = lows[tkr][i]
            if not np.isnan(lo) and lo <= ps["px"] * (1 - STOP):
                px_exit, why = ps["px"] * (1 - STOP), "止损"
            elif held >= p["hold"]:
                c = closes[tkr][i]
                if not np.isnan(c):
                    px_exit, why = c, "持有到期"
            if px_exit is None:
                continue
            proceeds = ps["shares"] * px_exit * (1 - COST)
            cash += proceeds
            r = (px_exit * (1 - COST) - ps["px"] * (1 + COST)) / (ps["px"] * (1 + COST))
            trades.append(dict(ticker=tkr,
                               entry=master_dates[ps["entry_i"]].strftime("%Y-%m-%d"),
                               exit=master_dates[i].strftime("%Y-%m-%d"),
                               entry_px=round(ps["px"], 2), exit_px=round(px_exit, 2),
                               ret=round(float(r), 4), days=int(held), why=why))
            del positions[tkr]
        # --- 入场：i-1 日信号 → i 日开盘买入 ---
        if i > 0:
            eq_prev = equity[i - 1] if equity[i - 1] > 0 else mark(i - 1)
            for tkr in tickers:
                if len(positions) >= MAX_POS or tkr in positions:
                    continue
                if not sig_master[tkr][i - 1]:
                    continue
                if chan_buy is not None and not chan_buy[tkr][i - 1]:
                    continue
                op = opens[tkr][i]
                if np.isnan(op) or op <= 0:
                    continue
                size = eq_prev / MAX_POS
                shares = size / op
                need = shares * op * (1 + COST)
                if cash < need or shares <= 0:
                    continue
                cash -= need
                positions[tkr] = dict(entry_i=i, px=float(op), shares=float(shares))
        equity[i] = mark(i)
    # 期末强制平仓（用于统计，净值不受影响因为按市价计）
    return equity, trades


def metrics(equity, dates, trades):
    eq = pd.Series(equity, index=dates)
    rets = eq.pct_change().dropna()
    total = float(eq.iloc[-1] / eq.iloc[0] - 1)
    yrs = max((dates[-1] - dates[0]).days / 365.25, 1e-9)
    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1)
    vol = float(rets.std() * np.sqrt(252)) if len(rets) > 1 else 0.0
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    roll_max = eq.cummax()
    dd = eq / roll_max - 1
    max_dd = float(dd.min())
    trough = dd.idxmin()
    peak = eq.loc[:trough].idxmax()
    dd_days = int((trough - peak).days)
    tr = np.array([t["ret"] for t in trades], dtype=float)
    n = len(tr)
    wins = tr[tr > 0]
    losses = tr[tr < 0]
    win_rate = float(len(wins) / n) if n else 0.0
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) else (float("inf") if len(wins) else 0.0)
    pnl_std = float(tr.mean() / tr.std()) if n > 1 and tr.std() > 0 else 0.0
    return dict(total=round(total, 4), cagr=round(cagr, 4), vol=round(vol, 4),
                sharpe=round(sharpe, 3), max_dd=round(max_dd, 4),
                dd_days=dd_days,
                dd_peak=peak.strftime("%Y-%m-%d"), dd_trough=trough.strftime("%Y-%m-%d"),
                n_trades=n, win_rate=round(win_rate, 4),
                avg_win=round(float(wins.mean()), 4) if len(wins) else 0.0,
                avg_loss=round(float(losses.mean()), 4) if len(losses) else 0.0,
                profit_factor=round(pf, 3) if pf != float("inf") else 999.0,
                expectancy=round(float(tr.mean()), 4) if n else 0.0,
                pnl_by_std=round(pnl_std, 3),
                daily_mean=round(float(rets.mean()), 6),
                daily_std=round(float(rets.std()), 6))


def beta_alpha(strat_rets, spy_rets):
    df = pd.DataFrame({"s": pd.Series(strat_rets), "b": pd.Series(spy_rets)}).dropna()
    s, b = df["s"], df["b"]
    if len(s) < 30 or b.var() == 0:
        return 0.0, 0.0, 0.0
    beta = float(s.cov(b) / b.var())
    alpha = float((s.mean() - beta * b.mean()) * 252)
    corr = float(s.corr(b))
    return round(beta, 3), round(alpha, 4), round(corr, 3)


def san(o):
    """递归把 NaN/inf 转成 None，保证 JSON 干净。"""
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: san(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [san(v) for v in o]
    return o


def main():
    t0 = datetime.now()
    raw = download()
    if "SPY" not in raw:
        print("[backtest] SPY 数据缺失，无法生成基准对比", flush=True)
        return
    tickers = [t for t in raw if t not in ("SPY", "QQQ")]

    # master 日历：SPY 有有效收盘价的交易日（去掉 Yahoo 尾部 NaN 的预发布 bar）
    spy_df = raw["SPY"]
    master = spy_df.index[spy_df["Close"].notna()]
    print(f"[backtest] 有效交易日: {len(master)}（{master[0].date()} ~ {master[-1].date()}）",
          flush=True)
    opens, closes, lows = {}, {}, {}
    feats = {}
    for t in tickers:
        df = raw[t]
        f = features(df)
        idx = df.index
        # 特征数组对齐到 master 日历（数据不足的 ticker 缺失处填 NaN/False）
        def _al(arr, fill):
            s = pd.Series(arr, index=idx).reindex(master)
            if fill is not None:
                s = s.fillna(fill)
            return s.to_numpy()
        fa = dict(dip=_al(f["dip"], None), ret=_al(f["ret"], None),
                  s20=_al(f["s20"], None), s50=_al(f["s50"], None),
                  s200=_al(f["s200"], None), close=_al(f["close"], None))
        for k in ("trend", "maint", "recvol", "mom", "ok_sma"):
            fa[k] = _al(f[k], False).astype(bool)
        fa["_has"] = pd.Series(True, index=idx).reindex(master).fillna(False).to_numpy(bool)
        feats[t] = fa
        # 对齐到 master 日历
        o = pd.Series(df["Open"].to_numpy(float), index=df.index).reindex(master)
        c = pd.Series(df["Close"].to_numpy(float), index=df.index).reindex(master)
        l = pd.Series(df["Low"].to_numpy(float), index=df.index).reindex(master)
        opens[t] = o.to_numpy(float)
        closes[t] = c.to_numpy(float)
        lows[t] = l.to_numpy(float)

    def sig_for(p):
        out = {}
        for t in tickers:
            out[t] = signals(feats[t], p) & feats[t]["_has"]
        return out

    # --- 基准：SPY / QQQ 买入持有 ---
    def bench_eq(sym):
        c = pd.Series(raw[sym]["Close"].to_numpy(float),
                      index=raw[sym].index).reindex(master).to_numpy(float)
        return c / c[0]
    spy_eq = bench_eq("SPY")
    m_spy = metrics(spy_eq, master, [])
    if "QQQ" in raw:
        qqq_eq = bench_eq("QQQ")
        m_qqq = metrics(qqq_eq, master, [])
    else:
        qqq_eq, m_qqq = None, None
        print("[backtest] QQQ 数据缺失，跳过 QQQ 基准", flush=True)

    # --- 基础策略 ---
    print("[backtest] 基础策略回测 ...", flush=True)
    sig_base = sig_for(BASE)
    n_sig = sum(int(v.sum()) for v in sig_base.values())
    print(f"[backtest] 基础信号数: {n_sig}", flush=True)
    eq_base, tr_base = simulate(master, opens, closes, lows, sig_base, BASE)
    m_base = metrics(eq_base, master, tr_base)

    # --- 缠论确认变体 ---
    print("[backtest] 缠论买点确认变体 ...", flush=True)
    chan_buy = chan_confirm(raw, feats, sig_base, master)
    eq_chan, tr_chan = simulate(master, opens, closes, lows, sig_base, BASE, chan_buy)
    m_chan = metrics(eq_chan, master, tr_chan)

    # --- LEAP call swing（按技术评分选股 + 缠论买点确认） ---
    print("[backtest] LEAP call swing 回测 ...", flush=True)
    score_master = {t: tech_scores(feats[t]) for t in tickers}
    sigma = trail_sigma(closes)
    eq_leap, tr_leap = simulate_leap(master, opens, closes, sig_base,
                                     score_master, chan_buy, sigma, LEAP)
    m_leap = metrics(eq_leap, master, tr_leap)
    print(f"[backtest] LEAP 交易数: {len(tr_leap)}", flush=True)

    # --- 参数寻优 ---
    print("[backtest] 参数网格寻优 ...", flush=True)
    grid_rows = []
    for lo in GRID["dip_lo"]:
        for hi in GRID["dip_hi"]:
            if hi <= lo:
                continue
            for rmin in GRID["retrace_min"]:
                for hold in GRID["hold"]:
                    p = dict(dip_lo=lo, dip_hi=hi, retrace_min=rmin, hold=hold)
                    eq, tr = simulate(master, opens, closes, lows, sig_for(p), p)
                    m = metrics(eq, master, tr)
                    calmar = m["cagr"] / abs(m["max_dd"]) if m["max_dd"] < 0 else 0
                    grid_rows.append(dict(params=p, sharpe=m["sharpe"], calmar=round(calmar, 3),
                                          cagr=m["cagr"], max_dd=m["max_dd"],
                                          n_trades=m["n_trades"], win_rate=m["win_rate"],
                                          profit_factor=m["profit_factor"]))
    grid_rows.sort(key=lambda r: -r["sharpe"])
    best_sharpe = grid_rows[0]
    best_calmar = max(grid_rows, key=lambda r: r["calmar"])
    # 持有期敏感性（其余取最优 sharpe 参数）
    bp = best_sharpe["params"]
    hold_sens = {}
    for hold in GRID["hold"]:
        p = dict(bp, hold=hold)
        eq, tr = simulate(master, opens, closes, lows, sig_for(p), p)
        m = metrics(eq, master, tr)
        hold_sens[str(hold)] = dict(sharpe=m["sharpe"], cagr=m["cagr"],
                                    max_dd=m["max_dd"], n_trades=m["n_trades"],
                                    win_rate=m["win_rate"])
    print(f"[backtest] 网格完成 {len(grid_rows)} 组", flush=True)

    # --- vs 大盘（SPY / QQQ） ---
    def vs_pair(eq_s, m_s, eq_b, m_b):
        s_rets = pd.Series(eq_s).pct_change().dropna().to_numpy()
        b_rets = pd.Series(eq_b).pct_change().dropna().to_numpy()
        be, al, co = beta_alpha(s_rets, b_rets)
        return dict(beta=be, alpha=al, corr=co,
                    excess_cagr=round(m_s["cagr"] - m_b["cagr"], 4),
                    dd_diff=round(m_s["max_dd"] - m_b["max_dd"], 4))
    vsb = {"base_vs_spy": vs_pair(eq_base, m_base, spy_eq, m_spy),
           "chan_vs_spy": vs_pair(eq_chan, m_chan, spy_eq, m_spy),
           "leap_vs_spy": vs_pair(eq_leap, m_leap, spy_eq, m_spy)}
    if m_qqq is not None:
        vsb["base_vs_qqq"] = vs_pair(eq_base, m_base, qqq_eq, m_qqq)
        vsb["chan_vs_qqq"] = vs_pair(eq_chan, m_chan, qqq_eq, m_qqq)
        vsb["leap_vs_qqq"] = vs_pair(eq_leap, m_leap, qqq_eq, m_qqq)
    beta, alpha, corr = (vsb["base_vs_spy"]["beta"],
                         vsb["base_vs_spy"]["alpha"],
                         vsb["base_vs_spy"]["corr"])

    # --- 优化建议（由数字自动生成） ---
    sug = []
    bs, bc = best_sharpe, best_calmar
    sug.append(
        f"参数优化：网格 {len(grid_rows)} 组中夏普最优为"
        f"回踩 {bs['params']['dip_lo']*100:.0f}%–{bs['params']['dip_hi']*100:.0f}%、"
        f"收复≥{bs['params']['retrace_min']*100:.0f}%、持有 {bs['params']['hold']} 天，"
        f"夏普 {m_base['sharpe']:.2f}→{bs['sharpe']:.2f}，"
        f"年化 {m_base['cagr']*100:.1f}%→{bs['cagr']*100:.1f}%。"
        + (f"Calmar 最优是另一组（回踩 {bc['params']['dip_lo']*100:.0f}%–{bc['params']['dip_hi']*100:.0f}%、"
           f"持有 {bc['params']['hold']} 天，Calmar {bc['calmar']:.2f}），"
           f"更看重回撤控制可选这组。"
           if bc["params"] != bs["params"] else "该组同时也是 Calmar 最优。"))
    hs = [f"{k}天:夏普{v['sharpe']:.2f}/胜率{v['win_rate']*100:.0f}%/交易{v['n_trades']}笔"
          for k, v in sorted(hold_sens.items())]
    sug.append(f"持有期敏感性（其余参数取最优）：{'；'.join(hs)}。"
               f"{'持有期越长胜率越高但资金周转下降，' if hold_sens['90']['win_rate'] >= hold_sens['40']['win_rate'] else ''}"
               f"建议持有期取 {bs['params']['hold']} 天。")
    d_sharpe = m_chan["sharpe"] - m_base["sharpe"]
    d_wr = (m_chan["win_rate"] - m_base["win_rate"]) * 100
    sug.append(
        f"缠论确认：叠加一/二/三买后，交易 {m_base['n_trades']}→{m_chan['n_trades']} 笔，"
        f"胜率 {m_base['win_rate']*100:.1f}%→{m_chan['win_rate']*100:.1f}%（{d_wr:+.1f}pp），"
        f"夏普 {m_base['sharpe']:.2f}→{m_chan['sharpe']:.2f}（{d_sharpe:+.2f}），"
        f"盈亏因子 {m_base['profit_factor']:.2f}→{m_chan['profit_factor']:.2f}。"
        + ("建议入场叠加缠论买点确认：过滤效果为正。" if d_sharpe > 0.05
           else ("缠论确认减少了交易次数但夏普变化不大，可作为可选过滤器。" if abs(d_sharpe) <= 0.05
                 else "缠论确认反而拖累夏普，不建议作为硬性过滤，可只作观察。")))
    ex = (m_base["cagr"] - m_spy["cagr"]) * 100
    sug.append(
        f"相对大盘：策略年化 {m_base['cagr']*100:.1f}% vs SPY {m_spy['cagr']*100:.1f}%，"
        f"超额 {ex:+.1f}pp；Beta {beta}、年化 Alpha {alpha*100:+.1f}%、相关性 {corr}；"
        f"最大回撤 {m_base['max_dd']*100:.1f}% vs SPY {m_spy['max_dd']*100:.1f}%。"
        + ("策略在回撤控制上优于大盘。" if m_base["max_dd"] > m_spy["max_dd"]
           else "策略回撤深于大盘，止损/仓位需再收紧。"))
    if m_qqq is not None:
        exq = (m_base["cagr"] - m_qqq["cagr"]) * 100
        sug.append(
            f"相对 QQQ：策略年化 {m_base['cagr']*100:.1f}% vs QQQ {m_qqq['cagr']*100:.1f}%，"
            f"超额 {exq:+.1f}pp；最大回撤 {m_base['max_dd']*100:.1f}% vs QQQ {m_qqq['max_dd']*100:.1f}%；"
            f"Beta {vsb['base_vs_qqq']['beta']}、相关性 {vsb['base_vs_qqq']['corr']}。"
            + ("相对 QQQ 同样跑赢。" if exq > 0 else "相对 QQQ 未跑赢，策略风格更偏防御/价值。"))
    ex_ls = (m_leap["cagr"] - m_spy["cagr"]) * 100
    ex_lq = (m_leap["cagr"] - m_qqq["cagr"]) * 100 if m_qqq is not None else None
    sug.append(
        f"LEAP call swing（技术评分 Top{LEAP['top_k']} + 缠论买点确认，1 年期平值 call，"
        f"持有 {LEAP['hold']} 天 / 期权价值 -{int(LEAP['stop']*100)}% 止损）："
        f"年化 {m_leap['cagr']*100:.1f}%、夏普 {m_leap['sharpe']:.2f}、"
        f"最大回撤 {m_leap['max_dd']*100:.1f}%、胜率 {m_leap['win_rate']*100:.1f}%、"
        f"盈亏因子 {m_leap['profit_factor']:.2f}、P&L÷σ {m_leap['pnl_by_std']:.2f}，"
        f"共 {m_leap['n_trades']} 笔；相对 SPY 超额 {ex_ls:+.1f}pp"
        + (f"、相对 QQQ {ex_lq:+.1f}pp" if ex_lq is not None else "")
        + f"；波动率 {m_leap['vol']*100:.1f}% vs 正股策略 {m_base['vol']*100:.1f}%。"
        + ("期权杠杆放大了收益也放大了波动，且存在时间价值损耗，仓位需更克制。"
           if m_leap["vol"] > m_base["vol"] else ""))

    # --- 落盘 ---
    dd_series = (pd.Series(eq_base) / pd.Series(eq_base).cummax() - 1).round(4)
    equity_json = dict(
        dates=[d.strftime("%Y-%m-%d") for d in master],
        strat=[round(float(x), 4) for x in eq_base],
        spy=[round(float(x), 4) for x in spy_eq],
        qqq=([round(float(x), 4) for x in qqq_eq] if qqq_eq is not None else []),
        leap=[round(float(x), 4) for x in eq_leap],
        drawdown=dd_series.tolist())
    (OUT / "equity.json").write_text(json.dumps(san(equity_json), separators=(",", ":")))

    tr_sorted = sorted(tr_base, key=lambda t: t["ret"])
    tr_leap_sorted = sorted(tr_leap, key=lambda t: t["ret"])
    results = dict(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        period=dict(start=master[0].strftime("%Y-%m-%d"),
                    end=master[-1].strftime("%Y-%m-%d"),
                    n_days=len(master), n_tickers=len(tickers)),
        params_base=BASE, max_pos=MAX_POS, stop=STOP, cost=COST,
        params_leap=LEAP,
        metrics_base=m_base, metrics_chan=m_chan, metrics_spy=m_spy,
        metrics_qqq=m_qqq,
        metrics_leap=m_leap,
        vs_market=dict(beta=beta, alpha=alpha, corr=corr,
                       excess_cagr=round(m_base["cagr"] - m_spy["cagr"], 4)),
        vs_benchmarks=vsb,
        grid_top8=grid_rows[:8],
        suggestion=sug,
        best_trades=sorted(tr_base, key=lambda t: -t["ret"])[:5],
        worst_trades=tr_sorted[:5],
        best_leap_trades=sorted(tr_leap, key=lambda t: -t["ret"])[:5],
        worst_leap_trades=tr_leap_sorted[:5],
        assumptions=[
            "信号日 t 收盘后判定，t+1 开盘买入；无未来函数",
            f"等权，最多同时持有 {MAX_POS} 只；持有 {BASE['hold']} 天或 -{int(STOP*100)}% 止损",
            f"单边手续费 {COST*100:.2f}%，无滑点假设",
            "3 年日线，auto_adjust 复权；数据不足 3 年的标的用现有全部数据",
            "Universe 为当前 40 只成分（存在幸存者偏差）；未计入分红税、融资成本",
            f"LEAP 策略：信号日按技术评分（0-80 分，不含基本面）取 Top{LEAP['top_k']} + 缠论买点确认，"
            f"次日开盘买入 1 年期平值 call；每笔投入权益 {int(LEAP['alloc']*100)}% 买期权费，"
            f"最多同时 {LEAP['max_pos']} 只",
            "期权价为 Black-Scholes 合成（无历史期权链数据）：r=4.25%，"
            "IV=过去 60 日实现波动率×1.15，每日按收盘重估；"
            f"期权价值 -{int(LEAP['stop']*100)}% 止损，单边费用按期权费 {LEAP['cost']*100:.0f}% 计",
        ])
    (OUT / "results.json").write_text(
        json.dumps(san(results), ensure_ascii=False, separators=(",", ":")))
    print(f"[backtest] done: results.json + equity.json -> {OUT} "
          f"({(datetime.now()-t0).total_seconds():.0f}s)", flush=True)


if __name__ == "__main__":
    main()
