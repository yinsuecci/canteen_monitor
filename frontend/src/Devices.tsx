import { useEffect, useState } from 'react';
import { Copy, Download, KeyRound, Plus, Radio, RefreshCw } from 'lucide-react';

type Device = {collector_id:string;name:string;location:string;source:string;interval_seconds:number;enabled:boolean;online:boolean;data_fresh:boolean;last_received_at:string|null;last_observed_at:string|null;last_status:string|null;last_error:string|null};
const stamp=(v:string|null)=>v?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(v)):'—';
const blank={collector_id:'',name:'',location:'',source:'esp32_c5',interval_seconds:60};
export default function Devices({demo}:{demo:boolean}) {
  const [devices,setDevices]=useState<Device[]>([]);
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [busy,setBusy]=useState(false);
  const [form,setForm]=useState(blank);
  const [adding,setAdding]=useState(false);
  const [editing,setEditing]=useState<Device|null>(null);
  const [credential,setCredential]=useState<{collector_id:string;token:string}|null>(null);
  const [revision,setRevision]=useState(0);
  const [server,setServer]=useState(location.origin);
  const local=['127.0.0.1','localhost','[::1]'].includes(location.hostname);
  useEffect(()=>{
    const controller=new AbortController();
    if(demo){setDevices([]);return ()=>controller.abort();}
    async function load(){
      try{const res=await fetch('/api/devices',{signal:controller.signal});if(!res.ok)throw new Error('设备列表读取失败');const result=await res.json();if(!controller.signal.aborted)setDevices(result);}
      catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'设备列表读取失败');}
    }
    void load();const timer=setInterval(()=>{if(!document.hidden)void load();},15000);
    return ()=>{controller.abort();clearInterval(timer);};
  },[demo,revision]);
  async function mutate(path:string,method:string,body?:unknown){
    setBusy(true);setError('');setNotice('');
    try{
      const res=await fetch(path,{method,headers:{'Content-Type':'application/json','X-Local-Admin':'1'},...(body?{body:JSON.stringify(body)}:{})});
      if(!res.ok){throw new Error(res.status===409?'设备 ID 已存在，请使用新 ID':res.status===403?'仅允许在服务器本机管理设备':res.status===422?'请检查字段格式与范围':`操作失败 (${res.status})`);}
      const result=await res.json();setRevision(v=>v+1);return result;
    }catch(e){setError(e instanceof Error?e.message:'操作失败');return null;}
    finally{setBusy(false);}
  }
  async function create(){const result=await mutate('/api/devices','POST',form);if(result){setCredential(result);setAdding(false);setForm(blank);}}
  async function save(device:Device){const result=await mutate(`/api/devices/${device.collector_id}`,'PUT',{name:device.name,location:device.location,interval_seconds:device.interval_seconds,enabled:device.enabled});if(result){setEditing(null);setNotice('设备设置已保存');}}
  async function rotate(device:Device){if(!window.confirm(`重置 ${device.name} 的密钥？旧密钥会立即失效。`))return;const result=await mutate(`/api/devices/${device.collector_id}/rotate-key`,'POST');if(result)setCredential(result);}
  function download(){if(!credential)return;let url:URL;try{url=new URL(server);if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error();}catch{setError('请输入有效的 HTTP(S) 服务器地址');return;}const content={schema_version:1,collector_id:credential.collector_id,server_url:url.origin,token:credential.token,endpoint:'/api/collector/observations'};const objectUrl=URL.createObjectURL(new Blob([JSON.stringify(content,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=objectUrl;a.download=`${credential.collector_id}-credentials.json`;a.click();URL.revokeObjectURL(objectUrl);}
  return <div className="device-page">
    {demo&&<div className="notice">演示模式不创建或修改设备。切换到真实数据后管理。</div>}
    {!local&&<div className="notice">设备管理操作仅在服务器本机开放；当前可查看设备状态。</div>}
    {error&&<div className="notice error-notice" role="alert">{error}</div>}
    {notice&&<div className="notice" role="status">{notice}</div>}
    {credential&&<section className="panel credential-panel"><div className="panel-head"><h2>设备密钥 · 仅本次显示</h2><KeyRound size={18}/></div><p className="credential-id">{credential.collector_id}</p><code className="secret">{credential.token}</code><div className="device-actions"><button className="secondary-button" onClick={async()=>{try{await navigator.clipboard.writeText(credential.token);setNotice('密钥已复制');}catch{setError('复制失败，可以下载设备凭据');}}}><Copy size={15}/>复制密钥</button><button className="secondary-button" onClick={()=>setCredential(null)}>关闭密钥</button></div><label className="device-field">设备可达的服务器地址<input value={server} onChange={e=>setServer(e.target.value)}/></label><p className="device-hint">远程设备不能使用 127.0.0.1。公网部署使用 HTTPS；凭据文件包含密钥，请妥善保存。</p><button className="secondary-button" onClick={download}><Download size={15}/>下载凭据</button></section>}
    <section className="panel"><div className="panel-head"><div className="heading-inline"><h2>采集设备</h2><span className="count">{devices.length}</span></div><div className="device-actions"><button className="secondary-button" aria-label="刷新设备" onClick={()=>setRevision(v=>v+1)}><RefreshCw size={15}/></button><button className="primary-button" disabled={demo||!local||busy} onClick={()=>setAdding(!adding)}><Plus size={15}/>{adding?'取消':'添加设备'}</button></div></div>
    {adding&&<form className="device-form" onSubmit={e=>{e.preventDefault();void create();}}><label className="device-field">设备 ID<input required pattern="[a-zA-Z0-9_-]{1,64}" maxLength={64} placeholder="canteen_probe_01" value={form.collector_id} onChange={e=>setForm({...form,collector_id:e.target.value})}/></label><label className="device-field">名称<input required maxLength={80} placeholder="食堂采集器" value={form.name} onChange={e=>setForm({...form,name:e.target.value})}/></label><label className="device-field">采样位置<input maxLength={160} placeholder="食堂入口" value={form.location} onChange={e=>setForm({...form,location:e.target.value})}/></label><label className="device-field">设备类型<select value={form.source} onChange={e=>setForm({...form,source:e.target.value})}><option value="esp32_c5">ESP32-C5</option><option value="linux_probe">Linux 探针</option><option value="windows_netsh">Windows 采集端</option></select></label><label className="device-field">预期上报间隔（秒）<input type="number" required min={10} max={86400} value={form.interval_seconds} onChange={e=>setForm({...form,interval_seconds:Number(e.target.value)})}/></label><button className="primary-button" disabled={busy} type="submit">创建设备</button></form>}
    <div className="table-scroll"><table><thead><tr><th>设备 / ID</th><th>采样位置</th><th>连接</th><th>采集数据</th><th>最后上报</th><th>操作</th></tr></thead><tbody>{devices.map(d=><tr key={d.collector_id}><td><strong>{d.name}</strong><small className="device-id">{d.collector_id} · {d.source}</small></td><td>{d.location||'未设置'}</td><td><span className={`badge ${d.online?'good':'pending'}`}>{!d.enabled?'已停用':!d.last_received_at?'待接入':d.online?'在线':'离线'}</span></td><td><span className={`badge ${d.data_fresh&&d.last_status==='success'?'good':'pending'}`}>{!d.last_observed_at?'未采集':d.last_status==='failed'?'扫描失败':d.data_fresh?'最新':'已过期'}</span><small className="device-id">{stamp(d.last_observed_at)}</small>{d.last_error&&<small className="device-error">{d.last_error}</small>}</td><td className="mono">{stamp(d.last_received_at)}</td><td><div className="device-actions"><button className="text-button" disabled={demo||!local||busy} onClick={()=>setEditing(d)}>编辑</button><button className="text-button" disabled={demo||!local||busy} onClick={()=>void rotate(d)}>重置密钥</button><button className="text-button" disabled={demo||!local||busy} onClick={()=>{if(window.confirm(`${d.enabled?'停用':'启用'} ${d.name}？`))void save({...d,enabled:!d.enabled});}}>{d.enabled?'停用':'启用'}</button></div></td></tr>)}</tbody></table></div>
    {!devices.length&&<div className="empty"><Radio size={30}/><p>尚未连接采集设备</p><span>添加设备后，使用设备密钥向接收接口上传。</span></div>}
    </section>
    {editing&&<section className="panel"><div className="panel-head"><h2>编辑 · {editing.collector_id}</h2></div><form className="device-form" onSubmit={e=>{e.preventDefault();void save(editing);}}><label className="device-field">名称<input required maxLength={80} value={editing.name} onChange={e=>setEditing({...editing,name:e.target.value})}/></label><label className="device-field">采样位置<input maxLength={160} value={editing.location} onChange={e=>setEditing({...editing,location:e.target.value})}/></label><label className="device-field">预期上报间隔（秒）<input type="number" required min={10} max={86400} value={editing.interval_seconds} onChange={e=>setEditing({...editing,interval_seconds:Number(e.target.value)})}/></label><button className="primary-button" type="submit" disabled={busy}>保存</button><button className="secondary-button" type="button" onClick={()=>setEditing(null)}>取消</button></form><p className="device-hint padded">间隔用于离线判断，不会远程修改设备固件。</p></section>}
    <section className="panel connection-guide"><h2>接收接口</h2><code>POST /api/collector/observations</code><p>设备使用 Bearer 密钥上传；扫描时间与上报时间分别保存，断网补传按批次去重。</p><p>Dashboard 不执行采集。ESP32-C5 需要兼容固件；添加设备不会自动安装固件或连接硬件。</p></section>
  </div>;
}
