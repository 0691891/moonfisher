#!/usr/bin/env python3
"""正股小额买入+基本面+抄底评级：为 dashboard 提供 HTML 片段（build_fragment），
也可独立运行生成 stock.html。"""
import glob
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def latest(pattern):
    fs = [f for f in glob.glob(str(BASE / "reports" / pattern))
          if "/_stale/" not in f]
    fs.sort(key=lambda f: Path(f).stat().st_mtime, reverse=True)
    return fs[0] if fs else None


DIP_CSS = {"A": "#3fb950", "B": "#58a6ff", "C": "#d29922", "D": "#8b949e"}
DIP_LBL = {"A": "抄底信号强", "B": "可分批观察", "C": "观望", "D": "不建议抄底"}


def get_stock_data():
    """返回 (stamp, rows)，无数据时返回 (None, [])。"""
    sf = latest("stock-*.json")
    if not sf:
        return None, []
    stock = json.loads(Path(sf).read_text())
    stamp = stock["date"]
    scf = latest("scan-*.json")
    scan = json.loads(Path(scf).read_text()) if scf else {"results": {}}
    tech = {t: (r.get("detail") or {}).get("tech_state", "")
            for t, r in scan.get("results", {}).items()}

    rows = []
    for sec, ts in stock["sectors"].items():
        for t in ts:
            r = stock["results"].get(t, {})
            if not r.get("ok"):
                continue
            f = r["fields"]
            rows.append({"t": t, "sec": sec, "name": f.get("longName") or t,
                         "price": r["price"], "per100": r["per_100"],
                         "per500": r["per_500"], "mcap": f.get("marketCap"),
                         "pe": f.get("trailingPE"), "fpe": f.get("forwardPE"),
                         "peg": f.get("pegRatio"),
                         "rg": f.get("revenueGrowth"),
                         "pm": f.get("profitMargins"),
                         "roe": f.get("returnOnEquity"),
                         "div": f.get("dividendYield"),
                         "beta": f.get("beta"),
                         "tp": f.get("targetMeanPrice"),
                         "upside": r["upside"],
                         "rec": f.get("recommendationKey"),
                         "nrec": f.get("numberOfAnalystOpinions"),
                         "d52": r["dist_52w_high"],
                         "checks": r["checks_pass"],
                         "tech": tech.get(t, ""),
                         "dip": r.get("dip_rating", "?"),
                         "dip_score": r.get("dip_score"),
                         "dip_depth": r.get("dip_depth"),
                         "dip_reasons": r.get("dip_reasons") or []})
    return stamp, rows


def _cand_html(rows):
    cand = sorted([r for r in rows if r["dip"] in ("A", "B")],
                  key=lambda x: x["dip_score"] or 0, reverse=True)
    return "".join(
        "<tr><td><b>%s</b></td>"
        "<td><span class='badge' style='border-color:%s;color:%s'>%s · %s</span></td>"
        "<td class='num'>%s</td><td class='num'>$%.2f</td>"
        "<td class='num'>%s</td><td>%s</td><td><span class='badge'>%d/5</span></td>"
        "<td class='rsn'>%s</td></tr>"
        % (r["t"], DIP_CSS[r["dip"]], DIP_CSS[r["dip"]], r["dip"],
           DIP_LBL[r["dip"]],
           r["dip_score"], r["price"],
           ("%.1f%%" % (r["dip_depth"] * 100)) if r["dip_depth"] is not None else "—",
           r["tech"], r["checks"], "；".join(r["dip_reasons"]))
        for r in cand) or "<tr><td colspan='8' class='note'>今日无 A/B 抄底候选</td></tr>"


def _cheap_html(rows):
    cheap = sorted([r for r in rows if r["price"]],
                   key=lambda x: x["price"])[:12]
    return "".join(
        "<tr><td><b>%s</b></td><td>%s</td><td class='num'>$%.2f</td>"
        "<td class='num'>%.2f</td><td class='num'>%.2f</td>"
        "<td><span class='badge' style='border-color:%s;color:%s'>%s</span></td>"
        "<td class='num'>%s</td></tr>"
        % (r["t"], r["name"][:28], r["price"], r["per100"], r["per500"],
           DIP_CSS.get(r["dip"], "#8b949e"), DIP_CSS.get(r["dip"], "#8b949e"),
           r["dip"] if r["dip"] != "?" else "—",
           ("$%.1fB" % (r["mcap"] / 1e9)) if r["mcap"] else "—")
        for r in cheap)


# 样式全部用 #p-stock 作用域隔离，避免与 dashboard 的 .badge 等冲突
FRAG_CSS = """
#p-stock .card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin-bottom:16px}
#p-stock table{border-collapse:collapse;width:100%;font-size:12px}
#p-stock th,#p-stock td{padding:7px 9px;border-bottom:1px solid #21262d;text-align:left;white-space:nowrap}
#p-stock th{color:#8b949e;cursor:pointer;user-select:none;position:sticky;top:0;background:#161b22}
#p-stock th:hover{color:#e6edf3}
#p-stock .num{font-variant-numeric:tabular-nums;text-align:right}
#p-stock tr:hover td{background:#1c2128}
#p-stock .wrap{overflow-x:auto}
#p-stock .note{font-size:11px;color:#8b949e;line-height:1.7}
#p-stock .badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#ffffff08;border:1px solid #1f6feb}
#p-stock .rsn{font-size:11px;color:#8b949e;white-space:normal;min-width:220px}
#p-stock a{color:#58a6ff}
"""


def build_fragment():
    """返回 {'stamp','css','body','js'}，无数据时返回 None。"""
    stamp, rows = get_stock_data()
    if not rows:
        return None
    payload = json.dumps({"date": stamp, "rows": rows}, ensure_ascii=False)
    body = """<div class="sect">正股小额买入 + 基本面</div>
<div class="card"><b>抄底评级候选</b> <span class="note">— 技术形态×基本面机械打分：技术状态35（正常回调35/修正观察20/趋势完好8/警告5/趋势反转0）＋回调形态25（近20日高点回调5%~15%为理想区）＋趋势保护20（均线多头完好）＋基本面勾选20；趋势反转强制D，警告或超跌（>22.5%）最高C</span>
<div class="wrap"><table><tr><th>Ticker</th><th>抄底评级</th><th>分数</th><th>现价</th><th>回调深度</th><th>技术状态</th><th>基本面勾选</th><th>打分理由</th></tr>""" + _cand_html(rows) + """</table></div></div>
<div class="card"><b>超低投资速览</b> <span class="note">— 按现价从低到高，1股成本最低的12只（$100/$500可买股数）</span>
<div class="wrap"><table><tr><th>Ticker</th><th>公司</th><th>现价</th><th>$100可买</th><th>$500可买</th><th>抄底评级</th><th>市值</th></tr>""" + _cheap_html(rows) + """</table></div></div>
<div class="card"><b>基本面全表</b> <span class="note">— 点击表头排序（默认按抄底分数）；勾选=PEG&lt;2/营收增长&gt;15%/净利率&gt;15%/ROE&gt;12%/目标价&gt;现价（机械勾选，非推荐）；悬停抄底评级看打分理由</span>
<div class="wrap"><table id="ft"><thead><tr>
<th data-k="t">Ticker</th><th data-k="dip_score">抄底评级</th><th data-k="sec">板块</th><th data-k="price">现价</th>
<th data-k="per100">$100可买</th><th data-k="mcap">市值</th><th data-k="pe">TTM P/E</th>
<th data-k="peg">PEG</th><th data-k="rg">营收增长</th><th data-k="pm">净利率</th>
<th data-k="roe">ROE</th><th data-k="div">股息率</th><th data-k="upside">目标价隐含</th>
<th data-k="rec">分析师</th><th data-k="d52">距52周高</th><th data-k="checks">勾选</th><th data-k="tech">技术状态</th>
</tr></thead><tbody id="fb"></tbody></table></div></div>
<div class="note">Yahoo 免费基本面可能滞后或缺失（ETF 无 P/E 等属正常）；分析师目标价仅供参考。技术状态来自当日 LEAP 形态扫描。抄底评级为机械打分，不构成买卖建议。</div>"""
    js = """<script>
(function(){
const STOCK_DATA = """ + payload + """;
const DIP_LBL={A:'抄底信号强',B:'可分批观察',C:'观望',D:'不建议抄底'};
const DIP_CSS={A:'#3fb950',B:'#58a6ff',C:'#d29922',D:'#8b949e'};
function fmtM(x){return x==null?'—':'$'+(x/1e9).toFixed(1)+'B';}
function fmtP(x){return x==null?'—':(x*100).toFixed(1)+'%';}
function fmtD(x){return x==null?'—':Number(x).toFixed(2)+'%';}
function fmtN(x,d){return x==null?'—':Number(x).toFixed(d==null?2:d);}
function dipBadge(r){const c=DIP_CSS[r.dip]||'#8b949e';
  return '<span class="badge" style="border-color:'+c+';color:'+c+'" title="'+(r.dip_reasons||[]).join('；')+'">'
    +r.dip+' '+(r.dip_score==null?'':r.dip_score+'分')+'</span>';}
let sortK='dip_score',asc=false;
function render(){
  const tb=document.getElementById('fb');if(!tb)return;tb.innerHTML='';
  const rs=[...STOCK_DATA.rows].sort((a,b)=>{const x=a[sortK],y=b[sortK];
    if(x==null)return 1;if(y==null)return -1;
    return (typeof x==='string'?x.localeCompare(y):x-y)*(asc?1:-1);});
  for(const r of rs){
    const tr=document.createElement('tr');
    tr.innerHTML='<td><b>'+r.t+'</b></td><td>'+dipBadge(r)+'</td><td>'+r.sec+'</td><td class="num">$'+fmtN(r.price)+'</td>'
      +'<td class="num">'+fmtN(r.per100)+'</td><td class="num">'+fmtM(r.mcap)+'</td>'
      +'<td class="num">'+fmtN(r.pe)+'</td><td class="num">'+fmtN(r.peg)+'</td>'
      +'<td class="num">'+fmtP(r.rg)+'</td><td class="num">'+fmtP(r.pm)+'</td>'
      +'<td class="num">'+fmtP(r.roe)+'</td><td class="num">'+fmtD(r.div)+'</td>'
      +'<td class="num">'+fmtP(r.upside)+'</td><td>'+(r.rec||'—')+'</td>'
      +'<td class="num">'+fmtP(r.d52)+'</td>'
      +'<td><span class="badge">'+r.checks+'/5</span></td><td>'+(r.tech||'—')+'</td>';
    tb.appendChild(tr);
  }
}
document.querySelectorAll('#ft th').forEach(th=>{th.onclick=()=>{const k=th.dataset.k;
  if(sortK===k)asc=!asc;else{sortK=k;asc=false;}render();};});
render();
})();
</script>"""
    return {"stamp": stamp, "css": FRAG_CSS, "body": body, "js": js}


def main():
    frag = build_fragment()
    if not frag:
        print("no stock data")
        return
    stamp = frag["stamp"]
    html = """<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>正股小额买入 + 基本面 """ + stamp + """</title>
<style>
body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:16px}
h1{font-size:20px;margin:8px 0}.sub{color:#8b949e;font-size:12px;margin-bottom:12px}
""" + FRAG_CSS + """
</style></head><body>
<h1>正股小额买入 + 基本面</h1>
<div class="sub">数据日期 """ + stamp + """ ｜ Yahoo 基本面 ｜ 展示与筛选，仅供参考，不构成买卖建议</div>
<div id="p-stock">""" + frag["body"] + """</div>
""" + frag["js"] + """</body></html>"""
    (BASE / "stock.html").write_text(html)
    print(f"stock.html built: {stamp}")


if __name__ == "__main__":
    main()
