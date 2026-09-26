/* 策略回测页签：渲染 DATA.backtest（指标/参数/建议）与 DATA.btequity（净值曲线）。 */
function initBacktest(){
  if(window._btInit)return;window._btInit=true;
  var el=document.getElementById('p-backtest');
  var r=(typeof DATA!=="undefined"&&DATA.backtest)||{};
  if(!r.metrics_base){el.innerHTML='<div class="warn">暂无回测数据，请先运行 backtest.py 生成。</div>';return;}
  var mb=r.metrics_base,mc=r.metrics_chan,ms=r.metrics_spy,mq=r.metrics_qqq||{},
      ml=r.metrics_leap||{},vm=r.vs_market||{},vsb=r.vs_benchmarks||{};
  function pc(x,d){if(x==null||!isFinite(x))return '—';return (x*100).toFixed(d==null?1:d)+'%';}
  function f2(x){return x==null||!isFinite(x)?'—':Number(x).toFixed(2);}
  function f3(x){return x==null||!isFinite(x)?'—':Number(x).toFixed(3);}
  function card(k,v,sub){return '<div class="card"><div class="k">'+k+'</div><div class="v">'+v+'</div>'+(sub?'<div class="s">'+sub+'</div>':'')+'</div>';}
  function row(k,fb,fc,fs,fq){return '<tr><td>'+k+'</td><td class="num">'+fb+'</td><td class="num">'+fc+'</td><td class="num">'+fs+'</td>'+(fq!==undefined?'<td class="num">'+fq+'</td>':'')+'</tr>';}
  var h='';
  h+='<div class="warn">正股策略 = 扫描器「海底捞月」ok（趋势/海底形态/均线完好/捞月反弹/动量五条件全过）→ 次日开盘买入；'
    +'持有'+r.params_base.hold+'天或 -'+Math.round(r.stop*100)+'% 止损；等权、最多同时持有 '+r.max_pos+' 只。'
    +'回测区间 '+r.period.start+' ~ '+r.period.end+'（'+r.period.n_tickers+' 只标的，'+r.period.n_days+' 个交易日）。'
    +'回测不代表未来收益，技术筛选仅供参考，不构成买卖建议。</div>';
  h+='<div class="cards">'
    +card('总收益',pc(mb.total),'年化 '+pc(mb.cagr))
    +card('夏普比率',f2(mb.sharpe),'波动率 '+pc(mb.vol))
    +card('最大回撤',pc(mb.max_dd),mb.dd_days+' 天走完')
    +card('胜率',pc(mb.win_rate),mb.n_trades+' 笔交易')
    +card('盈亏因子',f2(mb.profit_factor),'期望 '+pc(mb.expectancy))
    +card('P&L ÷ σ',f3(mb.pnl_by_std),'每笔收益风险比')
    +'</div>';
  // ---- 策略 vs 大盘（SPY / QQQ） ----
  h+='<div class="sect">策略 vs 大盘</div><table><tr><th>指标</th><th>基础策略</th><th>+缠论确认</th><th>SPY 买入持有</th><th>QQQ 买入持有</th></tr>';
  h+=row('总收益',pc(mb.total),pc(mc.total),pc(ms.total),pc(mq.total));
  h+=row('年化收益',pc(mb.cagr),pc(mc.cagr),pc(ms.cagr),pc(mq.cagr));
  h+=row('年化波动',pc(mb.vol),pc(mc.vol),pc(ms.vol),pc(mq.vol));
  h+=row('夏普',f2(mb.sharpe),f2(mc.sharpe),f2(ms.sharpe),f2(mq.sharpe));
  h+=row('最大回撤',pc(mb.max_dd),pc(mc.max_dd),pc(ms.max_dd),pc(mq.max_dd));
  h+=row('交易次数',mb.n_trades,mc.n_trades,'—','—');
  h+=row('胜率',pc(mb.win_rate),pc(mc.win_rate),'—','—');
  h+=row('平均盈利 / 平均亏损',pc(mb.avg_win)+' / '+pc(mb.avg_loss),pc(mc.avg_win)+' / '+pc(mc.avg_loss),'—','—');
  h+=row('盈亏因子',f2(mb.profit_factor),f2(mc.profit_factor),'—','—');
  h+=row('P&L ÷ σ',f3(mb.pnl_by_std),f3(mc.pnl_by_std),'—','—');
  h+='</table>';
  // ---- 跑赢指数 ----
  function exrow(label,key,bench,benchDD){
    var v=vsb[key];if(!v)return '';
    var s=key.indexOf('base')===0?mb:(key.indexOf('chan')===0?mc:ml);
    return '<tr><td>'+label+'</td><td class="num">'+(v.excess_cagr>=0?'+':'')+pc(v.excess_cagr)+'</td>'
      +'<td class="num">'+pc(s.max_dd)+' vs '+pc(benchDD)+'</td>'
      +'<td class="num">'+f3(v.beta)+'</td><td class="num">'+(v.alpha>=0?'+':'')+pc(v.alpha)+'</td>'
      +'<td class="num">'+f3(v.corr)+'</td></tr>';
  }
  h+='<div class="sect">跑赢指数多少（超额年化 / 最大回撤对比）</div>'
    +'<table><tr><th></th><th>超额年化</th><th>最大回撤（策略 vs 指数）</th><th>Beta</th><th>年化Alpha</th><th>相关性</th></tr>'
    +exrow('基础策略 vs SPY','base_vs_spy',0,ms.max_dd)
    +exrow('基础策略 vs QQQ','base_vs_qqq',0,mq.max_dd)
    +exrow('+缠论确认 vs SPY','chan_vs_spy',0,ms.max_dd)
    +exrow('+缠论确认 vs QQQ','chan_vs_qqq',0,mq.max_dd)
    +exrow('LEAP策略 vs SPY','leap_vs_spy',0,ms.max_dd)
    +exrow('LEAP策略 vs QQQ','leap_vs_qqq',0,mq.max_dd)
    +'</table>';
  // ---- LEAP call swing 专区 ----
  var lp=r.params_leap||{};
  h+='<div class="sect">LEAP call swing（按评级选股）</div>'
    +'<div class="warn">选股：信号日对通过「海底捞月」ok 且有缠论买点（一/二/三买）的标的，'
    +'按技术评分（0–80 分：技术状态 35 + 回调形态 25 + 趋势保护 20，不含基本面）取 Top '+lp.top_k+'，次日开盘买入 1 年期平值 call。'
    +'每笔投入权益 '+Math.round((lp.alloc||0)*100)+'% 买期权费，最多同时 '+lp.max_pos+' 只；'
    +'持有 '+lp.hold+' 天或期权价值 -'+Math.round((lp.stop||0)*100)+'% 止损。'
    +'期权价为 Black-Scholes 合成（无历史期权链数据），r=4.25%，IV=过去60日实现波动率×1.15，每日收盘重估。'
    +'回测不代表未来收益，不构成买卖建议。</div>';
  h+='<div class="cards">'
    +card('总收益',pc(ml.total),'年化 '+pc(ml.cagr))
    +card('夏普比率',f2(ml.sharpe),'波动率 '+pc(ml.vol))
    +card('最大回撤',pc(ml.max_dd),ml.dd_days+' 天走完')
    +card('胜率',pc(ml.win_rate),ml.n_trades+' 笔交易')
    +card('盈亏因子',f2(ml.profit_factor),'期望 '+pc(ml.expectancy))
    +card('P&L ÷ σ',f3(ml.pnl_by_std),'每笔收益风险比')
    +card('相对SPY超额',((vsb.leap_vs_spy||{}).excess_cagr>=0?'+':'')+pc((vsb.leap_vs_spy||{}).excess_cagr),'相对QQQ '+(((vsb.leap_vs_qqq||{}).excess_cagr>=0?'+':'')+pc((vsb.leap_vs_qqq||{}).excess_cagr)))
    +'</div>';
  h+='<div class="sect">LEAP vs 正股策略 vs 大盘</div><table><tr><th>指标</th><th>LEAP call</th><th>基础正股策略</th><th>SPY</th><th>QQQ</th></tr>';
  h+=row('总收益',pc(ml.total),pc(mb.total),pc(ms.total),pc(mq.total));
  h+=row('年化收益',pc(ml.cagr),pc(mb.cagr),pc(ms.cagr),pc(mq.cagr));
  h+=row('年化波动',pc(ml.vol),pc(mb.vol),pc(ms.vol),pc(mq.vol));
  h+=row('夏普',f2(ml.sharpe),f2(mb.sharpe),f2(ms.sharpe),f2(mq.sharpe));
  h+=row('最大回撤',pc(ml.max_dd),pc(mb.max_dd),pc(ms.max_dd),pc(mq.max_dd));
  h+=row('胜率',pc(ml.win_rate),pc(mb.win_rate),'—','—');
  h+=row('盈亏因子',f2(ml.profit_factor),f2(mb.profit_factor),'—','—');
  h+=row('P&L ÷ σ',f3(ml.pnl_by_std),f3(mb.pnl_by_std),'—','—');
  h+='</table>';
  // ---- 净值曲线 ----
  h+='<div class="sect">净值曲线（归一化=100）</div><div id="bteqbox"></div>';
  // ---- 参数寻优 ----
  h+='<div class="sect">参数寻优（网格 '+((r.grid_top8||[]).length? 'Top 8':'')+'，按夏普排序）</div>';
  h+='<table><tr><th>#</th><th>回踩区间</th><th>收复≥</th><th>持有天数</th><th>夏普</th><th>Calmar</th><th>年化</th><th>最大回撤</th><th>交易数</th><th>胜率</th></tr>';
  (r.grid_top8||[]).forEach(function(g,i){
    var p=g.params;
    h+='<tr><td class="num">'+(i+1)+'</td><td class="num">'+Math.round(p.dip_lo*100)+'%-'+Math.round(p.dip_hi*100)+'%</td><td class="num">'+Math.round(p.retrace_min*100)+'%</td><td class="num">'+p.hold+'</td><td class="num">'+f2(g.sharpe)+'</td><td class="num">'+f2(g.calmar)+'</td><td class="num">'+pc(g.cagr)+'</td><td class="num">'+pc(g.max_dd)+'</td><td class="num">'+g.n_trades+'</td><td class="num">'+pc(g.win_rate)+'</td></tr>';
  });
  h+='</table>';
  h+='<div class="sect">优化建议</div><div class="sug"><ol>'
    +(r.suggestion||[]).map(function(s){return '<li>'+s+'</li>';}).join('')+'</ol></div>';
  function trTable(title,trs){
    var x='<div class="sect">'+title+'</div><table><tr><th>标的</th><th>买入</th><th>卖出</th><th>买入价</th><th>卖出价</th><th>收益</th><th>持有天</th><th>离场</th></tr>';
    (trs||[]).forEach(function(t){
      var c=t.ret>=0?'color:#3fb950':'color:#f85149';
      x+='<tr><td><b>'+t.ticker+'</b></td><td class="num">'+t.entry+'</td><td class="num">'+t.exit+'</td><td class="num">'+t.entry_px+'</td><td class="num">'+t.exit_px+'</td><td class="num" style="'+c+'">'+(t.ret>=0?'+':'')+pc(t.ret)+'</td><td class="num">'+t.days+'</td><td>'+t.why+'</td></tr>';
    });
    return x+'</table>';
  }
  h+=trTable('收益最高的 5 笔（正股）',r.best_trades||[]);
  h+=trTable('亏损最大的 5 笔（正股）',r.worst_trades||[]);
  h+=trTable('LEAP：收益最高的 5 笔',r.best_leap_trades||[]);
  h+=trTable('LEAP：亏损最大的 5 笔',r.worst_leap_trades||[]);
  h+='<div class="sect">回测假设</div><div class="sug"><ul>'
    +(r.assumptions||[]).map(function(s){return '<li>'+s+'</li>';}).join('')+'</ul></div>';
  el.innerHTML=h;

  // --- 净值曲线 ---
  var eq=(typeof DATA!=="undefined"&&DATA.btequity)||{};
  var box=document.getElementById('bteqbox');
  if(box&&eq.dates&&eq.dates.length&&window.LightweightCharts){
    var chart=LightweightCharts.createChart(box,{
      layout:{background:{color:'#0d1117'},textColor:'#8b949e',fontSize:11},
      grid:{vertLines:{color:'#161b22'},horzLines:{color:'#161b22'}},
      width:box.clientWidth,height:380,
      rightPriceScale:{borderColor:'#30363d'},
      timeScale:{borderColor:'#30363d',timeVisible:false}});
    var s1=chart.addLineSeries({color:'#58a6ff',lineWidth:2,title:'正股策略'});
    var sL=chart.addLineSeries({color:'#3fb950',lineWidth:2,title:'LEAP call'});
    var s2=chart.addLineSeries({color:'#8b949e',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:'SPY'});
    var s3=chart.addLineSeries({color:'#d29922',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,title:'QQQ'});
    var dd=chart.addHistogramSeries({color:'rgba(248,81,73,0.45)',priceScaleId:'dd',title:'回撤(正股)',priceFormat:{type:'percent'}});
    chart.priceScale('dd').applyOptions({scaleMargins:{top:0.82,bottom:0}});
    var d1=[],d2=[],d3=[],d4=[],d5=[];
    for(var i=0;i<eq.dates.length;i++){
      d1.push({time:eq.dates[i],value:eq.strat[i]*100});
      d2.push({time:eq.dates[i],value:(eq.leap&&eq.leap[i]!=null?eq.leap[i]:NaN)*100});
      d3.push({time:eq.dates[i],value:eq.spy[i]*100});
      d4.push({time:eq.dates[i],value:(eq.qqq&&eq.qqq.length?eq.qqq[i]:NaN)*100});
      d5.push({time:eq.dates[i],value:eq.drawdown[i],color:eq.drawdown[i]<-0.05?'rgba(248,81,73,0.6)':'rgba(248,81,73,0.3)'});
    }
    s1.setData(d1);sL.setData(d2);s2.setData(d3);s3.setData(d4);dd.setData(d5);
    chart.timeScale().fitContent();
    new ResizeObserver(function(){chart.applyOptions({width:box.clientWidth});}).observe(box);
  }
}
