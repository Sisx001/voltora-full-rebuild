import React,{useState,useEffect} from 'react';
import {Plus,KeyRound,ShieldCheck,Trash2,RefreshCw,ExternalLink,Check} from 'lucide-react';
import {api,get,put,message} from '../../lib/api';
import {Btn,Field,Loading,Empty,Status,Toggle,Modal,Select} from '../../components/shared';
import {toast} from 'sonner';

/** Admin configuration surface for one provider kind (payment | courier | messaging).
 *  Lists every registered adapter, and per provider: one-click enable, sealed
 *  credential editing, sandbox/live, non-secret settings, connection test, disconnect. */
export const ProviderConfig=({kind,title,description,permUpdate=true}:{kind:string;title:string;description:string;permUpdate?:boolean})=>{
 const [rows,setRows]=useState<any[]|null>(null),[edit,setEdit]=useState<any>(null),[busy,setBusy]=useState(false);
 const load=()=>get('/admin/providers/'+kind).then(setRows).catch(e=>toast.error(message(e)));
 useEffect(()=>{load();},[kind]);
 if(!rows)return <Loading/>;
 const openEditor=async(row:any)=>{try{const detail=await get(`/admin/providers/${kind}/${row.id}`);setEdit(detail);}catch(e){toast.error(message(e));}};
 const save=async(enable:boolean)=>{setBusy(true);try{const credentials:any={};(edit.credentials_spec||[]).forEach((f:any)=>{credentials[f.key]=edit._input?.[f.key]??'';});const config:any={};(edit.settings_spec||[]).forEach((f:any)=>{if(edit._settings?.[f.key]!==undefined)config[f.key]=edit._settings[f.key];else if(edit.config?.[f.key]!==undefined)config[f.key]=edit.config[f.key];else if(f.default)config[f.key]=f.default;});
  const r=await put(`/admin/providers/${kind}/${edit.id}`,{credentials,config,sandbox:!!edit.sandbox,enabled:enable});
  setEdit(null);load();toast.success(enable?(r.message||'Connected and enabled'):'Saved (provider disabled)');}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 const verify=async(row:any)=>{try{const r:any=await api.post(`/admin/providers/${kind}/${row.id}/verify`);toast[r.ok?'success':'error'](r.message);load();}catch(e){toast.error(message(e));}};
 const disconnect=async(row:any)=>{try{await api.delete(`/admin/providers/${kind}/${row.id}`);load();toast.success('Provider disconnected and disabled');}catch(e){toast.error(message(e));}};
 return <section className="admin-panel" data-testid={`providers-${kind}`}>
  <div className="panel-heading"><h2>{title}</h2></div>
  <p className="small-note" style={{margin:'-6px 24px 16px'}}>{description}</p>
  {rows.length?<div className="provider-grid">{rows.map(row=><div className="provider-card" key={row.kind==='messaging'?row.messaging_kind+':'+row.id:row.id} data-testid={`provider-${row.id}`}>
    <div className="provider-card-head">
      <div><b>{row.label}</b>{row.method_ids?.length?<div className="permission-tags" style={{marginTop:6}}>{row.method_ids.map((m:string)=><span key={m}>{m}</span>)}</div>:null}</div>
      <div className="provider-card-status"><Status id={`provider-status-${row.id}`} value={row.enabled?(row.status==='connected'?'connected':'error'):(row.configured?'disabled':'not_configured')}/>{row.sandbox&&<span className="mono sandbox-tag">sandbox</span>}</div>
    </div>
    <p className="small-note">{row.configured?`Credentials saved${row.last_verified?` · verified ${new Date(row.last_verified).toLocaleDateString()}`:''}${row.error?' · '+row.error:''}`:'Not configured — credentials required.'}</p>
    <div className="provider-card-actions">
      {permUpdate&&<>
        <Btn id={`provider-configure-${row.id}`} variant="outline" onClick={()=>openEditor(row)}><KeyRound size={14}/>{row.configured?'Configure':'Set up'}</Btn>
        {row.configured&&<Toggle id={`provider-enabled-${row.id}`} label="Enabled" value={row.enabled} onChange={async(v:boolean)=>{if(v&&!row.configured){toast.error('Save credentials first');return;}try{await put(`/admin/providers/${kind}/${row.id}`,{credentials:{},config:{},sandbox:row.sandbox,enabled:v});load();toast.success(v?'Provider enabled':'Provider disabled');}catch(e){toast.error(message(e));}}}/>}
        {row.configured&&<Btn id={`provider-verify-${row.id}`} variant="outline" onClick={()=>verify(row)}><RefreshCw size={14}/>Test</Btn>}
        {row.configured&&(row.actions||[]).map((a:string)=><Btn id={`provider-action-${row.id}-${a}`} key={a} variant="outline" title={a==='purge_cache'?'Purge everything from the Cloudflare cache':'Toggle Cloudflare development mode'} onClick={async()=>{try{const params:any={};if(a==='dev_mode')params.enable=window.confirm('Enable development mode?\n\nOK = turn ON · Cancel = turn OFF');const r:any=await api.post(`/admin/providers/${kind}/${row.id}/actions/${a}`,params);toast.success(r.message||('Done: '+a.replaceAll('_',' ')));}catch(e){toast.error(message(e));}}}>{a.replaceAll('_',' ')}</Btn>)}
        {row.configured&&<Btn id={`provider-disconnect-${row.id}`} variant="outline" onClick={()=>disconnect(row)}><Trash2 size={14}/>Disconnect</Btn>}
        {row.docs_url&&<a className="icon-btn" href={row.docs_url} target="_blank" rel="noreferrer" title="Provider documentation"><ExternalLink size={15}/></a>}
      </>}
    </div>
  </div>)}</div>:<Empty title="No providers registered" description="Adapter modules appear here automatically when present on the server."/>}
  <Modal open={!!edit} onClose={()=>setEdit(null)} title={`Configure ${edit?.label||''}`} description="Credentials are encrypted at rest and never shown again after saving. Leave a field blank to keep its stored value.">
   {edit&&<form onSubmit={e=>{e.preventDefault();save(true);}} data-testid="provider-editor">
    {(edit.credentials_spec||[]).map((f:any)=><Field key={f.key} id={`provider-cred-${f.key}`} label={f.label+(f.required?'':' (optional)')} type={f.secret?'password':'text'} autoComplete="off" placeholder={edit.credentials_masked?.[f.key]?.configured?'•••••••• (saved)':f.placeholder||''} value={edit._input?.[f.key]??''} onChange={(e:any)=>setEdit({...edit,_input:{...(edit._input||{}),[f.key]:e.target.value}})}/>)}
    {(edit.settings_spec||[]).map((f:any)=>f.type==='select'?
      <Select key={f.key} id={`provider-setting-${f.key}`} label={f.label} value={edit._settings?.[f.key]??edit.config?.[f.key]??f.default??''} onChange={(e:any)=>setEdit({...edit,_settings:{...(edit._settings||{}),[f.key]:e.target.value}})}>{(f.options||[]).map((o:string)=><option key={o} value={o}>{o}</option>)}</Select>
      :<Field key={f.key} id={`provider-setting-${f.key}`} label={f.label} placeholder={f.help||(f.default||'')} value={edit._settings?.[f.key]??edit.config?.[f.key]??f.default??''} onChange={(e:any)=>setEdit({...edit,_settings:{...(edit._settings||{}),[f.key]:e.target.value}})}/>)}
    <Toggle id="provider-sandbox" label="Sandbox / test mode" value={!!edit.sandbox} onChange={(v:boolean)=>setEdit({...edit,sandbox:v})}/>
    <p className="form-error">{edit.error}</p>
    <div className="page-actions">
      <Btn id="provider-save-enable" type="submit" className="primary" disabled={busy}><ShieldCheck size={15}/>Verify & enable</Btn>
      <Btn id="provider-save-only" type="button" variant="outline" disabled={busy} onClick={()=>save(false)}>Save without enabling</Btn>
    </div>
   </form>}
  </Modal>
 </section>;
};
export default ProviderConfig;
export const TransactionsLog=()=>{
 const [rows,setRows]=useState<any[]|null>(null);
 const load=()=>get('/admin/transactions').then(setRows).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[]);
 if(!rows)return <Loading/>;
 return <section className="admin-panel" data-testid="transactions-log"><div className="panel-heading"><h2>Payment transactions</h2><Btn id="transactions-refresh" variant="outline" onClick={load}><RefreshCw size={15}/>Refresh</Btn></div>
 {rows.length?<div className="table-scroll"><table className="admin-table"><thead><tr><th>Order</th><th>Provider</th><th>Method</th><th>Amount</th><th>Status</th><th>Reference</th><th>Mode</th><th>Updated</th></tr></thead><tbody>{rows.map((t:any)=><tr key={t.id}><td className="mono">{t.order_number}</td><td>{t.provider}</td><td>{t.method_id}</td><td>{(t.amount/100).toLocaleString()} BDT</td><td><Status id={`tx-${t.id}`} value={t.status}/></td><td className="mono" style={{fontSize:11}}>{t.provider_ref||'—'}</td><td>{t.sandbox?'sandbox':'live'}</td><td>{new Date(t.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div>:<Empty title="No transactions yet." description="Online payment attempts appear here with their provider references and logs."/>}</section>;
};
