import React,{useEffect,useState} from 'react';
import {Area,AreaChart,CartesianGrid,ResponsiveContainer,Tooltip,XAxis,YAxis,Bar,BarChart} from 'recharts';
import {get,message} from '../../lib/api';
import {PageTitle,Loading,Empty} from '../../components/shared';
import {useStore} from '../../lib/store';
import {toast} from 'sonner';

const FUNNEL_LABELS:any={page_view:'Page views',product_view:'Product views',add_to_cart:'Added to bag',begin_checkout:'Checkout started',purchase:'Purchased'};

export const Analytics=()=>{
 const {money}=useStore();const [data,setData]=useState<any>(null),[days,setDays]=useState(30);
 const load=()=>get('/admin/analytics?days='+days).then(setData).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[days]);
 if(!data)return <Loading/>;
 const funnelMax=Math.max(1,...data.funnel.map((f:any)=>f.count));
 return <><PageTitle eyebrow="WORKSPACE / ANALYTICS" title="What shoppers actually do." description="Consent-gated funnel, traffic, and search insights. Visitor data is retained for 30 days.">
  <select data-testid="analytics-range" aria-label="Date range" value={days} onChange={e=>setDays(+e.target.value)}>{[7,30,90].map(d=><option key={d} value={d}>{d} days</option>)}</select></PageTitle>
 <div className="admin-metrics inventory-metrics">{[['Visitors',data.visitors],['Funnel top',data.funnel[0]?.count??0],['Purchases',data.funnel[4]?.count??0]].map(([label,val],i)=><div className="metric" key={label}><span>{label}</span><strong data-testid={`analytics-metric-${i}`}>{val}</strong></div>)}</div>
 <div className="overview-grid">
  <section className="admin-panel"><div className="panel-heading"><h2>Daily activity</h2></div>
  {data.daily.length?<div className="revenue-chart"><ResponsiveContainer width="100%" height={230}><AreaChart data={data.daily}><defs><linearGradient id="events-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7aa74f" stopOpacity={0.25}/><stop offset="100%" stopColor="#7aa74f" stopOpacity={0}/></linearGradient></defs><CartesianGrid stroke="#edf0e9" vertical={false}/><XAxis dataKey="date" fontSize={11}/><YAxis fontSize={11}/><Tooltip/><Area type="monotone" dataKey="events" stroke="#7fa653" fill="url(#events-fill)" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>:<Empty title="No recorded activity yet." description="Events appear once customers consent to analytics."/>}</section>
  <section className="admin-panel"><div className="panel-heading"><h2>Shopping funnel</h2></div>
  <div className="funnel-rows" data-testid="analytics-funnel">{data.funnel.map((f:any)=><div key={f.event} className="funnel-row"><span>{FUNNEL_LABELS[f.event]||f.event}</span><div><i style={{width:Math.round(f.count/funnelMax*100)+'%'}}/></div><b>{f.count}</b></div>)}</div></section>
 </div>
 <div className="overview-grid" style={{marginTop:24}}>
  <section className="admin-panel"><div className="panel-heading"><h2>Top search terms</h2></div>
  {data.search_terms.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Term</th><th>Searches</th></tr></thead><tbody>{data.search_terms.map((s:any)=><tr key={s.term}><td>{s.term}</td><td>{s.count}</td></tr>)}</tbody></table></div>:<Empty title="No search data yet."/>}</section>
  <section className="admin-panel"><div className="panel-heading"><h2>Traffic sources</h2></div>
  {data.sources.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Source</th><th>Visitors</th></tr></thead><tbody>{data.sources.map((s:any)=><tr key={s.source}><td>{s.source}</td><td>{s.count}</td></tr>)}</tbody></table></div>:<Empty title="No source data yet."/>}</section>
 </div>
 <div className="overview-grid" style={{marginTop:24}}>
  <section className="admin-panel"><div className="panel-heading"><h2>Devices</h2></div>
  {data.devices.length?<div className="revenue-chart"><ResponsiveContainer width="100%" height={200}><BarChart data={data.devices}><CartesianGrid stroke="#edf0e9" vertical={false}/><XAxis dataKey="device" fontSize={11}/><YAxis fontSize={11}/><Tooltip/><Bar dataKey="count" fill="#7fa653" radius={[6,6,0,0]}/></BarChart></ResponsiveContainer></div>:<Empty title="No device data yet."/>}</section>
  <section className="admin-panel"><div className="panel-heading"><h2>Most viewed products</h2></div>
  {data.top_products.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Path</th><th>Views</th></tr></thead><tbody>{data.top_products.map((p:any)=><tr key={p.path}><td className="mono" style={{fontSize:11}}>{p.path}</td><td>{p.count}</td></tr>)}</tbody></table></div>:<Empty title="No product views yet."/>}</section>
 </div>
 <p className="small-note" style={{marginTop:18}}>{data.note}</p></>;
};
export default Analytics;
