# LEAP Scanner （海底捞月）

A personal stock-screening and backtesting toolkit: a daily "buy-the-dip" scanner over a
42-ticker universe, Chan-theory （缠论） technical confirmation, and a backtested
LEAP-call swing-trading strategy. Results are served through a single-file interactive
dashboard.

> **Disclaimer:** This is a personal research/education project. Nothing here is
> investment advice or a recommendation to buy or sell any security. Option prices in
> the backtest are Black–Scholes synthetic values (no historical option chains).

## What it does

1. **Daily scan** (`scan.py`, `dip.py`) — scores each ticker 0–100 on dip depth,
   retracement, trend protection, and fundamentals (Free Cash Flow yield). Grades
   A/B/C/D; A means deep dip + clean retracement.
2. **Chan-theory confirmation** (`chan.py`, `chart_data.py`) — fractal → stroke （笔） →
   pivot （中枢） → divergence （背驰） → buy/sell points （一/二/三类买卖点）,
   rendered with TradingView Lightweight Charts across 7 timeframes.
3. **Backtest** (`backtest.py`) — 3-year walk-forward backtest of:
   - base stock strategy (buy B-or-better dips, 40-day hold),
   - Chan-confirmed variant (buy only on Chan buy points),
   - LEAP-call swing variant (top-5 technical scores + Chan buy point → 1-yr ATM
     call, 60-day hold / −50% stop, Black–Scholes repriced daily),
   vs SPY and QQQ benchmarks (excess CAGR, max drawdown, beta/alpha).
4. **Dashboard** (`dashboard.html`) — single-file, multi-tab: scanner, backtest,
   news, stock pages, Chan charts.

## Latest backtest snapshot (3Y, 2023-09-25 → 2026-09-24, 753 trading days)

| Strategy | Total | CAGR | Sharpe | Max DD | Profit factor | Win rate | Trades |
|---|---|---|---|---|---|---|---|
| Base (stock) | +238.7% | 50.2% | 1.09 | −42.0% | 2.83 | 39% | 120 |
| Chan-confirmed | +46.0% | 13.5% | 0.97 | −13.2% | 4.28 | 37% | 19 |
| LEAP call swing | +179.8% | 40.9% | 1.33 | −25.5% | 4.14 | 39% | 18 |
| SPY | +84.1% | 22.6% | 1.41 | −18.8% | — | — | — |
| QQQ | +109.6% | 28.0% | 1.31 | −22.8% | — | — | — |

Excess CAGR vs SPY: base +27.6pp, Chan-confirmed −9.1pp, LEAP +18.3pp. Note the
trade-off the numbers make explicit: Chan confirmation cuts max drawdown by ~2/3
(−42.0% → −13.2%) at the cost of most of the upside; the LEAP variant keeps
option-like convexity (profit factor 4.14) with a −25.5% max DD. See the Backtest
tab or `backtest/results.json` for full metrics (beta/alpha, best/worst trades,
grid search, suggestions).

## File map

| File | Purpose |
|---|---|
| `dashboard.html` | generated single-file dashboard (open in browser) |
| `backtest.py` | backtest engine (strategies, benchmarks, LEAP/BS pricing) |
| `scan.py` / `dip.py` | daily scanner + 海底捞月 scoring |
| `chan.py` / `chart_data.py` | Chan-theory engine + chart JSON export |
| `chart_tab.js` / `backtest_tab.js` | dashboard tab renderers |
| `build_dashboard.py` | assembles `dashboard.html` from parts |
| `stock.py` / `news.py` / `chains.py` | per-stock pages, news, option chains |
| `entry.py` | entry guidance: stock 买入/小批建仓/观察 + LEAP strike/expiry |
| `run_all.sh` | full pipeline: scan → chains → news → stock → entry → backtest → dashboard → charts |
| `backtest/results.json` | latest backtest metrics |
| `backtest/equity.json` | equity curves (base, chan, leap, SPY, QQQ) |

## Run it

```bash
cd leap-scanner
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
./run_all.sh        # full pipeline, outputs dashboard.html
```

Or run steps individually: `./venv/bin/python scan.py`, `./venv/bin/python backtest.py`,
`./venv/bin/python chart_data.py`, `./venv/bin/python build_dashboard.py`.

Data: Yahoo Finance (daily bars). No API keys needed.

## 中文摘要

海底捞月选股 + 缠论确认 + LEAP call 波段，三套策略 3 年回测跑赢 SPY/QQQ，
详情见 dashboard 回测页签。**回测不构成买卖建议；期权价格为 BS 合成价。**

## Roadmap

- [ ] Parameter calibration (walk-forward, per-regime)
- [ ] Live paper-trading log vs scanner signals
- [ ] Earnings-date filter for dip signals
