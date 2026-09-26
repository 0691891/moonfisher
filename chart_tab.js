/* 缠论图表页签：多周期 K 线 + 笔 / 中枢 / 分型 / 均线 / 买卖点 / 海底捞月 */
const CHTF = [["1d","日线"],["1wk","周线"],["5m","5分"],["15m","15分"],["30m","30分"],["1h","1小时"],["4h","4小时"]];
let chTF = "1d", chChart = null, chCandle = null, chOv = {}, chInit = false, chData = null;

function tfLabel(tf){ const f = CHTF.find(x=>x[0]===tf); return f ? f[1] : tf; }

function initChartTab(){
  if (chInit) { loadChart(); return; }
  chInit = true;
  const ts = Object.keys((DATA.scan && DATA.scan.results) || {}).sort();
  document.getElementById('chtk').innerHTML = ts.map(t=>'<option>'+t+'</option>').join('');
  document.getElementById('tfbtns').innerHTML = CHTF.map(x=>'<button data-tf="'+x[0]+'" onclick="setTF(\''+x[0]+'\')">'+x[1]+'</button>').join('');
  markTF();
  const el = document.getElementById('chartbox');
  new ResizeObserver(()=>{ if(chChart) chChart.applyOptions({width: el.clientWidth}); }).observe(el);
  const sel = document.getElementById('chtk');
  sel.addEventListener('change', loadChart);
  loadChart();
}
function setTF(tf){ chTF = tf; markTF(); loadChart(); }
function markTF(){ document.querySelectorAll('#tfbtns button').forEach(b=>b.classList.toggle('active', b.dataset.tf===chTF)); }

function loadChart(){
  const t = document.getElementById('chtk').value;
  if(!t) return;
  document.getElementById('chartinfo').textContent = '加载中 ' + t + ' ' + tfLabel(chTF) + ' …';
  fetch('charts/' + t + '_' + chTF + '.json')
    .then(r=>{ if(!r.ok) throw new Error('no data'); return r.json(); })
    .then(d=>{ chData = d; drawChart(d); })
    .catch(e=>{
      document.getElementById('chartinfo').textContent =
        '暂无 ' + t + ' ' + tfLabel(chTF) + ' 图表数据：请用「文件」方式把 dashboard.html 与同目录 charts/ 一起打开，或等下次扫描生成。';
      if(chChart){ chChart.remove(); chChart = null; }
    });
}

function drawChart(d){
  const el = document.getElementById('chartbox');
  if(typeof LightweightCharts === 'undefined'){
    document.getElementById('chartinfo').textContent = '图表库未加载'; return;
  }
  if(chChart) chChart.remove();
  chOv = {};
  chChart = LightweightCharts.createChart(el, {
    width: el.clientWidth, height: 540,
    layout: { background: { color: '#0d1117' }, textColor: '#8b949e' },
    grid: { vertLines: { color: '#161b22' }, horzLines: { color: '#161b22' } },
    timeScale: { timeVisible: true, secondsVisible: false },
    crosshair: { vertLine: { color: '#30363d' }, horzLine: { color: '#30363d' } }
  });
  chCandle = chChart.addCandlestickSeries({
    upColor: '#3fb950', downColor: '#f85149',
    wickUpColor: '#3fb950', wickDownColor: '#f85149', borderVisible: false
  });
  chCandle.setData(d.candles.map(c=>({time:c.t, open:c.o, high:c.h, low:c.l, close:c.c})));

  // 笔：端点折线
  if(d.pens.length){
    const pts = [{time: d.pens[0].t0, value: d.pens[0].p0}];
    d.pens.forEach(p=>pts.push({time:p.t1, value:p.p1}));
    chOv.pen = chChart.addLineSeries({color:'#e3b341', lineWidth:2, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false});
    chOv.pen.setData(pts);
  }
  // 中枢：上沿/下沿虚线
  chOv.zs = [];
  d.zhongshu.forEach(z=>{
    const up = chChart.addLineSeries({color:'rgba(248,81,73,0.85)', lineWidth:1, lineStyle:LightweightCharts.LineStyle.Dashed, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false});
    up.setData([{time:z.t0, value:z.zg},{time:z.t1, value:z.zg}]);
    const dn = chChart.addLineSeries({color:'rgba(63,185,80,0.85)', lineWidth:1, lineStyle:LightweightCharts.LineStyle.Dashed, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false});
    dn.setData([{time:z.t0, value:z.zd},{time:z.t1, value:z.zd}]);
    chOv.zs.push(up, dn);
  });
  // 均线
  if(d.sma20.length){
    chOv.ma20 = chChart.addLineSeries({color:'#58a6ff', lineWidth:1, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false});
    chOv.ma20.setData(d.sma20.map(p=>({time:p.t, value:p.v})));
  }
  if(d.sma50.length){
    chOv.ma50 = chChart.addLineSeries({color:'#d4a017', lineWidth:1, priceLineVisible:false, lastValueVisible:false, crosshairMarkerVisible:false});
    chOv.ma50.setData(d.sma50.map(p=>({time:p.t, value:p.v})));
  }

  buildMarkers();
  toggleOv();
  chChart.timeScale().fitContent();

  // 信息条
  const L = d.last;
  let info = '<b>' + d.ticker + '</b> ' + tfLabel(d.tf) + ' ｜ 收 <b>$' + L.close + '</b> ｜ ' + d.n_bars + '根K线';
  if(L.signal){
    const bull = ["一买","二买","三买"].indexOf(L.signal) >= 0;
    info += ' ｜ 缠论 <b style="color:' + (bull ? '#3fb950' : '#f85149') + '">' + L.signal + '</b>';
  }
  if(L.beichi) info += ' ' + L.beichi;
  info += ' ｜ 笔' + (L.pen_dir==='up' ? '向上' : (L.pen_dir==='down' ? '向下' : '—'));
  if(d.dip) info += ' ｜ 近90日高 $' + d.dip.high + ' → 低 $' + d.dip.low + ' → 收复 ' + d.dip.retrace_pct + '%';
  info += ' ｜ <span style="color:#6e7681">' + d.built + '</span>';
  document.getElementById('chartinfo').innerHTML = info;
}

function buildMarkers(){
  if(!chData || !chCandle) return;
  const d = chData, mk = [];
  const fF = document.getElementById('ov_fx').checked,
        fS = document.getElementById('ov_sig').checked,
        fD = document.getElementById('ov_dip').checked,
        fZ = document.getElementById('ov_zs').checked;
  if(fF) d.fractals.forEach(f=>mk.push({
    time: f.t, position: f.kind==='bottom' ? 'belowBar' : 'aboveBar',
    color: f.kind==='bottom' ? '#3fb950' : '#f85149',
    shape: f.kind==='bottom' ? 'arrowUp' : 'arrowDown'
  }));
  if(fZ) d.zhongshu.forEach(z=>mk.push({
    time: z.t0, position: 'aboveBar', color: '#8b949e', shape: 'circle',
    text: '中枢' + z.zd + '~' + z.zg
  }));
  if(fS) d.signals.forEach(s=>mk.push({
    time: s.t, position: s.side==='buy' ? 'belowBar' : 'aboveBar',
    color: s.side==='buy' ? '#3fb950' : '#f85149',
    shape: s.side==='buy' ? 'arrowUp' : 'arrowDown', text: s.sig
  }));
  if(fD && d.dip){
    mk.push({time: d.dip.high_t, position: 'aboveBar', color: '#8b949e', shape: 'circle', text: '高 ' + d.dip.high});
    mk.push({time: d.dip.low_t, position: 'belowBar', color: '#3fb950', shape: 'circle', text: '捞月 ' + d.dip.low});
  }
  mk.sort((a,b)=>a.time - b.time);
  chCandle.setMarkers(mk);
}

function toggleOv(){
  buildMarkers();
  const v = id=>document.getElementById(id).checked;
  if(chOv.pen) chOv.pen.applyOptions({visible: v('ov_pen')});
  (chOv.zs || []).forEach(s=>s.applyOptions({visible: v('ov_zs')}));
  if(chOv.ma20) chOv.ma20.applyOptions({visible: v('ov_ma')});
  if(chOv.ma50) chOv.ma50.applyOptions({visible: v('ov_ma')});
}
