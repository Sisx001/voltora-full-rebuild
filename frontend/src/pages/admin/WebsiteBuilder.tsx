import React,{useState,useEffect,useRef} from 'react';
import {Palette,LayoutTemplate,PanelTop,PanelBottom,LogIn,CreditCard,Save,Upload,History,Undo2,Redo2,Plus,Trash2,ChevronUp,ChevronDown} from 'lucide-react';
import {get,put,post,message,download} from '../../lib/api';
import {useStore} from '../../lib/store';
import {PageTitle,Btn,Field,Modal,Loading,Status,Toggle,Empty} from '../../components/shared';
import {ThemeStudio,PageBuilder,PreviewWindow,DevicePicker,RevisionHistory} from './DesignStudio';
import {toast} from 'sonner';

const SCREENS=[['design','Design & theme',Palette],['home','Homepage',LayoutTemplate],['header','Header & navigation',PanelTop],['footer','Footer',PanelBottom],['auth','Login & signup',LogIn],['checkout','Checkout',CreditCard]] as const;
export const WebsiteBuilder=()=>{
 const [screen,setScreen]=useState(()=>new URLSearchParams(window.location.search).get('screen')||'design');
 return <><PageTitle eyebrow="WEBSITE BUILDER" title="One editor. The whole website." description="Design, homepage, header, footer, login and checkout — every screen, live preview as you edit."/>
  <div className="table-tabs wb-tabs">{SCREENS.map(([id,label,Icon]:any)=><button key={id} data-testid={'wb-screen-'+id} className={screen===id?'active':''} onClick={()=>setScreen(id)}><Icon size={16}/>{label}</button>)}</div>
  <div className="wb-screen">{screen==='design'&&<ThemeStudio/>}{screen==='home'&&<PageBuilder autoOpenSlug="home"/>}{['header','footer','auth','checkout'].includes(screen)&&<SitePanel key={screen} kind={screen}/>}</div></>;
};

const PUSH={type:'voltora-site-preview'};
const SitePanel=({kind}:{kind:string})=>{
 const {user,refreshConfig}=useStore();
 const [doc,setDoc]=useState<any>(null),[draft,setDraft]=useState<any>(null),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[history,setHistory]=useState(false),[past,setPast]=useState<any[]>([]),[future,setFuture]=useState<any[]>([]),[device,setDevice]=useState('desktop');
 const frameRef=useRef<HTMLIFrameElement>(null);const draftRef=useRef<any>(null);const previewAreaRef=useRef<HTMLDivElement>(null);
 const [zoomInfo,setZoomInfo]=useState({zoom:1,frameW:1440,frameH:800});
 const load=async()=>{try{const d=await get('/admin/documents/site');setDoc(d);setDraft(d.draft);setDirty(false);setPast([]);setFuture([]);}catch(e){toast.error(message(e));}};
 useEffect(()=>{load();},[kind]);
 useEffect(()=>{draftRef.current=draft;},[draft]);
 useEffect(()=>{const el=previewAreaRef.current;if(!el)return;const update=()=>{const w=el.clientWidth-4,h=el.clientHeight-30-4;if(w<80||h<120)return;const target=device==='mobile'?390:device==='tablet'?768:1440;const z=Math.min(1,w/target);setZoomInfo({zoom:z,frameW:target,frameH:Math.max(1500,Math.round(h/z))});};update();const ro=new ResizeObserver(update);ro.observe(el);return()=>ro.disconnect();},[device]);
 useEffect(()=>{const beat=setInterval(()=>{if(draftRef.current&&frameRef.current?.contentWindow)try{frameRef.current.contentWindow.postMessage({...PUSH,site:draftRef.current},window.location.origin);}catch{}},2000);return()=>clearInterval(beat);},[]);
 useEffect(()=>()=>{try{frameRef.current?.contentWindow?.postMessage({type:'voltora-site-preview-end'},window.location.origin);}catch{}},[]);
 const pushLive=(next:any)=>{try{frameRef.current?.contentWindow?.postMessage({...PUSH,site:next},window.location.origin);}catch{}};
 const mutate=(next:any)=>{setPast(p=>[...p.slice(-29),draft]);setFuture([]);setDraft(next);setDirty(true);pushLive(next);};
 const undo=()=>{if(!past.length||!draft)return;const prev=past[past.length-1];setPast(p=>p.slice(0,-1));setFuture(f=>[draft,...f].slice(0,30));setDraft(prev);pushLive(prev);setDirty(true);};
 const redo=()=>{if(!future.length||!draft)return;const next=future[0];setFuture(f=>f.slice(1));setPast(p=>[...p.slice(-29),draft]);setDraft(next);pushLive(next);setDirty(true);};
 const part=draft?.[kind]||{};
 const setPart=(patch:any)=>mutate({...draft,[kind]:{...part,...patch}});
 const save=async()=>{const r=await put('/admin/documents/site',{value:draft,version:doc.version});setDoc({...doc,version:r.version});setDirty(false);return r.version;};
 const action=async(type:string)=>{setBusy(true);try{const version=await save();if(type==='publish'){await post('/admin/documents/site/publish',{version,summary:'Published '+kind+' builder changes'});await load();refreshConfig();try{localStorage.setItem('voltora-theme-version',String(Date.now()));}catch{}toast.success('Live — the storefront is updated');}else toast.success('Draft saved');}catch(e){toast.error(message(e));}finally{setBusy(false);}};
 if(!draft||!doc)return <Loading/>;
 const titles:any={header:'Header & navigation',footer:'Footer',auth:'Login & signup',checkout:'Checkout'};
 return <>
  <div className="builder-heading"><div><div><h1>{titles[kind]}</h1><span data-testid="site-builder-save-status"><i/>{dirty?'Unsaved changes':'Draft in sync with live'}</span></div></div><div className="page-actions">
   <Btn id="site-undo" variant="outline" disabled={!past.length} onClick={undo}><Undo2 size={15}/>Undo</Btn>
   <Btn id="site-redo" variant="outline" disabled={!future.length} onClick={redo}><Redo2 size={15}/>Redo</Btn>
   <Btn id="site-history" variant="outline" onClick={()=>setHistory(true)}><History size={16}/>History</Btn>
   {user.permissions.includes('content.update')&&<Btn id="site-save" variant="outline" disabled={busy} onClick={()=>action('save')}><Save size={16}/>Save draft</Btn>}
   {user.permissions.includes('content.publish')&&<Btn id="site-publish" className="primary" disabled={busy} onClick={()=>action('publish')}><Upload size={16}/>Publish</Btn>}
  </div></div>
  <div className="site-builder">
   <aside className="site-inspector">
    {kind==='header'&&<HeaderInspector part={part} setPart={setPart}/>}
    {kind==='footer'&&<FooterInspector part={part} setPart={setPart}/>}
    {kind==='auth'&&<AuthInspector part={part} setPart={setPart}/>}
    {kind==='checkout'&&<CheckoutInspector part={part} setPart={setPart}/>}
   </aside>
   <div className="site-preview">
    <div className="preview-toolbar"><span data-testid="site-live-preview-note">Live preview · draft applied instantly · navigate the real store</span><DevicePicker device={device} onChange={setDevice}/></div>
    <div className={'preview-window device-'+device} ref={previewAreaRef}><div className="preview-browser"><span/><span/><span/><b>{titles[kind]} — live draft</b></div><div className="preview-viewport"><iframe name="voltora-preview" ref={frameRef} data-testid="site-live-frame" src="/" title="Live site preview" style={{width:zoomInfo.frameW+'px',height:zoomInfo.frameH+'px',zoom:String(zoomInfo.zoom)}} onLoad={()=>draft&&pushLive(draft)}/></div></div>
   </div>
  </div>
  {history&&<RevisionHistory docId="site" version={doc.version} onRestore={(d:any)=>{setDoc({...doc,version:d.version});setDraft(d.draft);setDirty(false);}} onClose={()=>setHistory(false)}/>}
 </>;
};

/* ---------------- header ---------------- */
const TOP_TYPES=[['announcement','Announcement bar'],['utility_message','Utility message'],['track_order','Track order link'],['support_link','Support link'],['language','Language picker'],['currency','Currency picker']];
const MAIN_TYPES=[['menu','Mobile menu button'],['logo','Logo'],['search','Search bar']];
const ACTION_TYPES=[['notifications','Notifications bell'],['dark_mode','Dark mode toggle'],['account','Account'],['wishlist','Wishlist'],['compare','Compare'],['cart','Cart']];
const blockLabelUsed=(b:any)=>['utility_message','track_order','support_link'].includes(b.type);
const blockUrlUsed=(b:any)=>['support_link'].includes(b.type);
const HeaderInspector=({part,setPart}:any)=>{
 const zoneRow=(zone:string,label:string,types:any[])=>{
  const rows=(part[zone]||[]);
  const remaining=types.filter(([t]:any)=>!rows.some((b:any)=>b.type===t));
  const move=(i:number,dir:number)=>{const next=[...rows];const j=i+dir;if(j<0||j>=next.length)return;[next[i],next[j]]=[next[j],next[i]];setPart({[zone]:next});};
  return <div className="wb-zone"><h3>{label}</h3>{rows.map((b:any,i:number)=><div className={'block-row'+(b.enabled===false?' off':'')} key={b.id||i} data-testid={`header-block-${b.type}`}>
    <button className="icon-btn" title={b.enabled===false?'Show':'Hide'} onClick={()=>setPart({[zone]:rows.map((x:any,j:number)=>j===i?{...x,enabled:x.enabled===false?true:false}:x)})}>{b.enabled===false?'·':'✓'}</button>
    <div className="block-row-main"><b>{(types.find(([t]:any)=>t===b.type)||[b.type,b.type])[1]}</b>
     {blockLabelUsed(b)&&<Field id={`hb-${b.type}-label`} label="Label" value={b.label||''} onChange={(e:any)=>setPart({[zone]:rows.map((x:any,j:number)=>j===i?{...x,label:e.target.value}:x)})}/>}
     {blockUrlUsed(b)&&<Field id={`hb-${b.type}-url`} label="Links to" value={b.url||''} onChange={(e:any)=>setPart({[zone]:rows.map((x:any,j:number)=>j===i?{...x,url:e.target.value}:x)})}/>}
    </div>
    <div><button className="icon-btn" aria-label="Move up" disabled={i===0} onClick={()=>move(i,-1)}><ChevronUp size={13}/></button><button className="icon-btn" aria-label="Move down" disabled={i===rows.length-1} onClick={()=>move(i,1)}><ChevronDown size={13}/></button></div>
   </div>)}
   {remaining.length>0&&<select data-testid={`header-add-${zone}`} aria-label={'Add to '+label} value="" onChange={(e:any)=>{if(!e.target.value)return;const [t]:any=types.find(([tt]:any)=>tt===e.target.value);setPart({[zone]:[...rows,{id:t+'-'+Math.random().toString(36).slice(2,6),type:t,enabled:true}]});}}><option value="">+ Add block…</option>{remaining.map(([t,l]:any)=><option key={t} value={t}>{l}</option>)}</select>}
  </div>;
 };
 return <>
  <Field id="header-layout" label="Header layout" as="select" value={part.layout||'classic'} onChange={(e:any)=>setPart({layout:e.target.value})}>{['classic','centered','compact','bordered'].map(o=><option key={o}>{o}</option>)}</Field>
  <Toggle id="header-sticky" label="Sticky header" value={part.sticky!==false} onChange={(v:boolean)=>setPart({sticky:v})}/>
  <Toggle id="header-show-nav" label="Show navigation bar" value={part.show_nav!==false} onChange={(v:boolean)=>setPart({show_nav:v})}/>
  <Toggle id="header-show-browse" label="Show browse-categories menu" value={part.show_browse!==false} onChange={(v:boolean)=>setPart({show_browse:v})}/>
  <Field id="header-deal-label" label="Nav highlight label" value={part.nav_deal_label||''} onChange={(e:any)=>setPart({nav_deal_label:e.target.value})}/>
  <Field id="header-utility-message" label="Utility message" value={part.utility_message||''} onChange={(e:any)=>setPart({utility_message:e.target.value})}/>
  {zoneRow('top','Top strip',TOP_TYPES)}
  {zoneRow('main','Main row',MAIN_TYPES)}
  {zoneRow('actions','Action icons',ACTION_TYPES)}
 </>;
};

/* ---------------- footer ---------------- */
const COL_TYPES=[['brand','Brand & contact'],['links','Link group'],['newsletter','Newsletter'],['social','Social links'],['text','Free text']];
const LinksEditor=({links,onChange,testPrefix}:any)=><div className="wb-links">{links.map((l:any,i:number)=><div className="wb-link-row" key={i}>
  <Field id={`${testPrefix}-label-${i}`} label="Label" value={l.label||''} onChange={(e:any)=>onChange(links.map((x:any,j:number)=>j===i?{...x,label:e.target.value}:x))}/>
  <Field id={`${testPrefix}-url-${i}`} label="Links to" value={l.url||''} onChange={(e:any)=>onChange(links.map((x:any,j:number)=>j===i?{...x,url:e.target.value}:x))}/>
  <button className="icon-btn" data-testid={`${testPrefix}-remove-${i}`} aria-label="Remove link" onClick={()=>onChange(links.filter((_:any,j:number)=>j!==i))}><Trash2 size={14}/></button>
 </div>)}<Btn variant="outline" onClick={()=>onChange([...links,{label:'New link',url:'/shop'}])}><Plus size={14}/>Add link</Btn></div>;
const FooterInspector=({part,setPart}:any)=>{
 const cols=part.columns||[];
 const setCol=(i:number,patch:any)=>setPart({columns:cols.map((c:any,j:number)=>j===i?{...c,...patch}:c)});
 const move=(i:number,dir:number)=>{const j=i+dir;if(j<0||j>=cols.length)return;const next=[...cols];[next[i],next[j]]=[next[j],next[i]];setPart({columns:next});};
 const list=(v:string[])=>v.filter(Boolean);
 return <>
  <Field id="footer-style" label="Footer style" as="select" value={part.style||'dark'} onChange={(e:any)=>setPart({style:e.target.value})}>{['dark','light','minimal'].map(o=><option key={o}>{o}</option>)}</Field>
  <h3>Footer columns</h3>
  {cols.map((c:any,i:number)=><div className={'wb-col'+(c.enabled===false?' off':'')} key={c.id} data-testid={`footer-col-${c.id}`}>
   <div className="wb-col-head"><select aria-label="Column type" value={c.type} onChange={(e:any)=>setCol(i,{type:e.target.value})}>{COL_TYPES.map(([t,l]:any)=><option key={t} value={t}>{l}</option>)}</select>
    <button className="icon-btn" title={c.enabled===false?'Show column':'Hide column'} onClick={()=>setCol(i,{enabled:c.enabled===false})}>{c.enabled===false?'·':'✓'}</button>
    <button className="icon-btn" aria-label="Move up" disabled={i===0} onClick={()=>move(i,-1)}><ChevronUp size={13}/></button>
    <button className="icon-btn" aria-label="Move down" disabled={i===cols.length-1} onClick={()=>move(i,1)}><ChevronDown size={13}/></button>
    <button className="icon-btn" data-testid={`footer-col-remove-${c.id}`} aria-label="Remove column" onClick={()=>setPart({columns:cols.filter((_:any,j:number)=>j!==i)})}><Trash2 size={14}/></button></div>
   {c.type!=='brand'&&<Field id={`footer-col-${c.id}-title`} label="Heading" value={c.title||''} onChange={(e:any)=>setCol(i,{title:e.target.value})}/>}
   {['brand','text','newsletter'].includes(c.type)&&<Field id={`footer-col-${c.id}-text`} label={c.type==='newsletter'?'Short line under the heading':'Text'} as={c.type==='brand'?'textarea':'input'} value={c.text||''} onChange={(e:any)=>setCol(i,{text:e.target.value})}/>}
   {c.type==='links'&&<LinksEditor testPrefix={`footer-col-${c.id}`} links={c.links||[]} onChange={(next:any)=>setCol(i,{links:next})}/>}
  </div>)}
  {cols.length<6&&<select data-testid="footer-add-column" aria-label="Add footer column" value="" onChange={(e:any)=>{if(!e.target.value)return;const t=e.target.value;setPart({columns:[...cols,{id:t+'-'+Math.random().toString(36).slice(2,6),type:t,enabled:true,title:'',text:'',links:[]}]});}}><option value="">+ Add column…</option>{COL_TYPES.map(([t,l]:any)=><option key={t} value={t}>{l}</option>)}</select>}
  <h3>Social & payments</h3>
  <Toggle id="footer-show-social" label="Show social links" value={part.show_social!==false} onChange={(v:boolean)=>setPart({show_social:v})}/>
  <LinksEditor testPrefix="footer-social" links={part.social_links||[]} onChange={(next:any)=>setPart({social_links:next})}/>
  <Toggle id="footer-show-payments" label="Show payment badges" value={part.show_payments!==false} onChange={(v:boolean)=>setPart({show_payments:v})}/>
  <Field id="footer-badges" label="Payment badges (comma-separated labels or image URLs)" value={(part.payment_badges||[]).join(', ')} onChange={(e:any)=>setPart({payment_badges:list(e.target.value.split(','))})}/>
  <h3>Bottom bar</h3>
  <Field id="footer-copyright" label="Copyright note" value={part.copyright||''} onChange={(e:any)=>setPart({copyright:e.target.value})}/>
  <LinksEditor testPrefix="footer-legal" links={part.legal_links||[]} onChange={(next:any)=>setPart({legal_links:next})}/>
 </>;
};

/* ---------------- auth ---------------- */
const AuthInspector=({part,setPart}:any)=>{
 const bullets=(part.side_bullets||[]);
 return <>
  <Field id="auth-layout" label="Layout" as="select" value={part.layout||'split'} onChange={(e:any)=>setPart({layout:e.target.value})}>{['split','card','centered'].map(o=><option key={o}>{o}</option>)}</Field>
  <h3>Welcome panel</h3>
  <Field id="auth-side-heading" label="Headline (Enter for line breaks)" as="textarea" value={part.side_heading||''} onChange={(e:any)=>setPart({side_heading:e.target.value})}/>
  <Field id="auth-side-text" label="Sub-line" as="textarea" value={part.side_text||''} onChange={(e:any)=>setPart({side_text:e.target.value})}/>
  <Field id="auth-side-image" label="Panel image URL" value={part.side_image||''} onChange={(e:any)=>setPart({side_image:e.target.value})}/>
  <Field id="auth-side-bullets" label="Highlights (one per line)" as="textarea" value={bullets.join('\n')} onChange={(e:any)=>setPart({side_bullets:e.target.value.split('\n').slice(0,6)})}/>
  <h3>Sign-in options</h3>
  <Toggle id="auth-allow-email" label="Email & password sign-in" value={part.allow_email!==false} onChange={(v:boolean)=>setPart({allow_email:v})}/>
  <Toggle id="auth-allow-otp" label="Phone code (OTP) sign-in" value={part.allow_otp!==false} onChange={(v:boolean)=>setPart({allow_otp:v})}/>
  <Toggle id="auth-allow-social" label="Social sign-in buttons" value={part.allow_social!==false} onChange={(v:boolean)=>setPart({allow_social:v})}/>
  <Toggle id="auth-show-register" label="Show create-account switch" value={part.show_register!==false} onChange={(v:boolean)=>setPart({show_register:v})}/>
  <Field id="auth-card-note" label="Footer note on the form" value={part.card_note||''} onChange={(e:any)=>setPart({card_note:e.target.value})}/>
 </>;
};

/* ---------------- checkout ---------------- */
const LOCKED=['name','email','phone','address','city'];
const CheckoutInspector=({part,setPart}:any)=>{
 const fields=part.fields||[];
 const setField=(key:string,patch:any)=>setPart({fields:fields.map((f:any)=>f.key===key?{...f,...patch}:f)});
 return <>
  <Field id="checkout-layout" label="Layout" as="select" value={part.layout||'two_column'} onChange={(e:any)=>setPart({layout:e.target.value})}>{['two_column','single'].map(o=><option key={o}>{o}</option>)}</Field>
  <h3>Checkout fields</h3>
  <p className="small-note">Required-by-payment fields (name, email, phone, address, city) can be relabelled but not removed — the order system needs them.</p>
  {fields.map((f:any)=><div className={'wb-field-row'+(f.enabled===false?' off':'')} key={f.key} data-testid={`checkout-field-${f.key}`}>
   <Toggle id={`cf-enabled-${f.key}`} label={f.key.replaceAll('_',' ')} value={f.enabled!==false} onChange={(v:boolean)=>LOCKED.includes(f.key)?toast.error('The order system requires this field'):setField(f.key,{enabled:v})}/>
   <Field id={`cf-label-${f.key}`} label="Label shown to customers" value={f.label||''} onChange={(e:any)=>setField(f.key,{label:e.target.value})}/>
   <Toggle id={`cf-required-${f.key}`} label="Required" value={LOCKED.includes(f.key)?true:f.required!==false} onChange={(v:boolean)=>LOCKED.includes(f.key)?toast.error('The order system requires this field'):setField(f.key,{required:v})}/>
  </div>)}
  <Toggle id="checkout-show-coupon" label="Coupon box" value={part.show_coupon!==false} onChange={(v:boolean)=>setPart({show_coupon:v})}/>
  <Field id="checkout-terms-label" label="Terms line" value={part.terms_label||''} onChange={(e:any)=>setPart({terms_label:e.target.value})}/>
  <Field id="checkout-trust" label="Trust badges (comma-separated)" value={(part.trust_badges||[]).join(', ')} onChange={(e:any)=>setPart({trust_badges:e.target.value.split(',').map((x:string)=>x.trim()).filter(Boolean).slice(0,6)})}/>
  <h3>Thank-you page</h3>
  <Field id="checkout-thanks-title" label="Confirmation headline" value={part.thank_you_title||''} onChange={(e:any)=>setPart({thank_you_title:e.target.value})}/>
  <Field id="checkout-thanks-message" label="Confirmation note" as="textarea" value={part.thank_you_message||''} onChange={(e:any)=>setPart({thank_you_message:e.target.value})}/>
 </>;
};
