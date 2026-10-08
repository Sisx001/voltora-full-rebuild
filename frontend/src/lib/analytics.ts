import {post} from './api';

const captureUtm=():Record<string,string>|null=>{
 try{if(!localStorage.getItem('voltora-utm')){const params=new URLSearchParams(window.location.search);const utm:Record<string,string>={};
  ['utm_source','utm_medium','utm_campaign','utm_term','utm_content'].forEach(k=>{const v=params.get(k);if(v)utm[k]=v.slice(0,120);});
  if(Object.keys(utm).length)localStorage.setItem('voltora-utm',JSON.stringify(utm));}
  const stored=localStorage.getItem('voltora-utm');return stored?JSON.parse(stored):null;}catch{return null;}
};
captureUtm();

export const track=(event:string,enabled:boolean,path=window.location.pathname,term='')=>{
 if(!enabled)return;
 try{const consent=JSON.parse(localStorage.getItem('voltora-consent')||'{}');if(!consent.analytics)return;
  let visitor=localStorage.getItem('voltora-visitor');if(!visitor){visitor=crypto.randomUUID();localStorage.setItem('voltora-visitor',visitor);}
  post('/events',{event,visitor_id:visitor,path:path.split('?')[0],consent:true,term:term.slice(0,100),referrer:document.referrer.slice(0,300),utm:captureUtm()||{}}).catch(()=>{});}catch{}
};
