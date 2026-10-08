import React,{useState,useEffect} from 'react';
import {RefreshCw} from 'lucide-react';
import {get,message} from '../../lib/api';
import {Btn,Loading,Empty,Status} from '../../components/shared';
import {toast} from 'sonner';
import ProviderConfigurationPanel from './ProviderConfigurationPanel';

/** Admin configuration surface for one provider kind (payment | courier | messaging).
 *  Lists every registered adapter, and per provider: one-click enable, sealed
 *  credential editing, sandbox/live, non-secret settings, connection test, disconnect. */
export const ProviderConfig=ProviderConfigurationPanel;


export default ProviderConfig;
export const TransactionsLog=()=>{
 const [rows,setRows]=useState<any[]|null>(null);
 const load=()=>get('/admin/transactions').then(setRows).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[]);
 if(!rows)return <Loading/>;
 return <section className="admin-panel" data-testid="transactions-log"><div className="panel-heading"><h2>Payment transactions</h2><Btn id="transactions-refresh" variant="outline" onClick={load}><RefreshCw size={15}/>Refresh</Btn></div>
 {rows.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Order</th><th>Provider</th><th>Method</th><th>Amount</th><th>Status</th><th>Reference</th><th>Mode</th><th>Updated</th></tr></thead><tbody>{rows.map((t:any)=><tr key={t.id}><td className="mono">{t.order_number}</td><td>{t.provider}</td><td>{t.method_id}</td><td>{(t.amount/100).toLocaleString()} BDT</td><td><Status id={`tx-${t.id}`} value={t.status}/></td><td className="mono" style={{fontSize:11}}>{t.provider_ref||'—'}</td><td>{t.sandbox?'sandbox':'live'}</td><td>{new Date(t.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div>:<Empty title="No transactions yet." description="Online payment attempts appear here with their provider references and logs."/>}</section>;
};
