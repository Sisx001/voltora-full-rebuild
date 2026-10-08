import React, {useCallback, useEffect, useState} from 'react';
import {ExternalLink, KeyRound, RefreshCw, ShieldCheck} from 'lucide-react';
import {api, get, put, message} from '../../lib/api';
import {Btn, Field, Loading, Empty, Modal, Select} from '../../components/shared';
import {useStore} from '../../lib/store';
import {toast} from 'sonner';
import './integration-center.css';

type Props = {kind:string; title:string; description:string; permUpdate?:boolean; environment?:string};
export default function ProviderConfigurationPanel({kind,title,description,permUpdate=true,environment:controlledEnvironment}:Props) {
 const {user} = useStore();
 const [selectedEnvironment,setSelectedEnvironment]=useState('sandbox');
 const environment=controlledEnvironment||selectedEnvironment;
 const [rows,setRows]=useState<any[]|null>(null),[edit,setEdit]=useState<any>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const canManage=permUpdate&&user?.role==='owner';
 const load=useCallback(async()=>{setError('');try{setRows(await get(`/admin/providers/${kind}?environment=${environment}`));}catch(e){setError(message(e));}},[kind,environment]);
 useEffect(()=>{setRows(null);setEdit(null);load();},[load]);
 const path=(row:any,action='')=>`/admin/providers/${kind}/${row.id}${action}?environment=${environment}${row.messaging_kind?'&channel='+encodeURIComponent(row.messaging_kind):''}`;
 const openEditor=async(row:any)=>{try{setEdit(await get(path(row)));}catch(e){toast.error(message(e));}};
 const save=async()=>{setBusy(true);try{
  await put(path(edit),{credentials:edit._input||{},clear_credentials:edit._clear||[],config:edit._settings||{},sandbox:environment==='sandbox',enabled:false,expected_version:edit.version});
  setEdit(null);await load();toast.success('Saved locally. Provider remains disabled; no external request was sent.');
 }catch(e){toast.error(message(e));}finally{setBusy(false);}};
 const verify=async(row:any)=>{
  if(!window.confirm(`Contact ${row.label} using the saved sandbox credentials for a connection-only check? No charge, message or shipment will be created. This does not verify the complete workflow.`))return;
  setBusy(true);try{const r:any=await api.post(path(row,'/verify'),{expected_version:row.version,confirmation:'CHECK CONNECTION'});toast[r.ok?'success':'error'](r.message);await load();}catch(e){toast.error(message(e));}finally{setBusy(false);}
 };
 const disable=async(row:any)=>{setBusy(true);try{await api.delete(path(row)+`&expected_version=${row.version}`);await load();toast.success('Disabled. Credentials and history retained.');}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 return <section className="admin-panel integration-panel" data-testid={`providers-${kind}`}>
  <div className="panel-heading"><h2>{title}</h2>{!controlledEnvironment&&<select aria-label={`${title} environment`} value={environment} onChange={e=>setSelectedEnvironment(e.target.value)}><option value="sandbox">Sandbox configuration</option><option value="production">Production configuration</option></select>}</div>
  <p className="small-note integration-description">{description}</p>
  {error?<div role="alert" className="integration-error">{error}<Btn id={`retry-providers-${kind}`} variant="outline" onClick={load}>Retry</Btn></div>:!rows?<Loading/>:rows.length?<div className="provider-grid">{rows.map(row=><article className="provider-card" key={row.messaging_kind+row.id} data-testid={`provider-${row.id}`}>
   <div className="provider-card-head"><div><b>{row.label}</b><p className="small-note">{row.messaging_kind||kind} · {environment} · v{row.version}</p></div><span className="integration-badge">{row.enabled?'Enabled':'Disabled'}</span></div>
   <dl className="integration-evidence">
    <div><dt>Implementation</dt><dd>Adapter present · workflow unverified</dd></div>
    <div><dt>Credentials</dt><dd>{row.credentials_complete?'Required fields saved':row.configured?'Incomplete':'Not configured'}</dd></div>
    <div><dt>Connection check</dt><dd>{row.connection?.status||'unverified'}{row.connection?.version?` · v${row.connection.version}`:''}</dd></div>
    <div><dt>End-to-end workflow</dt><dd>{row.workflow?.status||'unverified'}</dd></div>
    <div><dt>Current health</dt><dd>{row.health?.status||'unknown'}</dd></div>
    <div><dt>Runtime actions</dt><dd>{row.external_actions_enabled?'Allowed by runtime gate':'Locked'}</dd></div>
   </dl>
   <p className="small-note">{row.setup_note}</p>
   {row.error&&<p role="alert" className="form-error">{row.error}</p>}
   {row.last_verified&&<p className="small-note">Last connection check: {new Date(row.last_verified).toLocaleString()}</p>}
   <div className="provider-card-actions">
    {canManage&&<><Btn id={`provider-configure-${row.id}`} variant="outline" disabled={busy} onClick={()=>openEditor(row)}><KeyRound size={14}/>{row.configured?'Edit configuration':'Set up'}</Btn>
     <Btn id={`provider-verify-${row.id}`} variant="outline" disabled={busy||!row.credentials_complete||!row.connection_check_supported} onClick={()=>verify(row)}><RefreshCw size={14}/>Check connection</Btn>
     {row.enabled&&<Btn id={`provider-disconnect-${row.id}`} variant="outline" disabled={busy} onClick={()=>disable(row)}>Disable</Btn>}
    </>}
    {row.docs_url&&<a href={row.docs_url} target="_blank" rel="noreferrer" className="text-link">Setup documentation<ExternalLink size={14}/></a>}
   </div>
   {!row.connection_check_supported&&<p className="small-note">{row.sandbox_support==='not_available'?'No general sandbox. Controlled verification requires a dedicated account and separate approval.':'A reviewed connection check is not available for this environment.'}</p>}
   <details className="integration-history"><summary>Configuration history ({row.history?.length||0})</summary>{row.history?.length?<ol>{[...row.history].reverse().map((h:any,i:number)=><li key={i}>v{h.version} · {h.action.replaceAll('_',' ')} · {new Date(h.at).toLocaleString()}</li>)}</ol>:<p>No saved changes in this environment.</p>}</details>
  </article>)}</div>:<Empty title="No operational adapter registered" description="No mock provider will be substituted. A real adapter and authorized account are required."/>}
  <Modal open={!!edit} onClose={()=>!busy&&setEdit(null)} title={`${edit?.label||'Provider'} · ${environment}`} description="Secrets are encrypted and write-only. Blank fields keep saved values. Saving never contacts or enables a provider.">
   {edit&&<form onSubmit={e=>{e.preventDefault();save();}} data-testid="provider-editor">
    <p className="small-note">Configuration v{edit.version}. {edit.missing_fields?.length?`Missing required fields: ${edit.missing_fields.join(', ')}`:'Required fields are saved.'}</p>
    {(edit.credentials_spec||[]).map((f:any)=><div key={f.key}><Field id={`provider-cred-${f.key}`} label={f.label+(f.required?'':' (optional)')} type="password" autoComplete="new-password" placeholder={edit.credentials_masked?.[f.key]?.configured?'Saved · leave blank to keep':f.placeholder||''} value={edit._input?.[f.key]??''} onChange={(e:any)=>setEdit({...edit,_input:{...(edit._input||{}),[f.key]:e.target.value}})}/>{edit.credentials_masked?.[f.key]?.configured&&<label className="integration-clear"><input type="checkbox" checked={(edit._clear||[]).includes(f.key)} onChange={e=>setEdit({...edit,_clear:e.target.checked?[...(edit._clear||[]),f.key]:(edit._clear||[]).filter((k:string)=>k!==f.key)})}/>Remove saved {f.label}</label>}</div>)}
    {(edit.settings_spec||[]).map((f:any)=>f.type==='select'?<Select key={f.key} id={`provider-setting-${f.key}`} label={f.label} value={edit._settings?.[f.key]??edit.config?.[f.key]??f.default??''} onChange={(e:any)=>setEdit({...edit,_settings:{...(edit._settings||{}),[f.key]:e.target.value}})}>{(f.options||[]).map((o:string)=><option key={o} value={o}>{o}</option>)}</Select>:<Field key={f.key} id={`provider-setting-${f.key}`} label={f.label} value={edit._settings?.[f.key]??edit.config?.[f.key]??f.default??''} onChange={(e:any)=>setEdit({...edit,_settings:{...(edit._settings||{}),[f.key]:e.target.value}})}/>)}
    <div className="integration-lock"><ShieldCheck size={18}/><p>Saving disables this configuration. Credential or settings changes invalidate its verification. Production activation is separate.</p></div>
    <Btn id="provider-save-only" type="submit" className="primary" disabled={busy}>{busy?'Saving…':'Save configuration'}</Btn>
   </form>}
  </Modal>
 </section>;
}
