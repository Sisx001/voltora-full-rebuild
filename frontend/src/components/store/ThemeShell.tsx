import React,{useEffect,useState,useRef} from 'react';
import {useStore} from '../../lib/store';
import {Theme} from '../../lib/types';
const ICON_WEIGHT:any={thin:1.2,regular:1.7,bold:2.4};
export const themeStyle=(theme:any,dark=false):React.CSSProperties=>({
 '--motion-duration':`${theme.motion===false||theme.animation_level==='none'?0:theme.motion_duration??180}ms`,'--motion-ease':theme.motion_easing||'ease-out',
 '--v-primary':theme.primary,'--v-bg':dark?theme.dark_background:theme.background,'--v-surface':dark?theme.dark_surface:theme.surface,'--v-text':dark?theme.dark_text:theme.text,'--v-muted':dark?'#a5afa7':theme.muted,'--v-border':dark?'#3b443d':theme.border,
 '--v-heading':`'${theme.heading_font}', 'Noto Sans Bengali', sans-serif`,'--v-body':`'${theme.body_font}', 'Noto Sans Bengali', sans-serif`,'--v-radius':theme.radius+'px','--v-space':theme.spacing+'px','--v-gap':theme.gap+'px','--v-width':theme.width+'px','--v-cols':theme.columns,
 '--v-heading-scale':(theme.heading_scale??1)+'','--v-body-size':(theme.body_font_size??16)+'px','--v-heading-weight':(theme.heading_weight??800)+'','--v-body-weight':(theme.body_weight??400)+'','--v-letter-spacing':(theme.letter_spacing??0)+'px','--v-line-height':((theme.line_height??155)/100)+'',
 '--v-secondary':theme.secondary||'#5b8f5b','--v-accent':theme.accent||'#f0b429','--v-success':theme.success||'#3f9d63','--v-card':dark?(theme.dark_surface||theme.card_background||'#232a25'):(theme.card_background||'#ffffff'),'--v-icon-weight':ICON_WEIGHT[theme.icon_style||'regular']+''
} as React.CSSProperties);
export const ThemeShell=({children,theme:override}:any)=>{
 const {config,mode,refreshConfig}=useStore();const [systemDark,setSystemDark]=useState(window.matchMedia('(prefers-color-scheme: dark)').matches);
 const [liveTheme,setLiveTheme]=useState<any>(null);
 const lastPing=useRef<number>(0);const hadPreview=useRef<boolean>(false);
 useEffect(()=>{const m=window.matchMedia('(prefers-color-scheme: dark)');const fn=(e:any)=>setSystemDark(e.matches);m.addEventListener('change',fn);return()=>m.removeEventListener('change',fn);},[]);
 useEffect(()=>{
  const apply=(t:any)=>{setLiveTheme(t);};
  const clear=()=>{setLiveTheme(null);try{sessionStorage.removeItem('voltora-live-theme');}catch{}refreshConfig();};
  const onMessage=(e:MessageEvent)=>{
   if(e.origin!==window.location.origin||e.source!==window.parent||window.name!=='voltora-preview'||!e.data)return;
   if(e.data.type==='voltora-theme-preview'&&e.data.theme){lastPing.current=Date.now();hadPreview.current=true;apply(e.data.theme);}
   if(e.data.type==='voltora-theme-preview-end'){clear();}
  };
  window.addEventListener('message',onMessage);
  // Watchdog: if the studio stops heartbeating (closed, navigated away, refreshed),
  // drop the live draft so the preview tab returns to the published theme.
  const watchdog=setInterval(()=>{if(hadPreview.current&&lastPing.current&&Date.now()-lastPing.current>6000){hadPreview.current=false;lastPing.current=0;clear();}},2000);
  return()=>{window.removeEventListener('message',onMessage);clearInterval(watchdog);};
 },[]);
 const theme=override||liveTheme||config?.theme;if(!theme)return children;
 const dark=config?.settings.features.dark_mode&&(mode==='dark'||(mode==='system'&&systemDark));
 return <div className={`store-theme card-${theme.card_style} header-${theme.header_style} hero-${theme.hero_style} footer-${theme.footer_style} button-${theme.button_style} image-${theme.image_ratio} shadow-${theme.shadow_style||'soft'} input-${theme.input_style||'rounded'} badge-${theme.product_badge_style||'solid'} cat-${theme.category_style||'grid'} layout-${theme.product_layout||'classic'} anim-${theme.animation_level||'subtle'} ${!theme.motion?'reduce-motion':''} ${theme.micro_interactions===false?'no-micro':''}`} style={themeStyle(theme,dark)} data-industry={theme.industry||'electronics'}>{children}</div>;
};
