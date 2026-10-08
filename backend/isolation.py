"""Demo namespaces, read-only investor enforcement and preview mutation boundaries."""
import os, re, secrets
from urllib.parse import urlparse, parse_qs
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import Field
from starlette.responses import JSONResponse
from core import db, raw_db, workspace, RUNTIME_MODE, PREFIX, Input, stamp, uid, EXTERNAL_ACTIONS
from auth import optional_user, create_session, hasher
from typing import Literal
router = APIRouter(prefix='/api', tags=['Environment isolation'])

async def isolation_guard(request, call_next):
    ns = request.cookies.get('voltora_workspace', '')
    if ns:
        response = JSONResponse({'detail':'Legacy demo sessions are disabled. Sign in to the private workspace.'}, status_code=401)
        response.delete_cookie('voltora_workspace', path='/')
        response.delete_cookie('voltora_session', path='/')
        return response
    # A signed guest capability carries its demo namespace; never scan other workspaces.
    access=request.query_params.get('access','')
    if request.method=='GET' and request.url.path.startswith('/api/orders/') and re.fullmatch(r'd[0-9a-f]{24}\.[0-9a-f]{64}', access):
        ns=access.split('.')[0]
    if ns and not re.fullmatch(r'd[0-9a-f]{24}', ns):
        return JSONResponse({'detail':'Invalid workspace'}, status_code=400)
    if ns and not await raw_db[PREFIX+'workspace_registry'].find_one({'id':ns}):
        response=JSONResponse({'detail':'Demo workspace expired; start a new demonstration'},status_code=401)
        response.delete_cookie('voltora_workspace',path='/');response.delete_cookie('voltora_session',path='/')
        return response
    token = workspace.set(ns)
    try:
        unsafe=request.method not in ('GET','HEAD','OPTIONS')
        ref_query=parse_qs(urlparse(request.headers.get('referer','')).query)
        ref_preview=ref_query.get('preview') or ref_query.get('theme_preview')
        preview=request.query_params.get('preview') or request.query_params.get('theme_preview') or request.query_params.get('builder_preview') or request.headers.get('x-voltora-preview') or ref_preview
        if unsafe and preview and request.url.path not in ['/api/cart/quote']:
            return JSONResponse({'detail':'Preview is isolated and read-only. Exit preview to make changes.'},status_code=403)
        user=await optional_user(request)
        if user and user.get('role')=='investor' and unsafe and request.url.path!='/api/auth/logout':
            return JSONResponse({'detail':'Investor access is read-only. This action is not permitted.'},status_code=403)
        # Public demo owners cannot reach external services, credentials, infrastructure or identity providers.
        if not EXTERNAL_ACTIONS and (request.url.path.startswith(('/api/auth/oauth','/api/webhooks')) or (unsafe and (request.url.path.startswith(('/api/admin/providers','/api/admin/oauth','/api/admin/ai','/api/assistant')) or '/ai' in request.url.path or request.url.path.endswith('/test-send')))):
            return JSONResponse({'detail':'External integrations are disabled in this isolated demonstration. No messages, charges or AI requests are sent.'},status_code=403)
        response=await call_next(request)
        response.headers['X-Voltora-Environment']=RUNTIME_MODE
        return response
    finally:
        workspace.reset(token)

class DemoStart(Input):
    role: Literal['owner','investor']='owner'

@router.post('/demo/start')
async def demo_start(data:DemoStart,request:Request,response:Response):
    raise HTTPException(404, 'Public demo access is disabled. Use the private owner sign-in.')
    # Rate-limited at ingress middleware. This creates an isolated, synthetic workspace only.
    ns='d'+uid()
    workspace.set(ns)
    from seed import seed_demo_workspace
    from pymongo.errors import AutoReconnect, ConnectionFailure
    import asyncio
    for attempt in range(3):
        try:
            await seed_demo_workspace()
            break
        except (AutoReconnect, ConnectionFailure):
            if attempt == 2:
                raise HTTPException(503, 'The demonstration database is reconnecting. Please try again shortly.')
            await asyncio.sleep(0.5 * (attempt + 1))
    await raw_db[PREFIX+'workspace_registry'].insert_one({'id':ns,'created_at':stamp(),'mode':'demo'})
    user={'id':uid(),'name':'Demo Owner' if data.role=='owner' else 'Investor Viewer','email':data.role+'@demo.voltora.invalid','password_hash':hasher.hash(secrets.token_urlsafe(40)),'role':data.role,'mfa_enabled':False,'demo_identity':True,'created_at':stamp(),'addresses':[]}
    await db.users.insert_one(user.copy())
    response.set_cookie('voltora_workspace',ns,httponly=True,secure=os.environ['APP_ORIGIN'].startswith('https'),samesite='lax',max_age=86400,path='/')
    result=await create_session(user,request,response,mfa=True)
    return {**result,'environment':'demo','isolated':True}

@router.get('/environment')
async def environment():
    return {'mode':RUNTIME_MODE,'isolated_demo':False,'external_delivery':EXTERNAL_ACTIONS,'base_country':'BD','sandbox_verified':False,'live_verified':False}
