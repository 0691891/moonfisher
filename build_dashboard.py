#!/usr/bin/env python3
"""生成自包含 dashboard.html：评级扫描 / 期权链 / 新闻 / 正股基本面 四个页签。"""
import glob
import json
from datetime import datetime
from pathlib import Path

from build_stock_page import build_fragment

BASE = Path(__file__).resolve().parent
REP = BASE / "reports"


def latest(prefix):
    files = [f for f in glob.glob(str(REP / (prefix + "-*.json")))
             if "/_stale/" not in f]
    files.sort(key=lambda f: Path(f).stat().st_mtime, reverse=True)
    if not files:
        return {}
    return json.loads(Path(files[0]).read_text())


def main():
    scan = latest("scan")
    chains = latest("chains")
    news = latest("news")
    entry = latest("entry")
    bt_path = BASE / "backtest" / "results.json"
    bt = json.loads(bt_path.read_text()) if bt_path.exists() else {}
    bteq_path = BASE / "backtest" / "equity.json"
    bteq = json.loads(bteq_path.read_text()) if bteq_path.exists() else {}
    frag = build_fragment()
    stamp = scan.get("date") or datetime.now().strftime("%Y-%m-%d")
    payload = json.dumps({"scan": scan, "chains": chains, "news": news,
                          "entry": entry,
                          "backtest": bt, "btequity": bteq},
                         ensure_ascii=False)
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append("<title>LEAP Dashboard " + stamp + "</title>")
    parts.append("""<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;padding:16px;max-width:1200px;margin:0 auto}
h1{font-size:20px;margin-bottom:4px}
.sub{color:#8b949e;font-size:12px;margin-bottom:16px}
.tabs{display:flex;gap:8px;margin-bottom:16px}
.tabs button{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:8px 18px;border-radius:8px;cursor:pointer;font-size:14px}
.tabs button.active{background:#1f6feb;border-color:#1f6feb}
table{width:100%;border-collapse:collapse;margin-bottom:24px;font-size:13px}
th,td{padding:8px 10px;border-bottom:1px solid #21262d;text-align:left;white-space:nowrap}
th{color:#8b949e;font-weight:600;background:#161b22}
tr:hover td{background:#161b22}
.sect{font-size:16px;margin:18px 0 8px;color:#58a6ff}
.badge{display:inline-block;min-width:26px;text-align:center;padding:2px 8px;border-radius:6px;font-weight:700}
.S{background:#d4a017;color:#000}.A{background:#238636;color:#fff}.B{background:#1f6feb;color:#fff}
.C{background:#6e7681;color:#fff}.D{background:#da3633;color:#fff}
.impact{color:#ff7b72;font-weight:700}
.ntitle{margin:6px 0}.ntitle a{color:#e6edf3;text-decoration:none}.ntitle a:hover{color:#58a6ff}
.nmeta{color:#8b949e;font-size:12px}
select{background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:8px 12px;font-size:14px;margin-bottom:12px}
.warn{background:#161b22;border:1px solid #d4a017;border-radius:8px;padding:10px 14px;margin-bottom:16px;font-size:12px}
.num{font-variant-numeric:tabular-nums}
.chartctl{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:10px}
.chartctl select{margin-bottom:0}
.tfbtns{display:flex;gap:6px;flex-wrap:wrap}
.tfbtns button{background:#161b22;border:1px solid #30363d;color:#e6edf3;padding:6px 12px;border-radius:8px;cursor:pointer;font-size:13px}
.tfbtns button.active{background:#1f6feb;border-color:#1f6feb}
.ovl{display:flex;gap:12px;flex-wrap:wrap;font-size:13px;color:#8b949e}
.ovl label{display:flex;gap:4px;align-items:center;cursor:pointer}
#chartbox{width:100%;height:540px;border:1px solid #21262d;border-radius:8px;overflow:hidden}
#chartinfo{color:#8b949e;font-size:12px;margin-bottom:8px}
#chartinfo b{color:#e6edf3}
#bteqbox{width:100%;height:380px;border:1px solid #21262d;border-radius:8px;overflow:hidden;margin-bottom:8px}
.cards{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:10px 14px;min-width:130px;flex:1}
.card .k{color:#8b949e;font-size:12px;margin-bottom:4px}
.card .v{font-size:20px;font-weight:700;color:#e6edf3}
.card .s{color:#8b949e;font-size:11px;margin-top:2px}
.sug{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px 18px;margin-bottom:16px;font-size:13px;line-height:1.7}
.sug ol,.sug ul{margin:0;padding-left:20px}
.sug li{margin-bottom:6px}
.tklink{color:#58a6ff;cursor:pointer;text-decoration:none}
.tklink:hover{text-decoration:underline}
</style>""" + ("<style>" + frag["css"] + "</style>" if frag else ""))
    lwc_path = BASE / "lightweight-charts.standalone.production.js"
    lwc = lwc_path.read_text() if lwc_path.exists() else ""
    chart_js_path = BASE / "chart_tab.js"
    chart_js = chart_js_path.read_text() if chart_js_path.exists() else ""
    bt_js_path = BASE / "backtest_tab.js"
    bt_js = bt_js_path.read_text() if bt_js_path.exists() else ""
    parts.append(("<script>" + lwc + "</scr" + "ipt>" if lwc else "") + "</head><body>")
    parts.append("<h1>LEAP 扫描 Dashboard</h1>")
    parts.append('<div class="sub">数据日期 ' + stamp + ' ｜ Yahoo 免费行情＋期权链 ｜ 技术形态筛选，仅供参考，不构成买卖建议</div>')
    parts.append("""<div class="tabs">
<button class="active" onclick="tab('scan')">评级扫描</button>
<button onclick="tab('entry')">入场建议</button>
<button onclick="tab('chains')">期权链</button>
<button onclick="tab('news')">新闻</button>
<button onclick="tab('stock')">正股基本面</button>
<button onclick="tab('chart')">缠论图表</button>
<button onclick="tab('backtest')">策略回测</button>
</div>
<div id="p-scan"></div>
<div id="p-entry" style="display:none"></div>
<div id="p-chains" style="display:none"></div>
<div id="p-news" style="display:none"></div>
<div id="p-backtest" style="display:none"></div>
<div id="p-stock" style="display:none">""" + (frag["body"] if frag else '<div class="warn">暂无正股数据</div>') + """</div>
<div id="p-chart" style="display:none">
<div class="chartctl">
<select id="chtk"></select>
<div class="tfbtns" id="tfbtns"></div>
</div>
<div class="chartctl ovl">
<label><input type="checkbox" id="ov_pen" checked onchange="toggleOv()"> 笔</label>
<label><input type="checkbox" id="ov_zs" checked onchange="toggleOv()"> 中枢</label>
<label><input type="checkbox" id="ov_fx" checked onchange="toggleOv()"> 分型</label>
<label><input type="checkbox" id="ov_ma" checked onchange="toggleOv()"> 均线</label>
<label><input type="checkbox" id="ov_sig" checked onchange="toggleOv()"> 买卖点</label>
<label><input type="checkbox" id="ov_dip" checked onchange="toggleOv()"> 海底捞月</label>
</div>
<div id="chartinfo"></div>
<div id="chartbox"></div>
<div class="warn" style="margin-top:10px">缠论为简化版（分型→笔→中枢→背驰→买卖点），买卖点为每笔终点处机械重算的历史信号；海底捞月标记仅日线。技术形态展示，不构成买卖建议。</div>
</div>
<script>
const DATA = """ + payload + """;
const ORDER={S:0,A:1,B:2,C:3,D:4};
function tab(id){document.querySelectorAll('.tabs button').forEach(function(b){if(b.getAttribute('onclick')==="tab('"+id+"')")b.classList.add('active');else b.classList.remove('active');});['scan','entry','chains','news','stock','chart','backtest'].forEach(t=>{document.getElementById('p-'+t).style.display=t===id?'block':'none';});if(id==='chart'&&typeof initChartTab==='function')initChartTab();if(id==='backtest'&&typeof initBacktest==='function')initBacktest();}
function gotoChart(t){tab('chart');var s=document.getElementById('chtk');if(s){s.value=t;loadChart();}}
function pct(x){return x==null?'—':(x*100).toFixed(1)+'%';}
function money(x){return x==null?'—':'$'+Number(x).toFixed(2);}
(function(){
  const s=DATA.scan;const el=document.getElementById('p-scan');
  if(!s.results){el.innerHTML='<div class="warn">暂无扫描数据</div>';return;}
  let h='<div class="warn">评级：S=形态全过且IV不贵 / A=形态全过 / B=观察 / C=趋势完好 / D=趋势走弱 ｜ 海底捞月：趋势→回调5-15%→20/50天线不破→反弹收复≥50%→动量确认 ｜ 缠论（简化版）：一买=底分型+底背驰 / 二买=回踩不破前低 / 三买=突破中枢回踩不进；<b style="color:#3fb950">✦</b>=与海底捞月共振（B+缠论买点→A），悬停看中枢/笔 ｜ <b style="color:#d4a017">⚠</b>=IV/RV数据缺失或异常（DQ）</div>';
  Object.keys(s.sectors||{}).forEach(function(sec){
    const ts=(s.sectors[sec]||[]).filter(t=>s.results[t]);
    ts.sort((a,b)=>((ORDER[s.results[a].rating]!=null?ORDER[s.results[a].rating]:5)-(ORDER[s.results[b].rating]!=null?ORDER[s.results[b].rating]:5)));
    if(!ts.length)return;
    h+='<div class="sect">'+sec+'</div><table><tr><th>Ticker</th><th>评级</th><th>形态分</th><th>缠论</th><th>现价</th><th>技术状态</th><th>回调/收复</th><th>20天线</th><th>50天线</th><th>200天线</th><th>RSI</th><th>ATR</th><th>RS20</th><th>IV</th><th>RV60</th><th>IV/RV</th><th>DQ</th></tr>';
    ts.forEach(function(t){const r=s.results[t],d=r.detail||{};
      var chg=r.score_chg;var chgs=chg==null?'':(chg>0?' <span style="color:#3fb950">▲'+chg+'</span>':(chg<0?' <span style="color:#f85149">▼'+(-chg)+'</span>':''));
      var cs=d.chan_signal||'—';
      if(d.chan_beichi)cs+='·'+d.chan_beichi;
      if(r.chan_resonance)cs+='✦';
      var cst=r.chan_resonance?'color:#3fb950;font-weight:700':'';
      var cti='笔:'+(d.chan_pen==='up'?'向上':(d.chan_pen==='down'?'向下':'—'));
      if(d.chan_zhongshu)cti+=' 中枢['+d.chan_zhongshu.zd+'~'+d.chan_zhongshu.zg+']';
      if(d.dip_fractal_ok)cti+=' 底分型确认';
      if(r.rating_upgraded)cti+=' B→A缠论升级';
      h+='<tr><td><a class="tklink" onclick="gotoChart(\\'"+t+"\\')"><b>'+t+'</b></a></td><td><span class="badge '+r.rating+'">'+r.rating+'</span></td><td class="num">'+(r.score!=null?r.score:'—')+chgs+'</td><td style="'+cst+'" title="'+cti+'">'+cs+'</td><td class="num">'+money(d.close)+'</td><td>'+(d.tech_state||'—')+'</td><td class="num">'+(d.dip_pct!=null?d.dip_pct+'% / '+d.retrace_pct+'%':'—')+'</td><td class="num">'+money(d.sma20)+'</td><td class="num">'+money(d.sma50)+'</td><td class="num">'+money(d.sma200)+'</td><td class="num">'+(d.rsi!=null?d.rsi:'—')+'</td><td class="num">'+(d.atr_pct!=null?d.atr_pct+'%':'—')+'</td><td class="num">'+(r.rs20!=null?(r.rs20>0?'+':'')+r.rs20+'%':'—')+'</td><td class="num">'+pct(r.iv)+'</td><td class="num">'+pct(r.rv60)+'</td><td class="num">'+(r.iv_rv!=null?r.iv_rv:'—')+'<td>'+(r.dq_flag?'<span style="color:#d4a017;font-weight:700">&#9888;'+(r.dq_issues||[]).join('/')+'</span>':'<span class="num">-</span>')+'</td></tr>';});
    h+='</table>';
  });
  el.innerHTML=h;
})();
(function(){
  const e=DATA.entry;const el=document.getElementById('p-entry');
  if(!e.rows||!e.rows.length){el.innerHTML='<div class="warn">暂无入场建议数据</div>';return;}
  let h='<div class="warn">正股建议：<b style="color:#3fb950">买入</b>=形态全过+IV不贵（S）或缠论买点确认（A） / <b style="color:#d4a017">小批建仓</b>=缺精确买点、RSI≥75超买分批、B+缠论买点 / 观察=缺入场形态、趋势走弱、一卖或顶背驰等回调、数据缺失 ｜ LEAP口径：约1年期ATM call（与回测一致）；IV缺失/异常（&lt;5%）或IV偏贵（IV/RV&gt;1.5）时暂不推荐。机械规则输出，不构成买卖建议。</div>';
  h+='<table><tr><th>Ticker</th><th>评级</th><th>正股建议</th><th>LEAP call 推荐</th><th>依据</th></tr>';
  e.rows.forEach(function(r){
    var sc=r.stock==='买入'?'color:#3fb950;font-weight:700':(r.stock==='小批建仓'?'color:#d4a017':'color:#8b949e');
    var why=r.stock_why||'';
    if(r.leap_why&&r.leap!=='—')why+=' ｜ LEAP：'+r.leap_why;
    h+='<tr><td><a class="tklink" onclick="gotoChart(\\''+r.ticker+'\\')"><b>'+r.ticker+'</b></a></td><td><span class="badge '+r.rating+'">'+r.rating+'</span></td><td style="'+sc+'">'+r.stock+'</td><td class="num">'+r.leap+'</td><td style="white-space:normal;min-width:260px">'+why+'</td></tr>';
  });
  el.innerHTML=h+'</table>';
})();
(function(){
  const c=DATA.chains;const el=document.getElementById('p-chains');
  const ts=Object.keys(c).filter(t=>c[t]&&c[t].chains);
  if(!ts.length){el.innerHTML='<div class="warn">暂无期权链数据</div>';return;}
  el.innerHTML='<select id="tk" onchange="showChain()">'+ts.map(t=>'<option>'+t+'</option>').join('')+'</select><div id="chainbox"></div>';
  window.showChain=function(){
    const t=document.getElementById('tk').value,e=c[t];
    const ladder=(e.ladder&&e.ladder.length)?e.ladder:[{moneyness:'105%'},{moneyness:'110%'},{moneyness:'115%'},{moneyness:'120%'},{moneyness:'125%'},{moneyness:'130%'}];
    let x='<div class="sect">'+t+'（'+(e.sector||'')+'）现价 $'+e.spot+' ｜ RV20 '+pct(e.rv20)+' ｜ RV60 '+pct(e.rv60)+'</div>';
    x+='<div class="warn">OTM call 按现价 +5% 步长取 105%~130% 六档，列头为实际行权价</div>';
    x+='<table><tr><th>到期</th>'+ladder.map(s=>'<th>$'+(s.strike!=null?Number(s.strike).toFixed(1):s.moneyness)+'</th>').join('')+'</tr>';
    ["2027-01","2027-03","2027-06","2027-09","2027-12","2028-01"].forEach(function(px){
      const ch=e.chains[px]||{};
      const cell=function(k){const d=ch[k];if(!d)return '—';return 'IV '+pct(d.iv)+'｜mid $'+Number(d.mid).toFixed(2)+'｜OI '+d.oi;};
      x+='<tr><td>'+(ch.expiry||px)+'</td>'+ladder.map(s=>'<td class="num">'+cell(s.moneyness)+'</td>').join('')+'</tr>';
    });
    document.getElementById('chainbox').innerHTML=x+'</table>';
  };
  showChain();
})();
(function(){
  const n=DATA.news;const el=document.getElementById('p-news');
  if(!n.tickers){el.innerHTML='<div class="warn">暂无新闻数据</div>';return;}
  let h='<div class="warn">【重大】= 命中财报/指引/评级/并购/监管/宏观关键词</div><div class="sect">宏观 / 市场</div>';
  (n.macro||[]).forEach(function(m){h+='<div class="ntitle">'+(m.impact?'<span class="impact">【重大】</span>':'')+'<a href="'+m.link+'" target="_blank">'+m.title+'</a> <span class="nmeta">'+m.time+' '+m.publisher+'</span></div>';});
  Object.keys(n.tickers).forEach(function(t){
    const e=n.tickers[t];if(!e.news||!e.news.length)return;
    h+='<div class="sect">'+t+'（'+e.sector+'）</div>';
    e.news.slice().sort((a,b)=>((b.impact?1:0)-(a.impact?1:0))).forEach(function(m){h+='<div class="ntitle">'+(m.impact?'<span class="impact">【重大】</span>':'')+'<a href="'+m.link+'" target="_blank">'+m.title+'</a> <span class="nmeta">'+m.time+' '+m.publisher+'</span></div>';});
  });
  el.innerHTML=h;
})();
</script>
""" + (frag["js"] if frag else "") + ("""
<script>
""" + chart_js + """
</script>""" if chart_js else "") + ("""
<script>
""" + bt_js + """
</script>""" if bt_js else "") + """
</body>
</html>""")
    out = BASE / "dashboard.html"
    out.write_text("\n".join(parts))
    print("dashboard written: %s (%d KB)" % (out, len("\n".join(parts)) // 1024))


if __name__ == "__main__":
    main()
