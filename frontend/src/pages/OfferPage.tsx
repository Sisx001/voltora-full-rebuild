import React,{useState,useEffect,useRef} from 'react';
import {Link,useParams,useSearchParams} from 'react-router-dom';
import {ShoppingBag,ShieldCheck,Truck,RotateCcw,Check,Loader2,ChevronDown,ArrowRight} from 'lucide-react';
import {api,get,post,message} from '../lib/api';
import {Btn,Field,Loading,Status} from '../components/shared';
import {Logo} from '../components/store/Header';
import {toast} from 'sonner';

const visitor=()=>{let v=localStorage.getItem('voltora-visitor');if(!v){v=crypto.randomUUID();localStorage.setItem('voltora-visitor',v);}return v;};

export const OfferPage=()=>{
 const {code}=useParams();const [params]=useSearchParams();
 const [data,setData]=useState<any>(null),[error,setError]=useState('');
 const [qty,setQty]=useState(1),[shippingId,setShippingId]=useState(''),[payment,setPayment]=useState(''),[form,setForm]=useState({name:'',email:'',phone:'',address:'',city:'',postal_code:'',notes:'',terms:false});
 const [busy,setBusy]=useState(false),[done,setDone]=useState<any>(null);
 const track=(event:string)=>{try{const consent=JSON.parse(localStorage.getItem('voltora-consent')||'{}');if(!consent.analytics)return;post(`/offer/${code}/track`,{event,visitor_id:visitor(),referrer:document.referrer.slice(0,300)}).catch(()=>{});}catch{}};
 useEffect(()=>{get(`/offer/${code}?ref=${params.get('ref')||''}`).then((d:any)=>{setData(d);setShippingId(d.shipping[0]?.id||'');setPayment(d.payments.find((p:any)=>p.available)?.id||'');if(d.offer.affiliate_code)setForm((f:any)=>({...f}));}).catch(e=>setError(message(e)));window.scrollTo({top:0});},[code]);
 useEffect(()=>{if(data)track('view');},[data?.offer.code]);
 if(error)return <div className="offer-page"><div className="offer-error"><h1>This offer is not available.</h1><p>{error}</p><Link className="v-button primary" to="/">Visit the store instead</Link></div></div>;
 if(!data)return <div className="offer-page"><div className="offer-loading"><Loader2 size={30} className="spin"/></div></div>;
 const {offer,product,variant}=data;
 const endsAt=offer.countdown_ends_at?new Date(offer.countdown_ends_at).getTime():0;
 const shareLink=window.location.origin+'/offer/'+code+(params.get('ref')?'?ref='+params.get('ref'):'');
 const submit=async(e:any)=>{e.preventDefault();setBusy(true);try{track('begin_checkout');const response=await api.post(`/offer/${code}/checkout?ref=${params.get('ref')||''}`,{...form,variant_id:variant.id,quantity:qty,shipping_id:shippingId,payment_method:payment},{headers:{'Idempotency-Key':crypto.randomUUID()}});
  if(response.data.payment?.redirect_url){window.location.assign(response.data.payment.redirect_url);return;}
  track('purchase');setDone(response.data);}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 if(done)return <div className="offer-page"><div className="offer-done" data-testid="offer-success"><span className="offer-done-icon"><Check size={30}/></span><h1>Order confirmed.</h1><p>Your order <b>{done.number}</b> is placed. Total: <b>{(done.total/100).toLocaleString()} BDT</b>.</p><p className="small-note">Keep this private link to follow your order: <span className="mono">{shareLink.split('/offer')[0]}/order/{done.id}?access={done.access}</span></p><Link className="v-button primary" to="/">Continue to the store</Link></div></div>;
 return <div className="offer-page" data-testid="offer-page">
  <header className="offer-header"><Logo/><span className="offer-header-note">{offer.coupon?`Coupon ${offer.coupon} applied automatically`:''}</span></header>
  <main className="offer-main">
   <section className="offer-hero"><div className="offer-gallery"><img src={product.image} alt={product.name}/></div>
    <div className="offer-info">
     <span className="eyebrow">LIMITED OFFER</span>
     <h1 data-testid="offer-title">{offer.title||product.name}</h1>
     {offer.subtitle&&<p className="offer-subtitle">{offer.subtitle}</p>}
     <div className="offer-price"><strong data-testid="offer-price">{(variant.price/100).toLocaleString()} BDT</strong><span>{Object.values(variant.options).join(' / ')}</span></div>
     {endsAt>Date.now()&&<div className="offer-countdown" data-testid="offer-countdown"><ShoppingBag size={15}/> Offer ends {new Date(endsAt).toLocaleString()}</div>}
     {variant.stock<=0&&<p className="form-error">Sold out — check back soon.</p>}
     <Btn id="offer-cta" className="primary" disabled={busy||variant.stock<=0} onClick={()=>{document.getElementById('offer-checkout')?.scrollIntoView({behavior:'smooth'});track('click_cta');}}>{offer.cta_text}<ArrowRight size={16}/></Btn>
     {offer.show_trust&&<div className="offer-trust">
      <span><Truck size={16}/> Fast delivery across Bangladesh</span>
      <span><ShieldCheck size={16}/> {product.warranty||'Warranty included'}</span>
      <span><RotateCcw size={16}/> Easy returns</span>
     </div>}
    </div>
   </section>
   {offer.description&&<section className="offer-section"><h2>About this offer</h2><p>{offer.description}</p></section>}
   <section className="offer-section" id="offer-checkout"><h2>Complete your order</h2>
    <form className="offer-checkout" onSubmit={submit} data-testid="offer-checkout-form">
     <div className="field-grid">
      <Field id="offer-name" label="Full name" required value={form.name} onChange={(e:any)=>setForm({...form,name:e.target.value})}/>
      <Field id="offer-email" label="Email" type="email" required value={form.email} onChange={(e:any)=>setForm({...form,email:e.target.value})}/>
      <Field id="offer-phone" label="Phone" type="tel" required minLength={7} value={form.phone} onChange={(e:any)=>setForm({...form,phone:e.target.value})}/>
     </div>
     <Field id="offer-address" label="Street address" required minLength={5} value={form.address} onChange={(e:any)=>setForm({...form,address:e.target.value})}/>
     <div className="field-grid">
      <Field id="offer-city" label="City / district" required value={form.city} onChange={(e:any)=>setForm({...form,city:e.target.value})}/>
      <Field id="offer-postal" label="Postal code (optional)" value={form.postal_code} onChange={(e:any)=>setForm({...form,postal_code:e.target.value})}/>
     </div>
     <div className="field-grid">
      <Field id="offer-shipping" label="Delivery" as="select" value={shippingId} onChange={(e:any)=>setShippingId(e.target.value)}>{data.shipping.map((s:any)=><option key={s.id} value={s.id}>{s.name} — {s.fee?(s.fee/100).toLocaleString()+' BDT':'Free'} · {s.estimate}</option>)}</Field>
      <Field id="offer-payment" label="Payment" as="select" value={payment} onChange={(e:any)=>setPayment(e.target.value)}>{data.payments.filter((p:any)=>p.available).map((p:any)=><option key={p.id} value={p.id}>{p.label}</option>)}</Field>
      <Field id="offer-qty" label="Quantity" type="number" min="1" max={Math.min(50,variant.stock)} value={qty} onChange={(e:any)=>setQty(Math.max(1,Math.min(+e.target.value||1,Math.min(50,variant.stock))))}/>
     </div>
     <div className="offer-summary"><span>Total</span><strong data-testid="offer-total">{((variant.price*qty)+(data.shipping.find((s:any)=>s.id===shippingId)?.fee||0)).toLocaleString()} BDT</strong></div>
     <label className="checkbox-label"><input type="checkbox" required checked={form.terms} onChange={e=>setForm({...form,terms:e.target.checked})}/><span>I agree to the terms and privacy policy.</span></label>
     <Btn id="offer-place-order" type="submit" className="primary" disabled={busy||variant.stock<=0||!payment}>{busy?'Placing your order...':offer.cta_text}<ArrowRight size={17}/></Btn>
     <p className="small-note"><ShieldCheck size={12}/> Prices and stock are revalidated server-side. No payment is collected on this page for COD/bank transfer.</p>
    </form>
   </section>
   {product.warranty&&offer.show_warranty&&<section className="offer-section"><h2>Warranty</h2><p>{product.warranty}</p></section>}
   {offer.show_returns&&<section className="offer-section"><h2>Returns</h2><p>Changed your mind? Contact support through the store with your order number — returns are reviewed by the team.</p></section>}
   {offer.show_faq&&<section className="offer-section"><h2>Common questions</h2>
    <details><summary>How fast is delivery?<ChevronDown size={15}/></summary><p>Orders ship within 1–2 business days; Dhaka typically arrives in 2–3 days.</p></details>
    <details><summary>Can I pay on delivery?<ChevronDown size={15}/></summary><p>Cash on delivery is available when shown as a payment option above.</p></details>
    <details><summary>Who do I contact for help?<ChevronDown size={15}/></summary><p>Visit the store support page with your order number — the team responds quickly.</p></details>
   </section>}
  </main>
  <footer className="offer-footer"><Link to="/">{data.store.brand} — official store</Link><span className="mono">{shareLink}</span></footer>
 </div>;
};
export default OfferPage;
