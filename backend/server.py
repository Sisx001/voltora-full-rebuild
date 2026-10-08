import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.cors import CORSMiddleware
from core import db, client, settings
from core import digest, now
from datetime import timedelta
from seed import seed
from auth import router as auth_router
from catalog import router as catalog_router
from commerce import router as commerce_router
from cms import router as cms_router
from admin import router as admin_router
from support import router as support_router
from media import router as media_router
from ai import router as ai_router
from roles import router as roles_router
from providers_admin import router as providers_router
from locations import router as locations_router, admin_router as locations_admin_router
from payments import router as payments_router, webhook_router as payment_webhook_router
from couriers import router as couriers_router, webhook_router as courier_webhook_router
from auth_ext import router as auth_ext_router, oauth_admin as oauth_admin_router
from accounts import router as accounts_router, admin_router as accounts_admin_router
from ai_tools import router as ai_tools_router, admin_router as ai_tools_admin_router
from ai_monitor import router as ai_monitor_router
from industry import router as industry_router
from offers import router as offers_router, admin_router as offers_admin_router
from affiliates import router as affiliates_router, public_router as affiliates_public_router
from alerts import router as alerts_router
from risk import router as risk_router
from diagnostics import router as diagnostics_router
from email_admin import router as email_admin_router, email_theme_router
from monitor import router as monitor_router
from brand import router as brand_router, admin_router as brand_admin_router
from captcha import captcha_public_config
from support_ext import router as support_ext_router, admin_router as support_ext_admin_router
from analytics_ext import router as analytics_ext_router
from notifications import start_queue_worker
import providers  # noqa: F401 - loads the provider adapter registry

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')

class AccessLogRedaction(logging.Filter):
    def filter(self,record):
        from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
        if isinstance(record.args,tuple) and len(record.args)>=3 and isinstance(record.args[2],str):
            args=list(record.args)
            parsed=urlsplit(args[2])
            args[2]=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode([(k,'REDACTED' if k.lower() in ['access','preview','token','auth'] else v) for k,v in parse_qsl(parsed.query)]),parsed.fragment))
            record.args=tuple(args)
        return True

logging.getLogger('uvicorn.access').addFilter(AccessLogRedaction())

@asynccontextmanager
async def lifespan(app):
    await seed()
    from release_engine import initialize_releases
    await initialize_releases()
    # External delivery is paused; scheduled publication uses the platform scheduler.
    yield
    client.close()

app=FastAPI(title='VOLTORA Commerce',version='1.0.0',lifespan=lifespan,docs_url='/api/docs',openapi_url='/api/openapi.json')
origin=os.environ['APP_ORIGIN'].rstrip('/')
trusted_origins=[origin]+[x.strip().rstrip('/') for x in os.environ.get('ADDITIONAL_TRUSTED_ORIGINS','').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=trusted_origins,allow_credentials=True,allow_methods=['GET','POST','PUT','PATCH','DELETE','OPTIONS'],allow_headers=['Content-Type','X-CSRF-Token','Idempotency-Key','X-Voltora-Preview'],expose_headers=['X-Correlation-ID'])

@app.middleware('http')
async def safeguards(request:Request,call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        supplied=request.headers.get('origin')
        if supplied and supplied.rstrip('/') not in trusted_origins:
            logging.getLogger('security').warning('origin_rejected supplied=%r expected=%r',supplied,origin)
            return JSONResponse({'detail':'Origin is not permitted'},status_code=403)
        size=request.headers.get('content-length')
        if size and (not size.isdigit() or int(size)>11*1024*1024):
            return JSONResponse({'detail':'Request too large'},status_code=413)
        if request.url.path.startswith(('/api/demo/start','/api/auth/login','/api/auth/register','/api/auth/setup','/api/auth/otp','/api/auth/password','/api/auth/oauth','/api/support/conversations','/api/newsletter','/api/events','/api/locations/resolve','/api/customer/privacy')):
            window=int(now().timestamp()//60)
            route=request.url.path.split('/')[2]
            key=digest((request.client.host if request.client else 'unknown')+route+str(window))
            from core import raw_db, PREFIX
            limit_collection=raw_db[PREFIX+'demo_rate_limits'] if request.url.path=='/api/demo/start' else db.rate_limits
            row=await limit_collection.find_one_and_update({'_id':key},{'$inc':{'count':1},'$setOnInsert':{'expires_at':now()+timedelta(minutes=2)}},upsert=True,return_document=True)
            if row['count']>(20 if request.url.path=='/api/demo/start' else 120):
                return JSONResponse({'detail':'Too many requests. Please wait a minute.'},status_code=429,headers={'Retry-After':'60'})
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['X-Frame-Options']='SAMEORIGIN'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith(('/api/auth','/api/admin','/api/orders','/api/customer','/api/support')):response.headers['Cache-Control']='no-store'
    return response

for router in [auth_ext_router,oauth_admin_router,auth_router,support_ext_router,support_ext_admin_router,support_router,monitor_router,analytics_ext_router,catalog_router,commerce_router,cms_router,admin_router,media_router,ai_router,roles_router,providers_router,locations_router,locations_admin_router,payments_router,payment_webhook_router,couriers_router,courier_webhook_router,accounts_router,accounts_admin_router,ai_tools_router,ai_tools_admin_router,ai_monitor_router,industry_router,offers_router,offers_admin_router,affiliates_router,affiliates_public_router,alerts_router,risk_router,diagnostics_router,email_admin_router,email_theme_router,brand_router,brand_admin_router]:app.include_router(router)

# Scope every collection access and enforce read-only contexts before domain routes.
from isolation import router as isolation_router, isolation_guard
app.include_router(isolation_router)
app.middleware('http')(isolation_guard)
from mailbox import router as mailbox_router
app.include_router(mailbox_router)
from market import router as market_router
app.include_router(market_router)
from publishing_jobs import router as publishing_router
app.include_router(publishing_router)
from release_engine import router as release_router
app.include_router(release_router)
from mira_workspace import router as mira_workspace_router
app.include_router(mira_workspace_router)

@app.middleware('http')
async def correlated_errors(request:Request,call_next):
    from core import uid
    from pymongo.errors import PyMongoError
    correlation=uid()
    request.state.correlation_id=correlation
    try:
        response=await call_next(request)
    except PyMongoError:
        logging.getLogger('voltora').error('Database request failed correlation=%s path=%s',correlation,request.url.path)
        response=JSONResponse({'detail':'The database is temporarily unavailable. Your saved draft and bag have not been discarded.','correlation_id':correlation},status_code=503)
    except Exception:
        logging.getLogger('voltora').exception('Request failed correlation=%s path=%s',correlation,request.url.path)
        response=JSONResponse({'detail':'This request could not be completed. Retry with the reference shown.','correlation_id':correlation},status_code=500)
    response.headers['X-Correlation-ID']=correlation
    return response





@app.get('/api/captcha/config')
async def captcha_config_public():
    return await captcha_public_config()

@app.get('/api/health')
async def health():
    start=time.monotonic()
    await db.command('ping')
    return {'status':'ok','database':'connected','latency_ms':round((time.monotonic()-start)*1000,2)}

@app.get('/api/sitemap.xml')
async def sitemap():
    from xml.sax.saxutils import escape
    pages=await db.documents.find({'kind':'page','published':{'$ne':None}},{'_id':0,'published':1}).to_list(1000)
    products=await db.products.find({'published':True},{'_id':0,'slug':1}).to_list(10000)
    paths=['/','/shop']+['/product/'+p['slug'] for p in products]+['/pages/'+p['published']['slug'] for p in pages if p['published']['slug']!='home' and p['published'].get('indexable',True)]
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+''.join('<url><loc>'+escape(origin+p)+'</loc></url>' for p in paths)+'</urlset>',media_type='application/xml')

@app.get('/api/robots.txt')
async def robots():
    return Response('User-agent: *\nDisallow: /admin\nDisallow: /account\nDisallow: /order/\nDisallow: /checkout\nDisallow: /*?preview=\nSitemap: '+origin+'/api/sitemap.xml',media_type='text/plain')