import React,{useState,useEffect} from 'react';
import {RefreshCw,Search,Mail,FileText,Save,RotateCcw,Send} from 'lucide-react';
import {api,get,put,post,message,download} from '../../lib/api';
import {PageTitle,Btn,Loading,Empty,Status,Modal,Field,Toggle} from '../../components/shared';
import {toast} from 'sonner';

const SEV:any={healthy:'published',warning:'pending',critical:'failed'};

/* ---------- Email Theme Builder ---------- */
export const EmailThemeBuilder=()=>{
 const [theme,setTheme]=useState<any>(null),[preview,setPreview]=useState(''),[busy,setBusy]=useState(false);
 const load=async()=>{try{const t=await get('/admin/email-theme');setTheme({accent:'',button_color:'',logo:'',footer_text:'',...t});const r=await get('/admin/email-theme/preview');setPreview(r);}catch(e){toast.error(message(e));}};
 useEffect(()=>{load();},[]);
 const set=(k:string,v:any)=>setTheme((t:any)=>({...t,[k]:v}));
 const save=async()=>{setBusy(true);try{await put('/admin/email-theme',theme);await load();toast.success('Email theme saved — every branded email uses it now');}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 if(!theme)return <Loading/>;
 return <section className="admin-panel" data-testid="email-theme-builder" style={{marginTop:18}}>
  <div className="panel-heading"><h2>Email theme</h2><Status id="email-theme-status" value={theme.accent||theme.logo?'branded':'default'}/></div>
  <p className="small-note">Every transactional email (order updates, OTP, returns, marketing) is wrapped in this branding. Colors follow the storefront theme until you override them.</p>
  <div className="email-theme-grid">
   <div className="email-theme-fields">
    <label className="color-control"><span>Accent (header)</span><div><input data-testid="email-theme-accent" type="color" value={theme.accent||'#b9f46b'} onChange={e=>set('accent',e.target.value)}/><code>{theme.accent||'theme default'}</code></div></label>
    <label className="color-control"><span>Button color</span><div><input data-testid="email-theme-button" type="color" value={theme.button_color||theme.accent||'#b9f46b'} onChange={e=>set('button_color',e.target.value)}/><code>{theme.button_color||(theme.accent?'accent':'theme default')}</code></div></label>
    <Field id="email-theme-logo" label="Logo image URL (shown in the header)" value={theme.logo} onChange={(e:any)=>set('logo',e.target.value)}/>
    <Field id="email-theme-footer" label="Footer line" value={theme.footer_text} onChange={(e:any)=>set('footer_text',e.target.value)}/>
    <div className="page-actions"><Btn id="email-theme-save" className="primary" disabled={busy} onClick={save}><Save size={15}/>Save email theme</Btn><Btn id="email-theme-reset" variant="outline" onClick={()=>{setTheme({accent:'',button_color:'',logo:'',footer_text:''});}}><RotateCcw size={15}/>Clear overrides</Btn></div>
   </div>
   <div className="email-theme-preview">
    <span className="eyebrow">LIVE PREVIEW</span>
    <iframe title="Email theme preview" data-testid="email-theme-preview" sandbox="" referrerPolicy="no-referrer" srcDoc={preview} style={{width:'100%',height:420,border:'1px solid var(--v-border)',borderRadius:10,background:'#f4f5f3'}}/>
   </div>
  </div>
 </section>;
};

/* ---------- Diagnostics Center ---------- */
export const Diagnostics=()=>{
 const [data,setData]=useState<any>(null),[busy,setBusy]=useState(false);
 const scan=async()=>{setBusy(true);try{setData(await get('/admin/diagnostics'));}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 useEffect(()=>{scan();},[]);
 if(!data)return <Loading/>;
 const sections:string[]=Array.from(new Set<string>(data.checks.map((c:any)=>String(c.section))));
 return <><PageTitle eyebrow="ADMINISTRATION / DIAGNOSTICS" title="The whole store, scanned." description={data.note}><Btn id="diag-rescan" className="primary" disabled={busy} onClick={scan}><RefreshCw size={16}/>{busy?'Scanning...':'Re-scan'}</Btn></PageTitle>
 <div className="admin-metrics inventory-metrics">
  <div className="metric"><span>Healthy</span><strong data-testid="diag-healthy">{data.counts.healthy}</strong></div>
  <div className="metric"><span>Warnings</span><strong data-testid="diag-warning">{data.counts.warning}</strong></div>
  <div className="metric"><span>Critical</span><strong data-testid="diag-critical">{data.counts.critical}</strong></div>
  <div className="metric"><span>Scan time</span><strong style={{fontSize:16}}>{data.duration_ms} ms</strong></div>
 </div>
 {sections.map(sec=><section className="admin-panel" key={sec} style={{marginTop:20}}><div className="panel-heading"><h2>{sec}</h2></div>
  {data.checks.filter((c:any)=>c.section===sec).map((c:any,i:number)=><div className="health-service" key={i} data-testid={`diag-${c.severity}`}><span><b>{c.title}</b><small className="block">{c.detail}{c.fix?` — Fix: ${c.fix}`:''}</small></span><Status value={SEV[c.severity]}/></div>)}
 </section>)}</>;
};

/* ---------- API surface ---------- */
export const ApiSurface=()=>{
 const [data,setData]=useState<any>(null),[q,setQ]=useState('');
 const load=()=>get('/admin/diagnostics/api-surface').then(setData).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[]);
 if(!data)return <Loading/>;
 const rows=data.routes.filter((r:any)=>(r.path+r.area).toLowerCase().includes(q.toLowerCase()));
 return <><PageTitle eyebrow="ADMINISTRATION / API" title="Know your surface." description="Every live route, its methods, and its protection level - read straight from the running app."><Btn id="api-export" variant="outline" onClick={()=>download('voltora-api-surface.json',JSON.stringify(data.routes,null,2))}>Export JSON</Btn></PageTitle>
 <div className="admin-panel"><div className="table-toolbar"><h2>{data.count} routes</h2><div className="table-search"><Search size={16}/><input data-testid="api-search" placeholder="Filter routes..." value={q} onChange={e=>setQ(e.target.value)}/></div></div>
 <div className="table-scroll"><table className="admin-table"><thead><tr><th>Path</th><th>Methods</th><th>Protection</th></tr></thead><tbody>{rows.map((r:any)=><tr key={r.path+r.methods}><td className="mono" style={{fontSize:11}}>{r.path}</td><td>{r.methods}</td><td><Status id={`api-${r.path}`} value={r.area.startsWith('admin')?'published':r.area.startsWith('webhooks')?'awaiting_review':r.area.startsWith('auth')?'processing':'ready'}/><small className="block">{r.area}</small></td></tr>)}</tbody></table></div>
 <p className="small-note" style={{padding:'12px 24px 16px'}}>{data.note}</p></div></>;
};

/* ---------- Email templates ---------- */
export const EmailTemplates=()=>{
 const [data,setData]=useState<any>(null),[edit,setEdit]=useState<any>(null),[testTo,setTestTo]=useState('');
 const load=()=>get('/admin/email-templates').then(setData).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[]);
 const save=async()=>{try{await put('/admin/email-templates',{id:edit.id,subject:edit.subject,body:edit.body});load();toast.success('Template saved');}catch(e){toast.error(message(e));}};
 const reset=async(id:string)=>{try{await api.delete('/admin/email-templates/'+id);load();toast.success('Reset to default');}catch(e){toast.error(message(e));}};
 const testSend=async(id:string)=>{try{const r=await post(`/admin/email-templates/${id}/test-send`,{to_email:testTo});toast.success(r.note);}catch(e){toast.error(message(e));}};
 if(!data)return <Loading/>;
 return <><PageTitle eyebrow="CONNECTIONS / EMAIL" title="Emails that sound like you." description="Override the subject and body of every transactional email. Variables use {curly} placeholders and merge at send time."/>
 <EmailThemeBuilder/>
 {data.templates.map((t:any)=><section className="admin-panel" key={t.id} style={{marginTop:18}}><div className="panel-heading"><h2>{t.id.replaceAll('_',' ')}</h2><div>{t.custom&&<Status value="published"/>}<Btn id={`email-edit-${t.id}`} variant="outline" onClick={()=>setEdit({...t})}><FileText size={14}/>Edit</Btn></div></div>
  <p className="small-note" style={{margin:'-4px 24px 0'}}>Subject: {t.subject}</p>
  <pre className="email-preview">{t.body}</pre></section>)}
 <Modal open={!!edit} onClose={()=>setEdit(null)} title={`Edit template: ${edit?.id?.replaceAll('_','')}`} description="Plain text. Variables merge at send time.">
  {edit&&<form onSubmit={e=>{e.preventDefault();save();}} data-testid="email-editor">
   <Field id="email-subject" label="Subject" required value={edit.subject} onChange={(e:any)=>setEdit({...edit,subject:e.target.value})}/>
   <Field id="email-body" label="Body" as="textarea" rows={8} required value={edit.body} onChange={(e:any)=>setEdit({...edit,body:e.target.value})}/>
   {edit.variables.length>0&&<p className="small-note">Variables: {edit.variables.map((v:string)=>`{${v}}`).join(' ')}</p>}
   <div className="field-grid"><Field id="email-test-to" label="Send test to" type="email" value={testTo} onChange={(e:any)=>setTestTo(e.target.value)}/></div>
   <div className="page-actions">
    <Btn id="email-save" type="submit" className="primary"><Save size={15}/>Save override</Btn>
    <Btn id="email-test-send" variant="outline" onClick={()=>testSend(edit.id)}><Send size={15}/>Send test</Btn>
    {edit.custom&&<Btn id="email-reset" variant="outline" onClick={()=>reset(edit.id)}><RotateCcw size={15}/>Reset to default</Btn>}
   </div></form>}</Modal></>;
};
