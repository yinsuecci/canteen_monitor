import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowUpRight, BarChart3, ChevronRight, Clock3, Database, Layers3, MapPin, Radio, RefreshCw, Search, Settings2, Users, Wifi } from 'lucide-react';
import Chart from './Chart';
import Devices from './Devices';
import { demoPoints, demoSummary } from './demo';
import type { AP, Series, Summary } from './types';
import './styles.css';

const nav = [{id:'overview',label:'总览',icon:BarChart3},{id:'aps',label:'AP 管理',icon:Wifi},{id:'devices',label:'设备',icon:Radio},{id:'regions',label:'区域',icon:MapPin},{id:'settings',label:'设置',icon:Settings2}];
const time = (value?: string, seconds = false) => value ? new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',...(seconds?{second:'2-digit'}:{}),hour12:false}).format(new Date(value)) : '—';
const date = (value?: string) => value ? new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit'}).format(new Date(value)) : '—';
const number = (value: number | null | undefined) => value == null ? '—' : value;
function initialPage() { const page = location.hash.slice(1); return nav.some(n=>n.id===page)?page:'overview'; }
async function get<T,>(url: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, {signal});
  if (!response.ok) throw new Error(`请求失败 (${response.status})`);
  return response.json();
}

function App() {
  const [page,setPage] = useState(initialPage);
  const [demo,setDemo] = useState(false);
  const [summary,setSummary] = useState<Summary|null>(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(true);
  const [refresh,setRefresh] = useState(0);
  const [auto,setAuto] = useState(true);
  const [includeLocal,setIncludeLocal] = useState(false);
  const [query,setQuery] = useState('');
  const [band,setBand] = useState('');
  const [ssid,setSsid] = useState('');
  const [region,setRegion] = useState('');
  const [selected,setSelected] = useState('');
  const [hours,setHours] = useState(24);
  const [utilization,setUtilization] = useState(false);
  const [series,setSeries] = useState<Series[]>([]);
  const [chartLoading,setChartLoading] = useState(false);
  const [chartError,setChartError] = useState('');

  useEffect(()=>{ const change=()=>setPage(initialPage()); window.addEventListener('hashchange',change); return ()=>window.removeEventListener('hashchange',change); },[]);
  useEffect(()=>{
    const controller = new AbortController();
    let pending = false;
    setSummary(null); setError('');
    async function load() {
      if (pending) return;
      pending=true; setBusy(true);
      try { const data=demo?demoSummary():await get<Summary>('/api/dashboard/summary'+(includeLocal?'?include_local=true':''),controller.signal); if (!controller.signal.aborted) {setSummary(data);setError('');} }
      catch (e) {if (!controller.signal.aborted) setError(e instanceof Error?e.message:'连接失败');}
      finally {pending=false;if (!controller.signal.aborted) setBusy(false);}
    }
    void load();
    const timer=setInterval(()=>{if(auto && !document.hidden) void load();},15000);
    return ()=>{controller.abort();clearInterval(timer);};
  },[demo,refresh,auto,includeLocal]);

  const aps=summary?.aps??[];
  const chosen = aps.find(a=>a.bssid===selected)??aps[0];
  const second = aps.find(a=>a.bssid!==chosen?.bssid && a.collector_id===chosen?.collector_id);
  useEffect(()=>{
    const controller=new AbortController(); setSeries([]);setChartError('');
    if (!chosen) {setChartLoading(false);return ()=>controller.abort();}
    const targets=[chosen,...(second?[second]:[])]; setChartLoading(true);
    Promise.all(targets.map(async(a)=>{
      if(demo) return {name:a.bssid,points:demoPoints(a.station_count)};
      const result=await get<{points:Series['points'];truncated:boolean}>(`/api/aps/${a.bssid}/history?collector_id=${encodeURIComponent(a.collector_id)}&hours=${hours}`,controller.signal);
      return {name:a.bssid,...result};
    })).then(data=>{if(!controller.signal.aborted)setSeries(data);})
      .catch(()=>{if(!controller.signal.aborted)setChartError('趋势加载失败，请刷新重试');})
      .finally(()=>{if(!controller.signal.aborted)setChartLoading(false);});
    return ()=>controller.abort();
  },[chosen?.bssid,chosen?.collector_id,second?.bssid,hours,demo,summary?.timestamp]);

  const collectors=summary?.collectors??[];
  const collector=collectors.find(c=>c.collector_id===chosen?.collector_id)??collectors[0];
  const isOnline=collectors.some(c=>c.fresh && c.status==='success');
  const hasFailure=collectors.some(c=>c.status==='failed');
  const status=error?'连接异常':!summary?'加载中':isOnline?'在线':hasFailure?'扫描失败':collectors.length?'已过期':'待采集';
  const statusClass=isOnline&&!error?'good':'muted';
  const latest=collectors.map(c=>c.timestamp).sort().at(-1);
  const locations=[...new Set((summary?.registry??[]).map(a=>a.location_name).filter((x):x is string=>!!x))];
  const filtered=aps.filter(a=>(`${a.bssid} ${a.ssid}`.toLowerCase().includes(query.toLowerCase()))&&(!band||a.band===band)&&(!ssid||a.ssid===ssid)&&(!region||a.location_name===region));
  const confirmed=aps.filter(a=>a.confirmed&&a.location_name).length;
  const chartHasData=series.some(s=>s.points.some(p=>utilization?p.channel_utilization_raw!==null:p.station_count!==null));
  const navigate=(id:string)=>{location.hash=id;setPage(id);};
  const selectAP=(ap:AP)=>{setSelected(ap.bssid);navigate('overview');};
  const exportHistory=()=>{
    const data=series.flatMap(s=>s.points.map(p=>[s.name,p.timestamp,p.station_count??'',p.channel_utilization_raw??''].join(',')));
    const url=URL.createObjectURL(new Blob(['bssid,timestamp_utc,station_count,channel_utilization_raw\n'+data.join('\n')],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=demo?'demo-history.csv':'ap-history.csv';link.click();URL.revokeObjectURL(url);
  };

  function table(full=false) {
    return <section className={`panel ap-panel ${full?'full':''}`}>
      <div className="panel-head"><div className="heading-inline"><h2>AP 列表</h2><span className="count">{filtered.length}</span></div><label className="search"><Search size={16}/><span className="sr-only">搜索 BSSID 或 SSID</span><input placeholder="搜索 BSSID / SSID" value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
      {full&&<div className="filters"><label>频段<select value={band} onChange={e=>setBand(e.target.value)}><option value="">全部</option><option>2.4GHz</option><option>5GHz</option><option>6GHz</option></select></label><label>SSID<select value={ssid} onChange={e=>setSsid(e.target.value)}><option value="">全部</option>{[...new Set(aps.map(a=>a.ssid))].map(s=><option key={s}>{s}</option>)}</select></label><label>区域<select value={region} onChange={e=>setRegion(e.target.value)}><option value="">全部</option>{locations.map(l=><option key={l}>{l}</option>)}</select></label><button className="text-button" onClick={()=>{setQuery('');setBand('');setSsid('');setRegion('');}}>清除筛选</button></div>}
      <div className="table-scroll"><table><thead><tr><th>BSSID</th><th>SSID</th><th>频段</th>{full&&<><th>信道</th><th>信号</th></>}<th className="numeric">终端数</th><th className="numeric">利用率</th>{full&&<><th>区域</th><th>更新</th></>}</tr></thead><tbody>{(full?filtered:filtered.slice(0,6)).map(a=><tr key={a.bssid} className={a.bssid===chosen?.bssid?'selected-row':''}><td><button className="mac-link" onClick={()=>selectAP(a)} title="查看此 AP 趋势">{a.bssid}</button></td><td>{a.ssid||'隐藏网络'}</td><td><span className="band">{a.band??'—'}</span></td>{full&&<><td>{number(a.channel)}</td><td>{a.signal==null?'—':a.signal+'%'}</td></>}<td className="numeric station">{number(a.station_count)}</td><td className="numeric">{a.channel_utilization_percent==null?'—':a.channel_utilization_percent.toFixed(1)+'%'}</td>{full&&<><td>{a.location_name??'待确认'}</td><td className="mono">{date(a.timestamp)} {time(a.timestamp)}</td></>}</tr>)}</tbody></table></div>
      {!filtered.length&&<div className="empty compact"><Wifi size={25}/><p>{query||band||ssid||region?'没有匹配的 AP':'暂无扫描数据'}</p><span>未发现不等于终端数为零</span></div>}
      <div className="table-foot"><span>— 表示缺失 · 点击 BSSID 查看趋势</span>{!full&&<button className="text-button" onClick={()=>navigate('aps')}>查看全部 <ArrowUpRight size={14}/></button>}</div>
    </section>;
  }

  return <div className="shell">
    <aside className="sidebar"><a className="brand" href="#overview"><div className="brand-mark"><Radio size={20}/></div><span>Canteen<br/>Monitor<span className="brand-dot">.</span></span></a><div className="nav-label">工作空间</div><nav aria-label="主导航">{nav.map(n=><a href={'#'+n.id} key={n.id} aria-current={page===n.id?'page':undefined} className={page===n.id?'active':''}><n.icon size={19}/><span>{n.label}</span>{page===n.id&&<ChevronRight size={15} className="nav-chevron"/>}</a>)}</nav><div className="sidebar-foot"><div><span className={`dot ${statusClass}`}/>{demo?'演示工作空间':'本地工作空间'}</div></div></aside>
    <main><header className="topbar"><span>工作空间 <ChevronRight size={12}/> {nav.find(n=>n.id===page)?.label}</span><div><span className="timezone">Asia / Shanghai</span><span className="top-clock">{time(summary?.timestamp)}</span></div></header>
      <div className="content"><div className="page-heading"><div><h1>{({overview:'监测总览',aps:'AP 管理',devices:'采集设备',regions:'区域归属',settings:'采集设置'} as Record<string,string>)[page]}</h1>{page!=='overview'&&<p>{page==='aps'?'按 BSSID 查看无线广播。':page==='regions'?'采样点不等于安装点。':page==='devices'?'管理独立采集端。':'数据接收与显示偏好。'}</p>}</div><div className="header-actions"><button className={`mode-button ${demo?'demo':''}`} onClick={()=>{setDemo(!demo);setSelected('');setQuery('');setBand('');setSsid('');setRegion('');}}>{demo?'演示数据':'真实数据'}<ChevronRight size={13}/></button><button className="refresh" title="刷新数据" aria-label="刷新数据" onClick={()=>setRefresh(r=>r+1)} disabled={busy}><RefreshCw size={17} className={busy?'spinning':''}/></button></div></div>
      {demo&&<div className="notice demo-notice">演示模式 · 所有数值与曲线均为示例，不写入数据库。</div>}
      {error&&<div role="alert" className="notice error-notice">{error} · {summary?'当前保留上次结果，不代表实时状态。':'无法读取数据。'} <button onClick={()=>setRefresh(r=>r+1)}>重试</button></div>}
      {!demo&&summary&&!isOnline&&page!=='devices'&&<div className="notice">{hasFailure?'最近扫描失败，失败扫描不产生 AP 记录。':collectors.length?'采集数据已过期，以下为最后扫描记录。':'等待远程设备上报。'}{!collectors.length&&<button onClick={()=>navigate('devices')}>管理设备</button>}</div>}
      {(page==='overview'||page==='aps')&&<div className="metrics">{[{icon:Radio,label:'采集器',value:status,state:true},{icon:Wifi,label:'可见 AP',value:summary?aps.length:'—'},{icon:Layers3,label:'有效负载',value:summary?aps.filter(a=>a.station_count!==null).length:'—'},{icon:Clock3,label:'最近扫描',value:time(latest)}].map((m,i)=><section className="metric" key={m.label}><div className="metric-top"><span>{m.label}</span><m.icon size={19}/></div><div className={`metric-value ${i===3?'time-value':''}`}>{m.state&&<span className={`dot ${statusClass}`}/>} {m.value}</div></section>)}</div>}
      {page==='overview'&&<div className="dashboard-grid"><section className="panel chart-panel"><div className="panel-head"><div><h2>终端趋势 <span className="subtle">关联终端，非人数</span></h2></div><label className="range"><span className="sr-only">时间范围</span><select value={hours} onChange={e=>setHours(Number(e.target.value))}><option value={2}>近 2 小时</option><option value={24}>近 24 小时</option><option value={168}>近 7 天</option></select></label></div><div className="chart-toolbar"><div className="chart-tabs"><button className={!utilization?'chosen':''} onClick={()=>setUtilization(false)}>终端数</button><button className={utilization?'chosen':''} onClick={()=>setUtilization(true)}>利用率</button></div><div className="legend">{series.map((s,i)=><span key={s.name} title={s.name}><i className={i?'olive':''}/>{s.name.slice(-8)}</span>)}</div></div>
      {chartLoading?<div className="chart-placeholder">正在加载趋势…</div>:chartError?<div className="chart-placeholder" role="alert">{chartError}</div>:chartHasData?<Chart series={series} utilization={utilization}/>:<div className="chart-placeholder"><Activity size={30}/><p>该时段暂无有效数据</p><span>可扩大时间范围，或等待下一次扫描</span></div>}
      <div className="chart-foot"><span>上海时间 · 缺失值断开显示{series.some(s=>s.truncated)?' · 仅展示最近 10,000 条':''}</span><button className="text-button" onClick={exportHistory} disabled={!series.some(s=>s.points.length)}>导出 CSV <ArrowUpRight size={13}/></button></div></section>
      <div className="side-stack"><section className="panel status-panel"><div className="panel-head"><h2>采集状态</h2><Radio size={17}/></div><dl><div><dt>设备</dt><dd className="mono">{collector?.collector_id??summary?.collector_id??'—'}</dd></div><div><dt>状态</dt><dd><span className={`badge ${statusClass}`}>{collector?(collector.fresh&&collector.status==='success'?'在线':collector.status==='failed'?'失败':'已过期'):'待采集'}</span></dd></div><div><dt>采集间隔</dt><dd>{summary?.interval_seconds??'—'} 秒</dd></div></dl>{collector?.error&&<p className="scan-error">{collector.error}</p>}<div className="panel-note"><span className={`dot ${statusClass}`}/>{demo?'示例采集器':summary?.collection_enabled?'后台定时采集中':'独立采集 / 历史数据'}</div></section><section className="panel region-panel"><div className="panel-head"><h2>区域</h2><MapPin size={17}/></div><div className="region-status"><span>AP 归属</span><span className={`badge ${confirmed===aps.length&&aps.length?'good':'pending'}`}>{confirmed===aps.length&&aps.length?'已确认':'待确认'}</span></div><p>已确认 {confirmed} / {aps.length} 个 BSSID</p><button className="text-button" onClick={()=>navigate('regions')}>查看归属 <ArrowUpRight size={14}/></button></section></div>
      {table()}<section className="panel occupancy"><div className="panel-head"><h2>人数估计</h2><span className="tiny-label">待校准</span></div><div className="occupancy-empty"><div className="empty-icon"><Users size={29}/></div><h3>尚未启用</h3><p>等待人工计数校准</p></div></section></div>}
      {page==='aps'&&table(true)}
      {page==='devices'&&<Devices demo={demo}/>}
      {page==='regions'&&<section className="panel"><div className="panel-head"><h2>人工映射</h2><span className="subtle">{summary?.registry.length??0} 个已记录 BSSID</span></div><div className="table-scroll"><table><thead><tr><th>BSSID</th><th>SSID</th><th>区域</th><th>确认状态</th><th>置信度</th></tr></thead><tbody>{summary?.registry.map(r=><tr key={r.bssid}><td className="mono">{r.bssid}</td><td>{r.ssid}</td><td>{r.location_name??'未分配'}</td><td><span className={`badge ${r.confirmed?'good':'pending'}`}>{r.confirmed?'已确认':'待确认'}</span></td><td>{r.confidence==null?'—':Math.round(r.confidence*100)+'%'}</td></tr>)}</tbody></table></div>{!summary?.registry.length&&<div className="empty"><MapPin/><p>暂无 AP 映射</p></div>}<div className="table-foot">仅展示人工映射；不会根据 MAC 前缀推断位置。映射可使用现有 map 命令维护。</div></section>}
      {page==='settings'&&<div className="settings-grid"><section className="panel"><div className="panel-head"><h2>接收配置</h2><Settings2 size={18}/></div><dl><div><dt>工作模式</dt><dd>{summary?.collection_enabled?'本机采集（显式启用）':'远程设备接收'}</dd></div><div><dt>上传认证</dt><dd>设备专属 Bearer 密钥</dd></div><div><dt>存储时间</dt><dd>UTC</dd></div><div><dt>显示时区</dt><dd>Asia/Shanghai</dd></div></dl><button className="text-button padded" onClick={()=>navigate('devices')}>管理采集设备 <ArrowUpRight size={14}/></button></section><section className="panel"><div className="panel-head"><h2>界面偏好</h2></div><label className="toggle-row"><span>自动刷新<small>每 15 秒读取一次，不触发 Wi-Fi 扫描</small></span><input aria-label="自动刷新" type="checkbox" checked={auto} onChange={e=>setAuto(e.target.checked)}/></label><label className="toggle-row"><span>显示本机历史<small>仅查看旧数据，不启动本机扫描</small></span><input aria-label="显示本机历史" type="checkbox" checked={includeLocal} onChange={e=>setIncludeLocal(e.target.checked)}/></label><div className="settings-note"><Database size={22}/><h3>采集与展示分离</h3><p>扫描在独立设备上完成，服务器仅接收和存储。</p></div></section></div>}
      </div>
    </main></div>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><App/></StrictMode>);
