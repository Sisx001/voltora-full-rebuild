import React,{useState,useEffect} from 'react';
import {KeyRound,ExternalLink} from 'lucide-react';
import {api,get,put,message} from '../../lib/api';
import {PageTitle,Btn,Field,Loading,Status,Modal} from '../../components/shared';
import {toast} from 'sonner';

export const OAuthProviders=()=>{
 const [data,setData]=useState<any>(null),[edit,setEdit]=useState<any>(null),[secret,setSecret]=useState('');
 const load=()=>get('/admin/oauth').then(setData).catch(e=>toast.error(message(e)));useEffect(()=>{load();},[]);
 if(!data)return <Loading/>;
 const save=async()=>{try{await put('/admin/oauth/'+edit.id,{client_id:edit.client_id,client_secret:secret,enabled:edit.enabled!==false});setEdit(null);setSecret('');load();toast.success('OAuth provider saved');}catch(e){toast.error(message(e));}};
 return <><PageTitle eyebrow="CONNECTIONS / SIGN-IN" title="Familiar ways to sign in." description="Customer social sign-in. Redirect URIs are fixed to this deployment — register them with each provider."/>
 <div className="provider-grid">{data.providers.map((p:any)=><div className="provider-card" key={p.id} data-testid={`oauth-${p.id}`}>
  <div className="provider-card-head"><div><b>{p.id.charAt(0).toUpperCase()+p.id.slice(1)}</b></div><Status id={`oauth-status-${p.id}`} value={p.connected?'connected':'not_configured'}/></div>
  <p className="small-note">Redirect URI: <span className="mono">{p.redirect_uri}</span></p>
  <div className="provider-card-actions">
   <Btn id={`oauth-configure-${p.id}`} variant="outline" onClick={()=>{setEdit({...p});setSecret('');}}><KeyRound size={14}/>{p.connected?'Update':'Set up'}</Btn>
   {p.connected&&<Btn id={`oauth-remove-${p.id}`} variant="outline" onClick={async()=>{try{await api.delete('/admin/oauth/'+p.id);load();toast.success('Provider removed');}catch(e){toast.error(message(e));}}}>Remove</Btn>}
   {p.id==='google'&&<a className="icon-btn" href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer" title="Google Cloud credentials"><ExternalLink size={15}/></a>}
   {p.id==='facebook'&&<a className="icon-btn" href="https://developers.facebook.com/apps" target="_blank" rel="noreferrer" title="Facebook App dashboard"><ExternalLink size={15}/></a>}
   {p.id==='apple'&&<a className="icon-btn" href="https://developer.apple.com/account/resources/identifiers/list/serviceId" target="_blank" rel="noreferrer" title="Apple developer"><ExternalLink size={15}/></a>}
  </div>
 </div>)}</div>
 <Modal open={!!edit} onClose={()=>setEdit(null)} title={`Configure ${edit?.id} sign-in`} description="The secret is encrypted at rest. Create the OAuth app with the exact redirect URI shown above.">
  {edit&&<form onSubmit={e=>{e.preventDefault();save();}}>
   <Field id="oauth-client-id" label="Client ID" required value={edit.client_id||''} onChange={(e:any)=>setEdit({...edit,client_id:e.target.value})}/>
   <Field id="oauth-client-secret" label={edit.connected?'New client secret (blank to keep)':'Client secret'} type="password" autoComplete="off" value={secret} onChange={(e:any)=>setSecret(e.target.value)}/>
   <Btn id="oauth-save" type="submit" className="primary">Save provider</Btn>
  </form>}</Modal></>;
};
export default OAuthProviders;
