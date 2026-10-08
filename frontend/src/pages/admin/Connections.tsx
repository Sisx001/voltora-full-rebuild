import React,{useState,useEffect} from 'react';
import {PageTitle,Loading,Btn,Field,Toggle,Status} from '../../components/shared';
import {ProviderConfig} from './Providers';
import {useStore} from '../../lib/store';
import {get,put,post,message} from '../../lib/api';
import {toast} from 'sonner';
import OAuthProviders from './OAuth';

/** Per-event Telegram alert rules: toggle + severity floor per known event. */
export const AlertEventRules=()=>{
 const [data,setData]=useState<any>(null),[rules,setRules]=useState<any>({}),[minSev,setMinSev]=useState('low'),[busy,setBusy]=useState(false);
 const load=async()=>{try{const d=await get('/admin/alerts/settings');setData(d);setRules(d.events||{});setMinSev(d.min_severity||'low');}catch(e){toast.error(message(e));}};
 useEffect(()=>{load();},[]);
 const setRule=(ev:string,patch:any)=>setRules((r:any)=>({...r,[ev]:{enabled:true,min_severity:'low',...r[ev],...patch}}));
 const save=async()=>{setBusy(true);try{const events=Object.entries(rules).map(([event,v]:any)=>({event,...v}));await put('/admin/alerts/settings',{events,min_severity:minSev});await load();toast.success('Alert rules saved — future events follow them');}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 if(!data)return null;
 return <section className="admin-panel" data-testid="alert-event-rules" style={{marginTop:18}}>
  <div className="panel-heading"><h2>Alert events & severity</h2><Status id="alert-rules-status" value={Object.keys(rules).length?Object.keys(rules).length+' customized':'defaults'}/></div>
  <p className="small-note">Choose which events reach your Telegram alerts and the minimum severity for each. Events not listed here use the provider's own settings.</p>
  <div className="alert-rules-grid">
   {data.known_events.map((ev:string)=><div className="alert-rule" key={ev} data-testid={`alert-rule-${ev}`}>
    <Toggle id={`alert-on-${ev}`} label={ev.replaceAll('_',' ')} value={rules[ev]?rules[ev].enabled!==false:true} onChange={(v:boolean)=>setRule(ev,{enabled:v})}/>
    <Field id={`alert-sev-${ev}`} label="Min severity" as="select" value={rules[ev]?.min_severity||'low'} onChange={(e:any)=>setRule(ev,{min_severity:e.target.value})}>
     {['low','medium','high'].map(s=><option key={s} value={s}>{s}</option>)}
    </Field>
   </div>)}
  </div>
  <div className="field-grid" style={{maxWidth:320}}>
   <Field id="alert-global-sev" label="Global minimum severity" as="select" value={minSev} onChange={(e:any)=>setMinSev(e.target.value)}>{['low','medium','high'].map(s=><option key={s} value={s}>{s}</option>)}</Field>
  </div>
  <Btn id="alert-rules-save" className="primary" disabled={busy} onClick={save}>Save alert rules</Btn>
 </section>;
};

/** One hub for every provider kind: payments, couriers, SMS/OTP, email,
 *  Telegram alerts, CAPTCHA, Cloudflare, social sign-in. */
export const Connections=()=>{
 const {user}=useStore();
 const [sms,setSms]=useState<any[]|null>(null),[email,setEmail]=useState<any[]|null>(null);
 useEffect(()=>{get('/admin/providers/messaging').then(rows=>{setSms(rows.filter((r:any)=>r.messaging_kind==='sms'));setEmail(rows.filter((r:any)=>r.messaging_kind==='email'));}).catch(()=>{});},[]);
 return <><PageTitle eyebrow="CONNECTIONS" title="Every integration, one place." description="Enable, configure, test and activate providers — no code changes needed. Credentials are encrypted and never returned."/>
 {sms===null?<Loading/>:<>
  <ProviderConfig kind="payment" title="Payment providers" description="bKash, Nagad, Rocket, Upay, SSLCommerz, Stripe, PayPal + test gateway. One-click enable per gateway; sandbox mode before going live."/>
  <div style={{height:24}}/>
  <ProviderConfig kind="courier" title="Courier providers" description="Pathao, Steadfast, RedX + test courier. Booking, tracking, COD and cancellation."/>
  <div style={{height:24}}/>
  <ProviderConfig kind="messaging" title="SMS / OTP providers" description="Send OTP codes and SMS alerts. Required for OTP login and phone verification."/>
  <div style={{height:24}}/>
  <ProviderConfig kind="notification" title="Telegram alerts" description="Security and operations alerts to your Telegram: admin logins, failed logins, payment failures, courier failures, orders and returns."/>
  <AlertEventRules/>
  <div style={{height:24}}/>
  <ProviderConfig kind="captcha" title="CAPTCHA / bot protection" description="Cloudflare Turnstile, reCAPTCHA v2 or hCaptcha. Protect admin login, signup and password reset."/>
  <div style={{height:24}}/>
  <ProviderConfig kind="infra" title="Infrastructure" description="Cloudflare: verify your API token, then purge cache or toggle development mode right from here — real API actions, audited."/>
  <div style={{height:24}}/>
  <OAuthProviders/>
 </>}</>;
};
export default Connections;
