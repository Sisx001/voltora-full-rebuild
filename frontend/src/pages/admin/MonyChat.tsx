import React,{useState,useEffect,useRef} from 'react';
import {Sparkles,X,Send,Loader2,ShieldCheck,Brain,Plus,Trash2} from 'lucide-react';
import {get,post,api,API_ROOT,message} from '../../lib/api';
import {useStore} from '../../lib/store';
import {toast} from 'sonner';
import {Modal,Field,Btn,Loading,Empty,Status} from '../../components/shared';

/** Mony — the VOLTORA admin operations assistant. Floating widget on every admin page. */
export const MonyChat=()=>{
 const {user}=useStore();
 const [open,setOpen]=useState(false),[messages,setMessages]=useState<any[]>([]),[input,setInput]=useState(''),[busy,setBusy]=useState(false);
 const [memoryOpen,setMemoryOpen]=useState(false),[memories,setMemories]=useState<any[]|null>(null),[newMemory,setNewMemory]=useState('');
 const boxRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{const el=boxRef.current;if(el&&open)el.scrollTop=el.scrollHeight;},[messages,busy,open]);
 const send=async(e:any)=>{e.preventDefault();const text=input.trim();if(!text||busy)return;setInput('');setMessages(m=>[...m,{role:'user',text}]);setBusy(true);
  try{const me=await get('/auth/me');const response=await fetch(API_ROOT+'/admin/ai/assistant',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':me.csrf},body:JSON.stringify({message:text})});
   if(!response.ok){const r=await response.json();throw new Error(r.detail);}
   const reader=response.body!.getReader();const decoder=new TextDecoder();let buffer='';let output='';let tools:any[]=[];
   while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});const chunks=buffer.split('\n\n');buffer=chunks.pop()||'';
    for(const chunk of chunks){if(!chunk.startsWith('data:'))continue;const ev=JSON.parse(chunk.slice(5));if(ev.tools)tools=ev.tools;if(ev.text)output=ev.text;if(ev.error)toast.error(ev.error);}}
   setMessages(m=>[...m,{role:'mony',text:output,tools}]);}catch(err:any){toast.error(err.message||message(err));}finally{setBusy(false);}};
 if(!user?.permissions?.includes('ai.update'))return null;
 const loadMemory=()=>get('/admin/ai/memory').then(setMemories).catch(e=>toast.error(message(e)));
 return <div className="mony-root" data-testid="mony-root">
  {open&&<div className="mony-panel" data-testid="mony-panel">
   <div className="mira-head mony-head"><span className="mira-avatar mony-avatar"><Sparkles size={17}/></span><div><b>Mony</b><small>Admin operations assistant</small></div><button className="icon-btn" title="AI memory" data-testid="mony-memory" onClick={()=>{setMemoryOpen(true);loadMemory();}}><Brain size={16}/></button><button className="icon-btn" data-testid="mony-close" onClick={()=>setOpen(false)}><X size={17}/></button></div>
   <div className="mira-body" ref={boxRef}>
    {messages.length===0&&<div className="mira-welcome"><b>I'm Mony.</b><p>Ask me to analyze sales, find low stock, check payment failures, review security signals, draft products — or propose a theme switch for your approval.</p></div>}
    {messages.map((m:any,i:number)=><div key={i} className={'chat-message '+(m.role==='user'?'customer':'ai')}><p>{m.text}</p>{m.tools?.length>0&&<small className="mono" style={{fontSize:10,opacity:.7}}>{m.tools.map((t:any)=>'· '+t.tool).join(' ')}</small>}</div>)}
    {busy&&<div className="chat-message ai"><p><Loader2 size={14} className="spin"/> working…</p></div>}
   </div>
   <form className="mira-input" onSubmit={send}><input data-testid="mony-input" placeholder="Ask Mony anything about the store…" value={input} onChange={e=>setInput(e.target.value)}/><button data-testid="mony-send" type="submit" disabled={busy||!input.trim()} aria-label="Send to Mony"><Send size={17}/></button></form>
  </div>}
  <button className="mony-fab" data-testid="mony-fab" title="Ask Mony" onClick={()=>setOpen(!open)}><Sparkles size={20}/></button>
  <Modal open={memoryOpen} onClose={()=>setMemoryOpen(false)} title="Mony's memory" description="Business context you explicitly save. Injected into every conversation; never a source for transactional facts.">
   <form onSubmit={async e=>{e.preventDefault();try{await post('/admin/ai/memory',{content:newMemory});setNewMemory('');loadMemory();toast.success('Saved to memory');}catch(e){toast.error(message(e));}}} className="reply-form" data-testid="memory-form">
    <input data-testid="memory-input" placeholder="e.g. We never discount below 10% margin…" value={newMemory} onChange={e=>setNewMemory(e.target.value)}/>
    <button type="submit" aria-label="Save memory" disabled={newMemory.trim().length<3}><Plus size={17}/></button></form>
   {!memories?<Loading/>:memories.length?memories.map((m:any)=><div className="health-service" key={m.id}><span>{m.content}</span><button className="icon-btn" title="Forget" onClick={async()=>{try{await api.delete('/admin/ai/memory/'+m.id);loadMemory();toast.success('Forgotten');}catch(e){toast.error(message(e));}}}><Trash2 size={14}/></button></div>):<Empty title="Nothing saved yet." description="Save standing instructions and business context for Mony to respect."/>}
  </Modal>
 </div>;
};
export default MonyChat;
