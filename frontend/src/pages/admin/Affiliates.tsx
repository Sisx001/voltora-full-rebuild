import React,{useState,useEffect} from 'react';
import {Plus,Edit3,Wallet,ScrollText} from 'lucide-react';
import {get,post,put,message} from '../../lib/api';
import {PageTitle,Btn,Field,Loading,Empty,Status,Modal} from '../../components/shared';
import {useStore} from '../../lib/store';
import {toast} from 'sonner';

const blank={name:'',email:'',commission_pct:5,status:'active',notes:''};

export const AdminAffiliates=()=>{
 const {money}=useStore();
 const [rows,setRows]=useState<any[]|null>(null),[edit,setEdit]=useState<any>(null),[ledgerFor,setLedgerFor]=useState<any>(null),[ledger,setLedger]=useState<any[]>([]);
 const load=()=>get('/admin/affiliates').then(setRows).catch(e=>toast.error(message(e)));
 useEffect(()=>{load();},[]);
 const save=async()=>{try{edit.id?await put('/admin/affiliates/'+edit.id,{name:edit.name,email:edit.email,commission_pct:edit.commission_pct,status:edit.status,notes:edit.notes}):await post('/admin/affiliates',{name:edit.name,email:edit.email,commission_pct:edit.commission_pct,status:edit.status,notes:edit.notes});setEdit(null);load();toast.success('Affiliate saved');}catch(e){toast.error(message(e));}};
 const openLedger=async(row:any)=>{setLedgerFor(row);try{setLedger(await get('/admin/affiliates/'+row.id+'/ledger'));}catch(e){setLedger([]);}};
 const payout=async(row:any)=>{try{const r=await post('/admin/affiliates/'+row.id+'/payout',{note:'Manual payout'});toast.success(`Paid ${money(r.total,true)} across ${r.orders} orders`);openLedger(row);load();}catch(e){toast.error(message(e));}};
 return <><PageTitle eyebrow="MARKETING / AFFILIATES" title="Partners who grow the store." description="Referral codes, tracked links and commissions settled when orders are paid."><Btn id="affiliate-new" className="primary" onClick={()=>setEdit({...blank})}><Plus size={16}/>Add affiliate</Btn></PageTitle>
 <div className="admin-panel">{!rows?<Loading/>:rows.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Affiliate</th><th>Referral code</th><th>Clicks</th><th>Conversions</th><th>Commission</th><th>Status</th><th/></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><b>{r.name}</b><small className="block">{r.email}</small></td><td className="mono">{r.code}</td><td>{r.clicks}</td><td>{r.conversions}</td><td><b>{money(r.commission_earned||0,true)}</b><small className="block">paid {money(r.commission_paid||0,true)}</small></td><td><Status id={`affiliate-${r.id}`} value={r.status==='active'?'published':r.status==='pending'?'pending':'disabled'}/></td><td><button className="icon-btn" title="Ledger & payouts" onClick={()=>openLedger(r)}><ScrollText size={15}/></button><button className="icon-btn" title="Edit" onClick={()=>setEdit({...blank,...r})}><Edit3 size={15}/></button></td></tr>)}</tbody></table></div>:<Empty title="No affiliates yet." description="Add a partner, share their referral code, and commissions accrue automatically on paid orders."/>}</div>
 <Modal open={!!edit} onClose={()=>setEdit(null)} title={edit?.id?'Edit affiliate':'Add an affiliate'}>
  {edit&&<form onSubmit={e=>{e.preventDefault();save();}} data-testid="affiliate-editor">
   <Field id="affiliate-name" label="Name" required value={edit.name} onChange={(e:any)=>setEdit({...edit,name:e.target.value})}/>
   <Field id="affiliate-email" label="Email" type="email" required value={edit.email} onChange={(e:any)=>setEdit({...edit,email:e.target.value})}/>
   <div className="field-grid"><Field id="affiliate-commission" label="Commission (%)" type="number" min="0" max="50" step="0.5" value={edit.commission_pct} onChange={(e:any)=>setEdit({...edit,commission_pct:+e.target.value})}/><Field id="affiliate-status" label="Status" as="select" value={edit.status} onChange={(e:any)=>setEdit({...edit,status:e.target.value})}>{['pending','active','suspended'].map(s=><option key={s}>{s}</option>)}</Field></div>
   <Field id="affiliate-notes" label="Notes" as="textarea" value={edit.notes} onChange={(e:any)=>setEdit({...edit,notes:e.target.value})}/>
   <Btn id="affiliate-save" type="submit" className="primary">Save affiliate</Btn></form>}
 </Modal>
 <Modal open={!!ledgerFor} onClose={()=>setLedgerFor(null)} title={`Commission ledger — ${ledgerFor?.name||''}`} description="Commissions accrue when attributed orders are PAID, never on placement.">
  <div style={{display:'flex',gap:10,marginBottom:14}}><Btn id="affiliate-payout" variant="outline" onClick={()=>payout(ledgerFor)}><Wallet size={15}/>Pay out pending</Btn></div>
  {ledger.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Order</th><th>Order total</th><th>Commission</th><th>Status</th><th>Date</th></tr></thead><tbody>{ledger.map(l=><tr key={l.id}><td className="mono">{l.order_number}</td><td>{money(l.order_total,true)}</td><td><b>{money(l.commission,true)}</b></td><td><Status id={`ledger-${l.id}`} value={l.status==='paid'?'paid':'pending'}/></td><td>{new Date(l.created_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>:<Empty title="No commissions yet." description="Attributed orders appear here once they are placed and paid."/>}
 </Modal></>;
};
export default AdminAffiliates;
