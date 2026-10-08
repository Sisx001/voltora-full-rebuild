import React,{useState,useEffect} from 'react';
import {PageTitle,Btn,Field,Toggle,Status} from '../../components/shared';
import {ProviderConfig} from './Providers';
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
  <p className="small-note">Choose which events reach your Telegram alerts and the minimum severity for each. Events not listed here use the provider’s own settings.</p>
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
 const [environment,setEnvironment]=useState('sandbox');
 return <><PageTitle eyebrow="INTEGRATION CENTER" title="Every integration, one place." description="Configure safely. Verify deliberately. Saving credentials is never proof of operation."/>
 <div className="integration-environment"><label htmlFor="integration-environment">Configuration environment</label><select id="integration-environment" data-testid="integration-environment" value={environment} onChange={e=>setEnvironment(e.target.value)}><option value="sandbox">Sandbox</option><option value="production">Production</option></select><p>Separate credentials and verification for each environment. Production activation remains locked.</p></div>
 <>
  <ProviderConfig environment={environment} kind="payment" title="Payment providers" description="Real payment adapters. Connection checks and complete payment workflows are verified separately."/>
  <div style={{height:24}}/>
  <ProviderConfig environment={environment} kind="courier" title="Courier providers" description="Pathao, Steadfast and RedX. Credentials alone do not verify booking, tracking or delivery."/>
  <div style={{height:24}}/>
  <ProviderConfig environment={environment} kind="messaging" title="Email and SMS" description="SMTP email is available for configuration. A real SMS adapter is still required; no test sender will be substituted."/>
  <div style={{height:24}}/>
  <ProviderConfig environment={environment} kind="notification" title="Telegram alerts" description="Security and operations alerts. A dedicated test bot and controlled recipient are required for verification."/>
  <AlertEventRules/>
  <div style={{height:24}}/>
  <ProviderConfig environment={environment} kind="captcha" title="CAPTCHA / bot protection" description="Challenge validation is not a credential connection check. Widget and server-side challenge workflows still require verification."/>
  <div style={{height:24}}/>
  <ProviderConfig environment={environment} kind="infra" title="Infrastructure" description="Cloudflare configuration. No general sandbox; real account checks and infrastructure changes need separate approval."/>
  <div style={{height:24}}/>
  <p className="small-note">Social sign-in below uses its existing configuration system and is not yet migrated to the versioned integration center.</p>
  <OAuthProviders/>
 </></>;
};
export default Connections;
