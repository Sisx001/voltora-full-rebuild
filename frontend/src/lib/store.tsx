import React,{createContext,useContext,useState,useEffect,useCallback,useRef} from 'react';
import {isStoreConfiguration,storeFailure,StoreFailure} from './apiConfig';
import {readPreference,usePersistentState} from './persistentState';
import {get,post,api,setCsrf} from './api';
import {Product,CartItem,User} from './types';
import {toast} from 'sonner';
import {track} from './analytics';
const Context=createContext<any>(null);
const params=new URLSearchParams(window.location.search);
export const inPreview=!!(params.get('preview')||params.get('theme_preview')||params.get('builder_preview')||window.name==='voltora-preview');
// Preview storage is memory-only: it cannot alter the customer's saved cart or preferences.
function saved(key:string,def:any){if(inPreview)return def;try{const value=JSON.parse(localStorage.getItem(key)||'null')??def;return Array.isArray(def)&&!Array.isArray(value)?def:value;}catch{return def;}}
export const StoreProvider=({children}:{children:React.ReactNode})=>{
const [config,setConfig]=useState<any>(null),[error,setError]=useState<StoreFailure|null>(null),[configLoading,setConfigLoading]=useState(false),[user,setUser]=useState<User|null>(null),[authReady,setAuthReady]=useState(false);
const configRequest=useRef<Promise<void>|null>(null);
const [cart,setCart]=usePersistentState<CartItem[]>('voltora-cart',()=>saved('voltora-cart',[]),inPreview),[wishlist,setWishlist]=usePersistentState<string[]>('voltora-wishlist',()=>saved('voltora-wishlist',[]),inPreview),[wishlistReady,setWishlistReady]=useState(''),[compare,setCompare]=usePersistentState<string[]>('voltora-compare',()=>saved('voltora-compare',[]),inPreview);
const [language,setLanguage]=usePersistentState('voltora-language',()=>inPreview?'en':readPreference('voltora-language','en'),inPreview,false),[currency,setCurrency]=usePersistentState('voltora-currency',()=>inPreview?'BDT':readPreference('voltora-currency','BDT'),inPreview,false),[mode,setMode]=usePersistentState('voltora-mode',()=>params.get('appearance')||(inPreview?'light':readPreference('voltora-mode','light')),inPreview,false);
const refreshConfig=useCallback(()=>{
 if(configRequest.current)return configRequest.current;
 setConfigLoading(true);
 const pending=(async()=>{try{
  const q=new URLSearchParams(window.location.search),preview=q.get('preview'),preset=q.get('theme_preview');
  const response=await api.get('/store'+(preview?'?preview='+encodeURIComponent(preview):preset?'?theme_preview='+encodeURIComponent(preset):''),{timeout:12000});
  if(!isStoreConfiguration(response.data))throw Object.assign(new Error('Incomplete store response'),{code:'ERR_STORE_RESPONSE',response});
  setConfig(response.data);setError(null);
 }catch(e){setError(storeFailure(e,navigator.onLine));}finally{setConfigLoading(false);}})();
 configRequest.current=pending;
 void pending.finally(()=>{if(configRequest.current===pending)configRequest.current=null;});
 return pending;
},[]);
useEffect(()=>{const onMsg=(e:MessageEvent)=>{if(!inPreview||e.origin!==window.location.origin||e.source!==window.parent)return;const d=e.data||{};if(d.type==='voltora-theme-preview'&&d.theme)setConfig((c:any)=>c?{...c,theme:d.theme,site:c.site?{...c.site,header:{...c.site.header,layout:d.theme.header_style},footer:{...c.site.footer,style:d.theme.footer_style}}:c.site}:c);if(d.type==='voltora-site-preview'&&d.site)setConfig((c:any)=>c?{...c,site:d.site}:c);if(d.type==='voltora-page-preview'&&d.page)setConfig((c:any)=>c?{...c,...(d.page.slug==='home'?{home:d.page}:{livePage:d.page})}:c);if(d.type==='voltora-site-preview-end')refreshConfig();};window.addEventListener('message',onMsg);return()=>window.removeEventListener('message',onMsg);},[refreshConfig]);
const refreshUser=useCallback(async()=>{if(inPreview){setAuthReady(true);return;}try{const data=await get('/auth/session');setUser(data.user);setCsrf(data.csrf);}catch{setUser(null);setCsrf('');}finally{setAuthReady(true);}},[]);
useEffect(()=>{refreshConfig();refreshUser();},[refreshConfig,refreshUser]);
useEffect(()=>{if(!inPreview)return;const receive=(e:MessageEvent)=>{if(e.origin!==window.location.origin||e.source!==window.parent)return;if(e.data?.type==='voltora-release-preview'){const b=e.data.bundle;setConfig((c:any)=>c?{...c,theme:b.theme,site:b.site,home:b.pages.home,livePage:b.pages[window.location.pathname.replace('/pages/','')],customerPreviewState:e.data.customerState}:c);requestAnimationFrame(()=>requestAnimationFrame(()=>{document.querySelectorAll('.builder-highlight').forEach(n=>n.classList.remove('builder-highlight'));const target=e.data.selection==='footer'?document.querySelector('footer.store-footer'):e.data.selection==='header'?document.querySelector('header.store-header'):null;if(target){target.classList.add('builder-highlight');target.scrollIntoView({block:'start'});}else if(e.data.resetScroll)window.scrollTo(0,0);}));}};window.addEventListener('message',receive);return()=>window.removeEventListener('message',receive);},[]);
useEffect(()=>{const onStorage=(e:StorageEvent)=>{if(e.key==='voltora-theme-version'&&!inPreview)refreshConfig();};window.addEventListener('storage',onStorage);return()=>window.removeEventListener('storage',onStorage);},[refreshConfig]);
useEffect(()=>{if(inPreview)return;if(user&&user.role!=='investor'&&wishlistReady===user.id)api.put('/customer/wishlist',{product_ids:wishlist}).catch(()=>{});},[wishlist,user,wishlistReady]);
useEffect(()=>{setWishlistReady('');if(user&&!inPreview)get('/customer/wishlist').then((r:any)=>{setWishlist(v=>Array.from(new Set([...v,...r.product_ids])));setWishlistReady(user.id);}).catch(()=>{});},[user?.id]);
useEffect(()=>{document.documentElement.lang=language;},[language]);
const t=(key:string)=>config?.settings.translations?.[config?.settings.features.multilingual?language:'en']?.[key]||config?.settings.translations?.en?.[key]||key;
const money=(amount:number,forceBase=false)=>{const base=config?.settings.base_currency||'BDT';const currencies=config?.settings.currencies||[];const selected=(!forceBase&&config?.settings.features.multicurrency?currencies.find((c:any)=>c.code===currency&&c.enabled):null)||currencies.find((c:any)=>c.code===base)||{code:base,symbol:base==='BDT'?'৳':base+' ',rate:1,decimals:2};return selected.symbol+new Intl.NumberFormat(language==='bn'?'bn-BD':'en-BD',{minimumFractionDigits:selected.decimals,maximumFractionDigits:selected.decimals}).format(amount/100*(forceBase?1:selected.rate));};
const add=(product:Product,variant=product.variants[0],quantity=1)=>{if(!variant||variant.stock===0){toast.error('This option is out of stock');return;}setCart(old=>{const item=old.find(x=>x.variant_id===variant.id);return item?old.map(x=>x.variant_id===variant.id?{...x,quantity:Math.min(x.quantity+quantity,variant.stock??99)}:x):[...old,{product_id:product.id,variant_id:variant.id,quantity,expected_price:variant.price,name:product.name,slug:product.slug,image:product.images[0],options:variant.options}];});toast.success(inPreview?'Added to preview bag — not saved to your account':'Added to your bag',{description:product.name});if(!inPreview)track('add_to_cart',config?.settings.features.analytics);};
const toggleWishlist=(id:string)=>setWishlist(v=>v.includes(id)?v.filter(x=>x!==id):[...v,id]);
const toggleCompare=(id:string)=>setCompare(v=>{if(v.includes(id))return v.filter(x=>x!==id);if(v.length>=4){toast.error('Compare up to four products at a time');return v;}toast.success('Added to comparison');return [...v,id];});
const login=(data:any)=>{setUser(data.user);setCsrf(data.csrf);};
const logout=async()=>{await post('/auth/logout');setUser(null);setCsrf('');setWishlist([]);};
return <Context.Provider value={{config,error,configLoading,refreshConfig,user,authReady,refreshUser,login,logout,cart,setCart,add,wishlist,toggleWishlist,compare,toggleCompare,language,setLanguage,currency,setCurrency,mode,setMode,t,money,inPreview}}>{children}</Context.Provider>;
};
export const useStore=()=>useContext(Context);
