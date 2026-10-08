import React,{useState,useEffect} from 'react';
import {Plus,Edit3,Copy,Trash2,BarChart3,ExternalLink,Check} from 'lucide-react';
import {api,get,post,put,message} from '../../lib/api';
import {PageTitle,Btn,Field,Loading,Empty,Status,Toggle,Modal} from '../../components/shared';
import {useStore} from '../../lib/store';
import {toast} from 'sonner';

const blank={product_id:'',variant_id:'',title:'',subtitle:'',description:'',coupon:'',cta_text:'Order now',layout:'product_first',countdown_ends_at:'',show_trust:true,show_faq:true,show_warranty:true,show_returns:true,affiliate_code:'',active:true};

export const AdminOffers=()=>{
 const {money}=useStore();
 const [rows,setRows]=useState<any[]|null>(null),[products,setProducts]=useState<any[]>([]),[edit,setEdit]=useState<any>(null),[stats,setStats]=useState<any>(null);
 const load=()=>get('/admin/offers').then(setRows).catch(e=>toast.error(message(e)));
 useEffect(()=>{load();get('/admin/products').then(setProducts).catch(()=>{});},[]);
 const save=async()=>{try{const data={...edit,countdown_ends_at:edit.countdown_ends_at?new Date(edit.countdown_ends_at).toISOString():''};edit.id?await put('/admin/offers/'+edit.id,data):await post('/admin/offers',data);setEdit(null);load();toast.success('Offer saved');}catch(e){toast.error(message(e));}};
 const openStats=async(row:any)=>{try{setStats(await get('/admin/offers/'+row.id+'/analytics'));}catch(e){toast.error(message(e));}};
 const selected=edit&&products.find((p:any)=>p.id===edit.product_id);
 return <><PageTitle eyebrow="MARKETING / OFFER PAGES" title="One product. One page. One click to buy." description="Generate standalone shareable pages for campaigns, influencers and chat — with their own analytics."><Btn id="offer-new" className="primary" onClick={()=>setEdit({...blank})}><Plus size={16}/>New offer page</Btn></PageTitle>
 <div className="admin-panel">{!rows?<Loading/>:rows.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Offer</th><th>Product</th><th>Share URL</th><th>Views</th><th>Orders</th><th>Status</th><th/></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><b>{r.title}</b><small className="block mono">/{r.code}</small></td><td>{products.find((p:any)=>p.id===r.product_id)?.name||r.product_id}</td><td><button className="text-link" data-testid={`offer-copy-${r.id}`} onClick={()=>{navigator.clipboard.writeText(window.location.origin+'/offer/'+r.code);toast.success('Share link copied');}}><Copy size={13}/> /offer/{r.code}</button></td><td data-testid={`offer-views-${r.id}`}>{r.views}</td><td>{r.orders}</td><td><Status id={`offer-${r.id}`} value={r.active?'published':'disabled'}/></td><td><button className="icon-btn" title="Analytics" onClick={()=>openStats(r)}><BarChart3 size={15}/></button><a className="icon-btn" title="Open page" href={'/offer/'+r.code} target="_blank" rel="noreferrer"><ExternalLink size={15}/></a><button className="icon-btn" title="Edit" onClick={()=>setEdit({...blank,...r})}><Edit3 size={15}/></button><button className="icon-btn" title="Delete" onClick={async()=>{try{await api.delete('/admin/offers/'+r.id);load();toast.success('Offer deleted');}catch(e){toast.error(message(e));}}}><Trash2 size={15}/></button></td></tr>)}</tbody></table></div>:<Empty title="No offer pages yet." description="Generate a one-page checkout for a single product and share the link anywhere."/>}</div>
 <Modal open={!!edit} onClose={()=>setEdit(null)} title={edit?.id?'Edit offer page':'New offer page'} description="A standalone page with its own checkout. Prices, stock and coupons are revalidated server-side at order time.">
  {edit&&<form onSubmit={e=>{e.preventDefault();save();}} data-testid="offer-editor">
   <Field id="offer-product" label="Product" as="select" required value={edit.product_id} onChange={(e:any)=>setEdit({...edit,product_id:e.target.value,variant_id:''})}><option value="">Choose a product</option>{products.map((p:any)=><option key={p.id} value={p.id}>{p.name}</option>)}</Field>
   {selected&&<Field id="offer-variant" label="Featured variant" as="select" required value={edit.variant_id} onChange={(e:any)=>setEdit({...edit,variant_id:e.target.value})}><option value="">Choose a variant</option>{selected.variants.map((v:any)=><option key={v.id} value={v.id}>{Object.values(v.options).join(' / ')||v.sku} — {money(v.price,true)}</option>)}</Field>}
   <Field id="offer-title" label="Page title" required value={edit.title} onChange={(e:any)=>setEdit({...edit,title:e.target.value})}/>
   <Field id="offer-subtitle" label="Subtitle" value={edit.subtitle} onChange={(e:any)=>setEdit({...edit,subtitle:e.target.value})}/>
   <Field id="offer-description" label="Description" as="textarea" value={edit.description} onChange={(e:any)=>setEdit({...edit,description:e.target.value})}/>
   <div className="field-grid">
    <Field id="offer-coupon" label="Pre-applied coupon code (optional)" value={edit.coupon} onChange={(e:any)=>setEdit({...edit,coupon:e.target.value.toUpperCase()})}/>
    <Field id="offer-cta" label="Button text" value={edit.cta_text} onChange={(e:any)=>setEdit({...edit,cta_text:e.target.value})}/>
    <Field id="offer-layout" label="Layout" as="select" value={edit.layout} onChange={(e:any)=>setEdit({...edit,layout:e.target.value})}><option value="product_first">Product first</option><option value="checkout_first">Checkout first</option></Field>
    <Field id="offer-countdown" label="Offer ends at (optional, shown truthfully)" type="datetime-local" value={(edit.countdown_ends_at||'').slice(0,16)} onChange={(e:any)=>setEdit({...edit,countdown_ends_at:e.target.value})}/>
    <Field id="offer-affiliate" label="Affiliate code (optional attribution)" value={edit.affiliate_code} onChange={(e:any)=>setEdit({...edit,affiliate_code:e.target.value.toUpperCase()})}/>
   </div>
   <div className="feature-grid" style={{marginTop:12}}>{[['show_trust','Trust badges'],['show_faq','FAQ'],['show_warranty','Warranty info'],['show_returns','Return info']].map(([k,label])=><Toggle key={k} id={`offer-${k}`} label={label} value={edit[k]} onChange={(v:boolean)=>setEdit({...edit,[k]:v})}/>)}</div>
   <Toggle id="offer-active" label="Active (page is reachable)" value={edit.active} onChange={(v:boolean)=>setEdit({...edit,active:v})}/>
   <Btn id="offer-save" type="submit" className="primary"><Check size={15}/>Save offer page</Btn></form>}
 </Modal>
 <Modal open={!!stats} onClose={()=>setStats(null)} title="Offer analytics" description="Consent-aware events, 30-day retention.">
  {stats&&<><div className="admin-metrics inventory-metrics">
   <div className="metric"><span>Views</span><strong>{stats.views}</strong></div>
   <div className="metric"><span>Unique visitors</span><strong>{stats.unique_visitors}</strong></div>
   <div className="metric"><span>Orders</span><strong data-testid="offer-analytics-orders">{stats.purchases}</strong></div>
   <div className="metric"><span>Conversion</span><strong>{stats.conversion_rate}%</strong></div>
  </div>
  <p className="small-note">CTA clicks {stats.cta_clicks} · checkouts started {stats.checkouts} · devices: {stats.devices.map((d:any)=>`${d.device} ${d.count}`).join(', ')||'—'}</p></>}
 </Modal></>;
};
export default AdminOffers;
