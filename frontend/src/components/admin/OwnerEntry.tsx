import React, {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowRight, ArrowUpRight, LockKeyhole, ShieldCheck, Eye, EyeOff} from 'lucide-react';
import {get, post, message} from '../../lib/api';
import {useStore} from '../../lib/store';
import {Btn, Field} from '../shared';
import {Logo} from '../store/Header';
import './owner-entry.css';

export const OwnerEntry=()=>{
 const {login}=useStore();
 const [setup,setSetup]=useState(false),[ready,setReady]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const [name,setName]=useState(''),[email,setEmail]=useState(''),[password,setPassword]=useState(''),[visible,setVisible]=useState(false);
 const [key,setKey]=useState(()=>new URLSearchParams(window.location.hash.slice(1)).get('setup')||'');
 useEffect(()=>{if(window.location.hash.includes('setup='))window.history.replaceState(null,'',window.location.pathname);get('/auth/setup-status').then(r=>{setSetup(r.required);setReady(true);}).catch(e=>setError(message(e)));},[]);
 const submit=async(e:React.FormEvent)=>{e.preventDefault();setBusy(true);setError('');try{const data=await post('/auth/'+(setup?'setup':'login'),{email,password,...(setup?{name,setup_key:key}:{})});setKey('');login(data);}catch(e){setError(message(e));}finally{setBusy(false);}};
 return <div className="owner-entry" data-testid="owner-entry">
  <section className="owner-story"><div className="owner-brand"><Logo/><span>OWNER WORKSPACE</span></div><div className="owner-photo"><img src="/assets/voltora-headphones.jpg" alt="VOLTORA studio headphones"/><div className="owner-photo-caption"><span>CONSIDERED COMMERCE.</span><h1>Your vision.<br/>Every detail.</h1><p>A space to make it your own.</p></div></div><div className="owner-story-bottom"><span>VOLTORA / WORKSPACE 02</span><span>Thoughtfully connected.<ArrowUpRight size={15}/></span></div></section>
  <section className="owner-access"><Link to="/" data-testid="owner-back-store" className="owner-store-link">Visit storefront<ArrowUpRight size={15}/></Link><div className="owner-form-wrap"><div className="owner-lock"><LockKeyhole size={23}/></div><span className="owner-eyebrow">PRIVATE ACCESS</span><h2 data-testid="owner-heading">{setup?'Make it yours.':'Welcome back.'}</h2><p className="owner-intro">{setup?'Your store’s next chapter starts here.':'Your store. Your ideas. All in one place.'}</p><form onSubmit={submit}>
  {setup&&<Field id="owner-name" label="Full name" autoComplete="name" value={name} minLength={2} maxLength={80} required onChange={(e:any)=>setName(e.target.value)}/>}
  <Field id="owner-email" label="Email address" type="email" autoComplete="email" placeholder="you@yourstore.com" required value={email} onChange={(e:any)=>setEmail(e.target.value)}/>
  <div className="owner-password"><Field id="owner-password" label={setup?'Password · 12 characters minimum':'Password'} type={visible?'text':'password'} autoComplete={setup?'new-password':'current-password'} minLength={setup?12:1} maxLength={128} required value={password} onChange={(e:any)=>setPassword(e.target.value)}/><button type="button" data-testid="owner-toggle-password" aria-label={visible?'Hide password':'Show password'} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={17}/>:<Eye size={17}/>}</button></div>
  {setup&&<Field id="owner-setup-key" label="Private setup key" type="password" autoComplete="off" required value={key} onChange={(e:any)=>setKey(e.target.value)}/>}
  {error&&<p role="alert" className="owner-error" data-testid="owner-error">{error}</p>}
  <Btn id="owner-submit" type="submit" disabled={busy||!ready}>{busy?'Please wait…':setup?'Create owner account':'Open your workspace'}<ArrowRight size={17}/></Btn>
  </form><div className="owner-security"><ShieldCheck size={17}/><span>Private account. Two-factor protected.</span></div></div><footer className="owner-access-footer"><span className="owner-env"><i/>Isolated environment</span><span>External actions locked</span></footer></section>
 </div>;
};