import React,{useEffect,useState} from 'react';
import {Activity,ShoppingBag,Users,PackageCheck,AlertTriangle,Mail,Sparkles,ShieldAlert,Link2,RefreshCw} from 'lucide-react';
import {get,message} from '../../lib/api';
import {PageTitle,Loading,Empty,Btn,Status} from '../../components/shared';
import {toast} from 'sonner';

const Tile=({icon:Icon,label,value,tone,testid}:any)=>(
 <div className={'monitor-tile'+(tone==='warn'?' warn':tone==='bad'?' bad':'')} data-testid={testid||'monitor-tile'}>
  <span className="monitor-tile-icon"><Icon size={19}/></span>
  <div><strong>{value}</strong><small>{label}</small></div>
 </div>);

const StoreMonitor=()=>{
 const [data,setData]=useState<any>(null),[busy,setBusy]=useState(false);
 const load=async(silent=false)=>{if(!silent)setBusy(true);try{setData(await get('/admin/monitor'));}catch(e){if(!silent)toast.error(message(e));}finally{setBusy(false);}};
 useEffect(()=>{load();const t=setInterval(()=>load(true),5000);return()=>clearInterval(t);},[]);
 if(!data)return <Loading/>;
 const maxRev=Math.max(1,...(data.series||[]).map((s:any)=>s.revenue));
 const kinds=[['payment','Payments'],['courier','Couriers'],['email','Email'],['sms','SMS'],['notification','Telegram'],['captcha','CAPTCHA']] as const;
 return <><PageTitle eyebrow="WORKSPACE / LIVE" title="The store, right now." description="A live wall of everything moving — orders, visitors, integrations, AI and queues. Refreshes every few seconds.">
  <Btn id="monitor-refresh" variant="outline" disabled={busy} onClick={()=>load()}><RefreshCw size={16}/>Refresh now</Btn></PageTitle>
 <div className="monitor-grid">
  <Tile icon={ShoppingBag} label="Orders today" value={data.orders_today} testid="monitor-orders"/>
  <Tile icon={Activity} label="Revenue today (paid)" value={'৳ '+(data.revenue_today||0).toLocaleString()} testid="monitor-revenue"/>
  <Tile icon={Users} label="Visitors today" value={data.visitors_today} testid="monitor-visitors"/>
  <Tile icon={PackageCheck} label="Open orders" value={data.pending_orders} tone={data.pending_orders>0?'warn':'ok'} testid="monitor-pending"/>
  <Tile icon={AlertTriangle} label="Low stock variants" value={data.low_stock} tone={data.low_stock>0?'warn':'ok'} testid="monitor-lowstock"/>
  <Tile icon={ShieldAlert} label="Failed sign-ins (24h)" value={data.signals.failed_logins_24h} tone={data.signals.failed_logins_24h>5?'bad':'ok'} testid="monitor-failedlogins"/>
  <Tile icon={Mail} label="Email queue" value={data.queues.email_queued+(data.queues.email_failed?' ('+data.queues.email_failed+' failed)':'')} tone={data.queues.email_failed>0?'warn':'ok'} testid="monitor-emailqueue"/>
  <Tile icon={Sparkles} label="AI tasks today" value={data.ai.today+(data.ai.running?' · '+data.ai.running+' running':'')} tone={data.ai.failed_24h>0?'warn':'ok'} testid="monitor-ai"/>
 </div>
 <div className="admin-panel" style={{marginTop:20}}><div className="panel-heading"><h2>Last 14 days</h2><span className="small-note">orders placed · bars show paid revenue</span></div>
  {(data.series||[]).length?<div className="monitor-chart" data-testid="monitor-chart">{data.series.map((s:any)=><div className="monitor-chart-col" key={s.day} title={s.day+': '+s.orders+' orders · ৳ '+s.revenue}><i style={{height:Math.round(8+92*s.revenue/maxRev)+'%'}}/><small>{s.orders}</small><span>{s.day.slice(5)}</span></div>)}</div>:<Empty title="No orders in the last two weeks yet"/>}
 </div>
 <div className="admin-panel" style={{marginTop:20}}><div className="panel-heading"><h2>Integrations health</h2><span className="small-note">enabled adapters and their last verification status</span></div>
  {Object.keys(data.integrations||{}).length===0?<Empty icon={Link2} title="No integrations enabled yet." description="Connect payments, couriers, email, SMS, Telegram or CAPTCHA from the Connections hub."/>:
   <div className="monitor-integrations">{kinds.map(([k,label]:any)=>(data.integrations[k]||[]).length?data.integrations[k].map((row:any,i:number)=><div className="monitor-int" key={k+i} data-testid={`monitor-int-${k}-${i}`}><Link2 size={15}/><b>{label}</b><small>{row.provider}</small><Status id={`monitor-int-status-${k}-${i}`} value={row.status==='active'||row.status==='healthy'?'published':row.status==='error'?'failed':'pending'}/></div>):null)}</div>}
 </div>
 </>;
};
export default StoreMonitor;
