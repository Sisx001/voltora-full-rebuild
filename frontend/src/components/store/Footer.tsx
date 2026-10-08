import React,{useState} from 'react';
import {Link} from 'react-router-dom';
import {ArrowUpRight,ArrowRight,Check,ShieldCheck} from 'lucide-react';
import {Logo} from './Header';
import {useStore} from '../../lib/store';
import {post,message} from '../../lib/api';
import {toast} from 'sonner';

export const Footer=()=>{
 const {config}=useStore();const s=config.settings;const fc=s.footer_config||{};const [email,setEmail]=useState(''),[done,setDone]=useState(false);
 const subscribe=async(e:any)=>{e.preventDefault();try{await post('/newsletter',{email});setDone(true);}catch(err){toast.error(message(err));}};
 // website-builder site document: published footer columns override the classic layout
 const sf=config.site?.footer;const cols=(sf?.columns||[]).filter((c:any)=>c.enabled!==false);
 const hasCols=cols.length>0;
 const socialLinks=sf?(sf.social_links||[]):(fc.social_links||[]);
 const showSocial=sf?sf.show_social!==false:socialLinks.length>0;
 const badges=sf?(sf.payment_badges||[]):(fc.payment_badges||[]);
 const showPayments=sf?sf.show_payments!==false:badges.length>0;
 const legal=sf?(sf.legal_links||[]):s.footer_links.slice(6);
 const brandCol=cols.find((c:any)=>c.type==='brand');
 const Newsletter=()=>hasCols&&!cols.some((c:any)=>c.type==='newsletter')?null:
  <div className="footer-newsletter"><span className="eyebrow">GOOD TECH, IN YOUR INBOX</span><h2>{(cols.find((c:any)=>c.type==='newsletter')||{}).title||'Stay a little ahead.'}</h2><p>{(cols.find((c:any)=>c.type==='newsletter')||{}).text||'New finds, thoughtful edits, and store updates.'}</p><form onSubmit={subscribe}><input data-testid="newsletter-email" aria-label="Email for store updates" type="email" placeholder="Your email address" required value={email} onChange={e=>setEmail(e.target.value)}/><button data-testid="newsletter-submit" aria-label="Subscribe" type="submit">{done?<Check size={20}/>:<ArrowRight size={20}/>}</button></form><small data-testid="newsletter-state">{done?'You’re on the list. Thank you.':'By subscribing, you agree to receive store updates.'}</small></div>;
 const renderCol=(col:any,i:number)=>{
  if(col.type==='brand')return <div className="footer-brand" key={col.id}><Logo/><p data-testid="footer-tagline">{col.text||s.footer_text}</p><span className="footer-location" data-testid="footer-address">{s.address}</span>{s.email&&<a data-testid="footer-email" href={'mailto:'+s.email}>{s.email}</a>}{s.phone&&<a data-testid="footer-phone" href={'tel:'+s.phone}>{s.phone}</a>}</div>;
  if(col.type==='links')return <div key={col.id}><h2>{col.title}</h2>{(col.links&&col.links.length?col.links:s.footer_links.slice(0,6)).map((l:any,j:number)=><Link key={j} data-testid={`footer-link-${col.id}-${j}`} to={l.url}>{l.label}</Link>)}</div>;
  if(col.type==='text')return <div key={col.id}><h2>{col.title}</h2><p>{col.text}</p></div>;
  if(col.type==='social')return <div key={col.id}><h2>{col.title||'Follow along'}</h2>{(sf?.social_links||[]).filter((l:any)=>l.url.startsWith('https://')).map((l:any,j:number)=><a key={j} href={l.url} target="_blank" rel="noreferrer" data-testid={`footer-social-col-${col.id}-${j}`}>{l.label}</a>)}</div>;
  if(col.type==='newsletter')return <Newsletter key={col.id}/>;
  return null;
 };
 return <footer className={'store-footer footer-'+(sf?.style||'dark')}><div className="container footer-main">{hasCols?cols.map(renderCol):<><div className="footer-brand"><Logo/><p data-testid="footer-tagline">{s.footer_text}</p><span className="footer-location" data-testid="footer-address">{s.address}</span>{s.email&&<a data-testid="footer-email" href={'mailto:'+s.email}>{s.email}</a>}{s.phone&&<a data-testid="footer-phone" href={'tel:'+s.phone}>{s.phone}</a>}</div><div><h2>Explore</h2><Link data-testid="footer-all-products" to="/shop">All products</Link><Link data-testid="footer-new-arrivals" to="/shop?sort=newest">New arrivals</Link><Link data-testid="footer-audio" to="/shop?category=audio">Audio & sound</Link><Link data-testid="footer-accessories" to="/shop?category=accessories">Everyday essentials</Link></div><div><h2>We’re here to help</h2>{s.footer_links.slice(0,6).map((l:any,i:number)=><Link key={i} data-testid={`footer-page-${i}`} to={l.url}>{l.label}</Link>)}</div>{(sf?sf.show_payments!==false:fc.show_newsletter!==false)&&<Newsletter/>}</>}</div>{showSocial&&socialLinks.length>0&&<div className="container footer-social">{socialLinks.filter((l:any)=>l.url.startsWith('https://')).map((l:any,i:number)=><a key={i} href={l.url} target="_blank" rel="noreferrer" data-testid={`footer-social-${i}`}>{l.label}</a>)}</div>}{showPayments&&badges.length>0&&<div className="container footer-badges">{badges.map((b:string,i:number)=>b.startsWith('http')||b.startsWith('/')?<img key={i} className="payment-badge-img" data-testid={`footer-badge-${i}`} src={b} alt='payment'/>:<span key={i} className="payment-badge" data-testid={`footer-badge-${i}`}>{b}</span>)}</div>}<div className="container footer-bottom"><span data-testid="copyright">© {new Date().getFullYear()} {s.brand}.{(sf?sf.copyright:fc.copyright)?" "+(sf?sf.copyright:fc.copyright):" Thoughtfully connected."}</span><div>{legal.map((l:any,i:number)=><Link data-testid={`footer-legal-${i}`} key={i} to={l.url}>{l.label}</Link>)}<Link data-testid="admin-workspace-link" to="/admin">Store workspace <ArrowUpRight size={13}/></Link></div><span><ShieldCheck size={14}/> Secure shopping</span></div>{s.demo_catalog&&<div className="demo-disclosure" data-testid="demo-disclosure">Demonstration catalog · Fictional products and illustrative specifications. No online payments are currently connected.</div>}</footer>;
};
export const Consent=()=>{
 const [visible,setVisible]=useState(!localStorage.getItem('voltora-consent'));
 const choose=(value:boolean)=>{localStorage.setItem('voltora-consent',JSON.stringify({analytics:value,at:new Date().toISOString()}));setVisible(false);};
 if(!visible)return null;
 return <div className="cookie-consent" role="region" aria-label="Privacy preferences" data-testid="privacy-consent"><ShieldCheck size={18}/><p>Your privacy comes first.<br/><span>Essential cookies keep your bag and account working.</span></p><button data-testid="consent-essential" onClick={()=>choose(false)}>Essential only</button><button data-testid="consent-allow" onClick={()=>choose(true)}>Allow analytics</button></div>;
};
