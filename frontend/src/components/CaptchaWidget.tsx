import React,{useEffect,useRef} from 'react';

declare global{interface Window{[k:string]:any}}

/** Provider-agnostic CAPTCHA widget. Renders only when the store has an
 *  enabled CAPTCHA provider; exposes the token via onToken. */
export const CaptchaWidget=({config,onToken}:{config:{provider:string;site_key:string;script_url:string};onToken:(t:string)=>void})=>{
 const el=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(!config?.provider||!el.current)return;
  const render=()=>{
   try{
    if(config.provider==='turnstile'&&window.turnstile){window.turnstile.render(el.current,{sitekey:config.site_key,callback:onToken});return true;}
    if(config.provider==='recaptcha'&&window.grecaptcha){window.grecaptcha.render(el.current,{sitekey:config.site_key,callback:onToken});return true;}
    if(config.provider==='hcaptcha'&&window.hcaptcha){window.hcaptcha.render(el.current,{sitekey:config.site_key,callback:onToken});return true;}
   }catch{}
   return false;
  };
  if(render())return;
  const existing=document.querySelector(`script[data-captcha="${config.provider}"]`);
  const done=()=>{setTimeout(()=>{if(!render())onToken('__unavailable__');},600);};
  if(existing){existing.addEventListener('load',done);}
  else{const s=document.createElement('script');s.src=config.script_url;s.async=true;s.defer=true;s.dataset.captcha=config.provider;s.onload=done;s.onerror=()=>onToken('__unavailable__');document.head.appendChild(s);}
 },[config?.provider]);
 return <div className="captcha-widget" data-testid="captcha-widget"><div ref={el}/></div>;
};
export default CaptchaWidget;
