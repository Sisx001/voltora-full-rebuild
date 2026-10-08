import React,{useState,useEffect} from 'react';
import {RefreshCw,Package,X,Truck} from 'lucide-react';
import {api,get,post,message} from '../../lib/api';
import {PageTitle,Btn,Loading,Empty,Status} from '../../components/shared';
import {ProviderConfig} from './Providers';
import {toast} from 'sonner';

const SHIPMENT_STATES:any={booking:'processing',booked:'processing',picked_up:'shipped',in_transit:'shipped',out_for_delivery:'processing',delivered:'delivered',cancelled:'cancelled',returned:'failed',failed:'failed'};

export const AdminCouriers=()=>{
 return <><PageTitle eyebrow="CONNECTIONS / COURIERS" title="From your door to theirs." description="Connect Bangladesh couriers, book parcels per order, and keep tracking in sync."><a className="v-button" href="/admin/shipping">Delivery zones</a></PageTitle>
 <ProviderConfig kind="courier" title="Courier accounts" description="One-click enable per courier. Sandbox mode is available before going live. Booking and tracking need the courier's own merchant account."/>
 <ShipmentsTable/></>;
};

export const ShipmentsTable=({orderId=''}:{orderId?:string})=>{
 const [rows,setRows]=useState<any[]|null>(null);
 const load=()=>get('/admin/shipments').then(r=>setRows(orderId?r.filter((x:any)=>x.order_id===orderId):r)).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[orderId]);
 const track=async(id:string)=>{try{const r=await post('/admin/shipments/'+id+'/track');toast.success('Tracked: '+r.status);load();}catch(e){toast.error(message(e));}};
 const cancel=async(id:string)=>{try{await post('/admin/shipments/'+id+'/cancel');toast.success('Shipment cancelled');load();}catch(e){toast.error(message(e));}};
 if(!rows)return <Loading/>;
 return <section className="admin-panel" style={{marginTop:24}} data-testid="shipments-table"><div className="panel-heading"><h2>Shipments</h2><Btn id="shipments-refresh" variant="outline" onClick={load}><RefreshCw size={15}/>Refresh</Btn></div>
 {rows.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Order</th><th>Courier</th><th>Consignment</th><th>Status</th><th>COD</th><th>Mode</th><th>Updated</th><th/></tr></thead><tbody>{rows.map((s:any)=><tr key={s.id}><td className="mono">{s.order_number}</td><td>{s.provider}</td><td className="mono" style={{fontSize:11}}>{s.consignment_id||'—'}</td><td><Status id={`shipment-${s.id}`} value={SHIPMENT_STATES[s.status]||s.status}/></td><td>{s.cod_amount?(s.cod_amount/100).toLocaleString()+' BDT':'—'}</td><td>{s.sandbox?'sandbox':'live'}</td><td>{new Date(s.updated_at).toLocaleString()}</td><td><Btn id={`shipment-track-${s.id}`} variant="outline" onClick={()=>track(s.id)} disabled={!s.consignment_id}><RefreshCw size={13}/>Track</Btn>{!['delivered','cancelled'].includes(s.status)&&<Btn id={`shipment-cancel-${s.id}`} variant="outline" onClick={()=>cancel(s.id)}><X size={13}/>Cancel</Btn>}</td></tr>)}</tbody></table></div>:<Empty icon={Truck} title="No shipments yet." description="Book a parcel from an order in the Orders workspace."/>}</section>;
};
export default AdminCouriers;
