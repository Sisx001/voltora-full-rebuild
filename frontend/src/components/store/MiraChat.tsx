import React,{useState,useEffect,useRef} from 'react';
import {Sparkles,X,Send,Headset,Loader2,Bot,MessageCircle} from 'lucide-react';
import {useStore} from '../../lib/store';
import {get,post,API_ROOT,message} from '../../lib/api';
import {useLocation,useNavigate} from 'react-router-dom';
import {toast} from 'sonner';

const pageKey=(path:string):string=>{
 if(path==='/')return 'home';
 if(path.startsWith('/shop'))return 'shop';
 if(path.startsWith('/product/'))return 'product';
 if(path.startsWith('/cart'))return 'cart';
 if(path.startsWith('/checkout'))return 'checkout';
 if(path.startsWith('/account'))return 'account';
 if(path.startsWith('/support'))return 'support';
 if(path.startsWith('/assistant'))return 'assistant';
 if(path.startsWith('/pages/'))return 'page';
 return '';
};

/** Mira — the friendly VOLTORA shopping assistant. Floating storefront widget. */
export const MiraChat=()=>{
 const {config,user}=useStore();const navigate=useNavigate();const loc=useLocation();
 const mc:any=config?.settings?.mira_config||{};
 const [open,setOpen]=useState(false),[messages,setMessages]=useState<any[]>([]),[input,setInput]=useState(''),[busy,setBusy]=useState(false),[convId,setConvId]=useState(()=>localStorage.getItem('mira-conversation')||''),[shown,setShown]=useState(!mc.delay_ms);
 const boxRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(!shown&&mc.delay_ms>0){const t=setTimeout(()=>setShown(true),+mc.delay_ms||0);return()=>clearTimeout(t);}},[shown]);
 useEffect(()=>{const el=boxRef.current;if(el&&open)el.scrollTop=el.scrollHeight;},[messages,busy,open]);
 const send=async(e:any,text?:string)=>{e&&e.preventDefault();const body=(text||input).trim();if(!body||busy)return;setInput('');setMessages(m=>[...m,{role:'user',text:body}]);setBusy(true);
  try{const response=await fetch(`${API_ROOT}/assistant/chat`,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:convId,message:body})});
   if(!response.ok){const r=await response.json();throw new Error(r.detail);}
   const reader=response.body!.getReader();const decoder=new TextDecoder();let buffer='';let output='';let cid='';
   while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const chunks=buffer.split('\n\n');buffer=chunks.pop()||'';
    for(const chunk of chunks){if(!chunk.startsWith('data:'))continue;const ev=JSON.parse(chunk.slice(5));if(ev.text)output=ev.text;if(ev.conversation_id)cid=ev.conversation_id;if(ev.error)toast.error(ev.error);}}
   if(cid){setConvId(cid);localStorage.setItem('mira-conversation',cid);}
   setMessages(m=>[...m,{role:'mira',text:output}]);}catch(err:any){toast.error(err.message||message(err));}finally{setBusy(false);}};
 if(!config?.settings?.features?.ai_customer)return null;
 // visibility scope: empty list = everywhere; otherwise only the chosen pages
 if((mc.pages||[]).length>0&&!mc.pages.includes(pageKey(loc.pathname)))return null;
 const MIcon=mc.icon==='bot'?Bot:mc.icon==='chat'?MessageCircle:Sparkles;
 const greeting=mc.greeting||`Hi${user?' '+user.name.split(' ')[0]:''}! I'm Mira.`;
 const prompts=(mc.quick_prompts||[]).filter(Boolean);
 return <div className={'mira-root'+(mc.position==='bottom_left'?' mira-left':'')} data-testid="mira-root">
  {open&&<div className="mira-panel" data-testid="mira-panel">
   <div className="mira-head"><span className="mira-avatar"><MIcon size={17}/></span><div><b>Mira</b><small>VOLTORA shopping assistant</small></div><button className="icon-btn" data-testid="mira-close" onClick={()=>setOpen(false)}><X size={17}/></button></div>
   <div className="mira-body" ref={boxRef}>
    {messages.length===0&&<div className="mira-welcome"><b>{greeting}</b>{!mc.greeting&&<p>Ask me to find products, compare options, or check your order — I'll point you right.</p>}{prompts.length>0&&<div className="mira-prompts">{prompts.map((p:string,i:number)=><button key={i} data-testid={`mira-prompt-${i}`} onClick={()=>send(null,p)}>{p}</button>)}</div>}</div>}
    {messages.map((m:any,i:number)=><div key={i} className={'chat-message '+(m.role==='user'?'customer':'ai')}><p>{m.text}</p></div>)}
    {busy&&<div className="chat-message ai"><p><Loader2 size={14} className="spin"/> thinking…</p></div>}
   </div>
   <form className="mira-input" onSubmit={send}><input data-testid="mira-input" placeholder="What are you looking for?" value={input} onChange={e=>setInput(e.target.value)}/><button data-testid="mira-send" type="submit" disabled={busy||!input.trim()} aria-label="Send to Mira"><Send size={17}/></button></form>
   <button className="mira-handoff" data-testid="mira-handoff" onClick={()=>navigate('/support')}><Headset size={13}/> Talk to a human instead</button>
  </div>}
  {shown&&<button className="mira-fab" data-testid="mira-fab" title="Ask Mira" onClick={()=>setOpen(!open)}><MIcon size={20}/></button>}
 </div>;
};
export default MiraChat;
