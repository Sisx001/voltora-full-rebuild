import React,{useEffect} from 'react';
import {BrowserRouter,Routes,Route,Outlet,Link,useLocation,Navigate} from 'react-router-dom';
import {Headset,Scale,RefreshCw,Sparkles} from 'lucide-react';
import {Mailbox} from './pages/admin/Mailbox';
import {ThemeGallery} from './pages/admin/ThemeGallery';
import {MarketSettings} from './pages/admin/MarketSettings';
import {Toaster} from './components/ui/sonner';
import {StoreProvider,useStore} from './lib/store';
import {track} from './lib/analytics';
import {ThemeShell,themeStyle} from './components/store/ThemeShell';
import {Header} from './components/store/Header';
import {Footer,Consent} from './components/store/Footer';
import {Loading,Empty,Btn} from './components/shared';
import Home,{Shop,ProductDetail,SavedProducts,ContentPage} from './pages/StorePages';
import {Cart,Checkout,Order} from './pages/Checkout';
import {Account} from './pages/Account';
import {Support} from './pages/Support';
import {Assistant} from './pages/Assistant';
import {AdminShell} from './components/admin/AdminShell';
import Overview from './pages/admin/Overview';
import {AdminProducts,Taxonomies} from './pages/admin/Catalog';
import {Inventory,AdminOrders,Coupons,Customers,Reviews} from './pages/admin/Operations';
import {AdminLocations} from './pages/admin/Locations';
import {AdminOffers} from './pages/admin/Offers';
import Connections from './pages/admin/Connections';
import {Diagnostics,ApiSurface,EmailTemplates} from './pages/admin/Ops';
import {AdminAffiliates} from './pages/admin/Affiliates';
import {OfferPage} from './pages/OfferPage';
import MiraChat from './components/store/MiraChat';
import {ADMIN_PATH} from './lib/adminPath';
import {AdminCouriers} from './pages/admin/Couriers';
import OAuthProviders from './pages/admin/OAuth';
import Analytics from './pages/admin/Analytics';
import StoreMonitor from './pages/admin/Monitor';
import {ThemeStudio,PageBuilder} from './pages/admin/DesignStudio';
import {WebsiteBuilder} from './pages/admin/WebsiteBuilder';
import VisualBuilder from './pages/admin/builder/VisualBuilder';
import ReleaseHistory from './pages/admin/builder/ReleaseHistory';
import MiraWorkspace from './pages/admin/MiraWorkspace';
import {CustomerAuth} from './pages/CustomerAuth';
import StoreSettings from './pages/admin/Settings';
import {MediaLibrary,SupportInbox,Team,RoleBuilder,Audit,Security,AIStudio} from './pages/admin/Workspace';
import './App.css';
import './admin.css';
import './rebuild.css';
import './theme-gallery.css';
import './structural-themes.css';

const storeRoutes=[['/',<Home/>],['/shop',<Shop/>],['/product/:slug',<ProductDetail/>],['/wishlist',<SavedProducts/>],['/compare',<SavedProducts comparison/>],['/cart',<Cart/>],['/checkout',<Checkout/>],['/order/:id',<Order/>],['/account',<Account/>],['/support',<Support/>],['/assistant',<Assistant/>],['/pages/:slug',<ContentPage/>]] as const;
const adminRoutes=[['mail',<Mailbox/>],['products',<AdminProducts/>],['categories',<Taxonomies kind="categories"/>],['brands',<Taxonomies kind="brands"/>],['collections',<Taxonomies kind="collections"/>],['inventory',<Inventory/>],['locations',<AdminLocations/>],['reviews',<Reviews/>],['orders',<AdminOrders/>],['customers',<Customers/>],['coupons',<Coupons/>],['offers',<AdminOffers/>],['affiliates',<AdminAffiliates/>],['email-templates',<EmailTemplates/>],['connections',<Connections/>],['diagnostics',<Diagnostics/>],['api',<ApiSurface/>],['payments',<StoreSettings section="payments"/>],['shipping',<StoreSettings section="shipping"/>],['themes',<ThemeStudio/>],['pages',<PageBuilder/>],['website',<WebsiteBuilder/>],['media',<MediaLibrary/>],['navigation',<StoreSettings section="navigation"/>],['layout',<StoreSettings section="layout"/>],['localization',<StoreSettings section="localization"/>],['couriers',<AdminCouriers/>],['oauth',<OAuthProviders/>],['analytics',<Analytics/>],['monitor',<StoreMonitor/>],['support',<SupportInbox/>],['ai',<AIStudio/>],['settings',<StoreSettings/>],['features',<StoreSettings section="features"/>],['team',<Team/>],['roles',<RoleBuilder/>],['audit',<Audit/>],['security',<Security/>]] as const;

const StoreLayout=()=>{
 const {config,compare,inPreview}=useStore();const loc=useLocation();const preview=new URLSearchParams(loc.search).get('preview')||inPreview;
 useEffect(()=>{if(config&&inPreview)window.parent.postMessage({type:'voltora-preview-ready'},window.location.origin);},[config?.theme?.id,inPreview]);
 useEffect(()=>{if(!preview&&config)track(loc.pathname.startsWith('/product/')?'product_view':loc.pathname==='/checkout'?'begin_checkout':'page_view',config.settings.features.analytics);},[loc.pathname,config?.settings.features.analytics]);
 useEffect(()=>{
  if(!config)return;
  document.title=config.settings.seo_title;
  let description=document.querySelector('meta[name="description"]');
  if(!description){description=document.createElement('meta');description.setAttribute('name','description');document.head.appendChild(description);}
  description.setAttribute('content',config.settings.seo_description||config.settings.tagline);
  let canonical=document.querySelector('link[rel="canonical"]');
  if(!canonical){canonical=document.createElement('link');canonical.setAttribute('rel','canonical');document.head.appendChild(canonical);}
  canonical.setAttribute('href',window.location.origin+loc.pathname);
  let robots=document.querySelector('meta[name="robots"]');
  if(!robots){robots=document.createElement('meta');robots.setAttribute('name','robots');document.head.appendChild(robots);}
  robots.setAttribute('content',preview||/^\/(account|order|checkout|cart|support|assistant)/.test(loc.pathname)?'noindex,nofollow':'index,follow');
 },[config,loc.pathname,preview]);
 if(!config)return <Loading/>;
 return <ThemeShell><div className={preview?'store-preview-mode':''}>
  {preview&&<div className="preview-banner" data-testid="preview-banner">Private draft preview · Expires in 30 minutes<Link data-testid="exit-preview" to="/" onClick={()=>window.location.assign('/')}>Exit preview</Link></div>}
  <Header/>
  <main>{config.settings.mode==='live'&&!new URLSearchParams(loc.search).get('maintenance_preview')||preview&&!new URLSearchParams(loc.search).get('maintenance_preview')?<Outlet/>:<div className="container"><Empty title={config.settings.mode==='coming_soon'?'Something good is on its way.':'A little pause. A better experience.'} description={config.settings.maintenance_message}/></div>}</main>
  <Footer/>
  {!preview&&<><Consent/>
   {config.settings.features.support&&<Link data-testid="floating-support" className="floating-support" to="/support" title="Talk to our team"><Headset size={22}/></Link>}
   {config.settings.features.ai_chat&&<Link data-testid="floating-ai-assistant" className="floating-ai-assistant" to="/assistant" title="AI shopping assistant"><Sparkles size={19}/></Link>}
   {config.settings.features.compare&&compare.length>0&&<Link data-testid="floating-compare" className="floating-compare" title="Compare products" to="/compare"><Scale size={20}/><span>{compare.length}</span></Link>}
   <MiraChat/>
  </>}
 </div></ThemeShell>;
};

let lastTheme:any=null;
const Splash=()=>{
 const style=lastTheme?.loading_style||'branded';
 if(style==='none')return <Loading text="Getting the good things ready..."/>;
 return <div className={'splash splash-'+style} style={lastTheme?themeStyle(lastTheme):undefined} data-testid="boot-splash">
    <div className="loader-logo"><span className="logo-mark" aria-hidden="true"><i/><i/><i/></span><b>VOLTORA</b></div>
 </div>;
};

const AppRoutes=()=>{
 const {config,error,refreshConfig}=useStore();const loc=useLocation();
 useEffect(()=>{window.scrollTo({top:0,behavior:'instant' as ScrollBehavior});},[loc.pathname]);
 if(config)lastTheme=config.theme;
 if(!loc.pathname.startsWith(ADMIN_PATH)&&error)return <div className="mfa-page"><RefreshCw size={35}/><h1>Let’s try that again.</h1><p>We couldn’t reach the store. Your saved bag is still here.</p><Btn id="retry-store" onClick={refreshConfig}>Reconnect</Btn><Link data-testid="store-recovery-admin" to="/admin">Open owner workspace</Link></div>;
 if(!loc.pathname.startsWith(ADMIN_PATH)&&!config)return <Splash/>;
 return <Routes>
  <Route element={<StoreLayout/>}>
   <Route path="/login" element={<CustomerAuth/>}/><Route path="/signup" element={<CustomerAuth initial="signup"/>}/><Route path="/forgot-password" element={<CustomerAuth initial="forgot"/>}/>
   {storeRoutes.map(([path,element])=><Route path={path} element={element} key={path}/>)}
   <Route path="*" element={<Empty title={config?.settings?.not_found_message||"A little off the beaten path."} description="We couldn’t find that page." link="/" label="Back to the good things"/>}/>
  </Route>
  <Route path="/offer/:code" element={<OfferPage/>}/>
 <Route path={ADMIN_PATH} element={<AdminShell/>}>
   <Route index element={<WorkspaceStoreBoundary><Overview/></WorkspaceStoreBoundary>}/>
<Route path="themes" element={<WorkspaceStoreBoundary><ThemeGallery/></WorkspaceStoreBoundary>}/><Route path="localization" element={<WorkspaceStoreBoundary><MarketSettings/></WorkspaceStoreBoundary>}/>
   <Route path="website" element={<VisualBuilder/>}/>
   <Route path="releases" element={<ReleaseHistory/>}/>
   <Route path="ai" element={<MiraWorkspace/>}/>
   <Route path="pages" element={<Navigate to="/admin/website?select=page:home" replace/>}/>
   <Route path="navigation" element={<Navigate to="/admin/website?select=header" replace/>}/>
   <Route path="layout" element={<Navigate to="/admin/website?select=footer" replace/>}/>
   {adminRoutes.filter(([path])=>!['themes','localization','website','ai','pages','navigation','layout'].includes(path)).map(([path,element])=><Route path={path} element={<WorkspaceStoreBoundary>{element}</WorkspaceStoreBoundary>} key={path}/>)}
  </Route>
 </Routes>;
};
const WorkspaceStoreBoundary=({children}:{children:React.ReactNode})=>{const {config,error,refreshConfig}=useStore();if(error)return <div className="mfa-page"><h1>Store configuration is unavailable.</h1><p data-testid="admin-store-config-error">Your owner session and saved drafts are intact.</p><Btn id="retry-admin-store-config" onClick={refreshConfig}>Retry store connection</Btn><Link data-testid="open-independent-editor" to="/admin/website">Open website builder</Link></div>;return config?<>{children}</>:<Loading/>;};
export default function App(){return <BrowserRouter><StoreProvider><AppRoutes/><Toaster position="top-right" richColors closeButton/></StoreProvider></BrowserRouter>;}