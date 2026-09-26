#!/bin/bash
# LEAP 扫描全管道：形态扫描 → 期权链 → 新闻 → 基本面 → 入场建议 → 策略回测 → dashboard（含正股/缠论图表/策略回测页签）→ 多周期图表数据
set -u
cd /home/hatch/workspace/leap-scanner
PY=./venv/bin/python
echo "[1/8] scan...";      $PY scan.py > /dev/null 2>> reports/pipeline.log || echo "scan failed"
echo "[2/8] chains...";    $PY chains.py > /dev/null 2>> reports/pipeline.log || echo "chains failed"
echo "[3/8] news...";      $PY news.py > /dev/null 2>> reports/pipeline.log || echo "news failed"
echo "[4/8] stock...";     $PY stock.py > /dev/null 2>> reports/pipeline.log || echo "stock failed"
echo "[5/8] entry...";     $PY entry.py > /dev/null 2>> reports/pipeline.log || echo "entry failed"
echo "[6/8] backtest...";  $PY backtest.py 2>> reports/pipeline.log || echo "backtest failed"
echo "[7/8] dashboard..."; $PY build_dashboard.py 2>> reports/pipeline.log || echo "dashboard failed"
echo "[8/8] chart data..."; $PY chart_data.py 2>> reports/pipeline.log || echo "chart_data failed"
echo "done $(date)"
