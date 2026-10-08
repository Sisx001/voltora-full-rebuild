import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, Request, HTTPException
from typing import Literal
from pydantic import Field, EmailStr
from core import db, Input, Doc, uid, stamp, digest, flag, now, audit
from auth import current_user, optional_user
from permissions import require

router=APIRouter(prefix='/api',tags=['Customers and support'])

class Wishlist(Input):
    product_ids:list[str]=Field(default_factory=list,max_length=100)

@router.get('/customer/wishlist',response_model=Doc)
async def wishlist(user=Depends(current_user)):
    return {'product_ids':user.get('wishlist',[])}

@router.put('/customer/wishlist',response_model=Doc)
async def save_wishlist(data:Wishlist,user=Depends(current_user)):
    if not await flag('wishlist'):raise HTTPException(403,'Wishlist is unavailable')
    await db.users.update_one({'id':user['id']},{'$set':{'wishlist':list(dict.fromkeys(data.product_ids))}})
    return {'ok':True}

class Newsletter(Input):
    email:EmailStr

@router.post('/newsletter',response_model=Doc)
async def newsletter(data:Newsletter):
    await db.newsletter.update_one({'email':data.email.lower()},{'$setOnInsert':{'id':uid(),'created_at':stamp(),'consent':True}},upsert=True)
    return {'ok':True}

class Privacy(Input):
    type:Literal['export','delete']
    message:str=Field(default='',max_length=2000)

@router.post('/customer/privacy',response_model=Doc)
async def privacy(data:Privacy,user=Depends(current_user)):
    await db.privacy_requests.insert_one({'id':uid(),'user_id':user['id'],'email':user['email'],'status':'pending','created_at':stamp(),**data.model_dump()})
    return {'message':'Your request is recorded for identity-verified review. Required transaction records may be retained.'}

class Conversation(Input):
    name:str=Field(min_length=2,max_length=80)
    email:EmailStr
    subject:str=Field(min_length=3,max_length=200)
    message:str=Field(min_length=1,max_length=5000)
    order_id:str=Field(default='',max_length=100)
    order_access:str=Field(default='',max_length=100)
    use_ai:bool=False

@router.post('/support/conversations',response_model=Doc)
async def start(data:Conversation,request:Request):
    if not await flag('support'):raise HTTPException(403,'Support messaging is currently unavailable')
    if data.use_ai and (not await flag('ai_chat') or not await db.integrations.find_one({'id':'deepseek','connected':True})):
        raise HTTPException(503,'AI is unavailable; send a message to the human team instead')
    user=await optional_user(request)
    if data.order_id:
        from commerce import customer_order
        await customer_order(data.order_id,request,data.order_access)
    id=uid();token=secrets.token_urlsafe(32)
    row={'id':id,'user_id':user['id'] if user else None,'name':data.name,'email':data.email,'subject':data.subject,'order_id':data.order_id,'access_hash':digest(token),'created_at':stamp(),'updated_at':stamp(),'status':'open','priority':'normal','assigned_to':'','mode':'ai' if data.use_ai else 'human'}
    await db.conversations.insert_one(row)
    await db.messages.insert_one({'id':uid(),'conversation_id':id,'sender':'customer','name':data.name,'text':data.message,'internal':False,'created_at':stamp()})
    return {'id':id,'access':token}

async def owned_conversation(id,request,access):
    user=await optional_user(request)
    q={'id':id}
    if user:q['$or']=[{'user_id':user['id']},{'access_hash':digest(access)}]
    else:q['access_hash']=digest(access)
    row=await db.conversations.find_one(q,{'_id':0,'access_hash':0})
    if not row:raise HTTPException(404,'Conversation not found')
    return row

@router.get('/support/conversations',response_model=list[Doc])
async def conversations(user=Depends(current_user)):
    return await db.conversations.find({'user_id':user['id']},{'_id':0,'access_hash':0}).sort('updated_at',-1).to_list(100)

@router.get('/support/conversations/{id}',response_model=Doc)
async def read_conversation(id:str,request:Request,access:str=''):
    row=await owned_conversation(id,request,access)
    row['messages']=await db.messages.find({'conversation_id':id,'internal':False},{'_id':0}).sort('created_at',1).to_list(1000)
    return row

@router.post('/support/conversations/{id}/handoff',response_model=Doc)
async def handoff(id:str,request:Request,access:str=''):
    await owned_conversation(id,request,access)
    await db.conversations.update_one({'id':id},{'$set':{'mode':'human','status':'open','updated_at':stamp()}})
    return {'ok':True}

class Event(Input):
    event:Literal['page_view','product_view','search','add_to_cart','remove_from_cart','begin_checkout','checkout_step','purchase','wishlist','compare','support_started','login','logout']
    visitor_id:str=Field(pattern=r'^[a-zA-Z0-9-]{16,80}$')
    path:str=Field(max_length=300)
    consent:bool
    term:str=Field(default='',max_length=100)
    referrer:str=Field(default='',max_length=300)
    utm:dict[str,str]=Field(default_factory=dict,max_length=5)

def parse_device(user_agent):
    ua=(user_agent or '').lower()
    browser='other'
    for candidate in ['edg/','chrome','safari','firefox','opr/']:
        if candidate in ua:browser=candidate.strip('/.');break
    os='other'
    for candidate in ['windows','mac os','android','iphone','ipad','linux']:
        if candidate in ua:os=candidate;break
    device_type='mobile' if any(x in ua for x in ['iphone','android','mobile']) else ('tablet' if 'ipad' in ua else 'desktop')
    return {'browser':browser,'os':os,'device_type':device_type}

@router.post('/events',response_model=Doc)
async def event(data:Event,request:Request):
    if not data.consent or not await flag('analytics'):return {'recorded':False}
    visitor=digest(data.visitor_id)
    device=parse_device(request.headers.get('user-agent',''))
    referrer=data.referrer[:300]
    await db.events.insert_one({'id':uid(),'event':data.event,'visitor_id':visitor,'path':data.path.split('?')[0],'term':data.term.lower()[:100],'created_at':stamp(),'expires_at':now()+timedelta(days=30)})
    await db.visitor_sessions.update_one({'id':visitor},{'$setOnInsert':{'id':visitor,'first_seen':stamp(),'entry_page':data.path.split('?')[0],'utm':{k:str(v)[:120] for k,v in data.utm.items() if k in ('utm_source','utm_medium','utm_campaign','utm_term','utm_content')},'referrer':referrer,**device,'expires_at':now()+timedelta(days=30)},'$set':{'last_seen':stamp(),'exit_page':data.path.split('?')[0]}})
    return {'recorded':True}

class Message(Input):
    text:str=Field(min_length=1,max_length=5000)
    internal:bool=False

@router.post('/support/conversations/{id}/messages',response_model=Doc)
async def reply(id:str,data:Message,request:Request,access:str=''):
    if not await flag('support'):raise HTTPException(403,'Support messaging is unavailable')
    row=await owned_conversation(id,request,access)
    await db.messages.insert_one({'id':uid(),'conversation_id':id,'sender':'customer','name':row['name'],'text':data.text,'internal':False,'created_at':stamp()})
    await db.conversations.update_one({'id':id},{'$set':{'updated_at':stamp(),'status':'open'}})
    return {'ok':True}

@router.get('/admin/support',response_model=list[Doc])
async def inbox(user=Depends(require('support.read'))):
    return await db.conversations.find({},{'_id':0,'access_hash':0}).sort('updated_at',-1).to_list(300)

@router.get('/admin/support/{id}',response_model=Doc)
async def staff_conversation(id:str,user=Depends(require('support.read'))):
    row=await db.conversations.find_one({'id':id},{'_id':0,'access_hash':0})
    if not row:raise HTTPException(404,'Conversation not found')
    row['messages']=await db.messages.find({'conversation_id':id},{'_id':0}).sort('created_at',1).to_list(1000)
    return row

@router.post('/admin/support/{id}/messages',response_model=Doc)
async def staff_reply(id:str,data:Message,user=Depends(require('support.update'))):
    row=await db.conversations.find_one({'id':id},{'_id':0})
    if not row:raise HTTPException(404,'Conversation not found')
    await db.messages.insert_one({'id':uid(),'conversation_id':id,'sender':'staff','name':user['name'],'text':data.text,'internal':data.internal,'created_at':stamp()})
    meta={'updated_at':stamp(),'mode':'human'}
    if not row.get('first_response_at') and not data.internal:meta['first_response_at']=stamp()
    await db.conversations.update_one({'id':id},{'$set':meta})
    if not data.internal and row.get('user_id'):
        from notifications import notify
        await notify(row['user_id'],'support','New reply from support',f"Our team replied to \"{row.get('subject','your conversation')}\".",'/support')
    await audit(user,'support.replied',id)
    return {'ok':True}

class SupportUpdate(Input):
    status:Literal['open','resolved']='open'
    priority:Literal['low','normal','high']='normal'
    assigned_to:str=Field(default='',max_length=80)

@router.put('/admin/support/{id}',response_model=Doc)
async def support_update(id:str,data:SupportUpdate,user=Depends(require('support.update'))):
    if data.assigned_to and not await db.users.find_one({'id':data.assigned_to,'role':{'$ne':'customer'}}):raise HTTPException(422,'Select a staff account')
    await db.conversations.update_one({'id':id},{'$set':{**data.model_dump(),'updated_at':stamp()}})
    await audit(user,'support.updated',id)
    return {'ok':True}

@router.get('/admin/privacy',response_model=list[Doc])
async def privacy_requests(user=Depends(require('customers.read'))):
    return await db.privacy_requests.find({},{'_id':0}).sort('created_at',-1).to_list(300)

class PrivacyUpdate(Input):
    status:Literal['pending','in_review','completed','retained_records']
    note:str=Field(min_length=3,max_length=2000)

@router.put('/admin/privacy/{id}',response_model=Doc)
async def review_privacy(id:str,data:PrivacyUpdate,user=Depends(require('customers.update'))):
    await db.privacy_requests.update_one({'id':id},{'$set':{**data.model_dump(),'reviewed_by':user['id'],'updated_at':stamp()}})
    await audit(user,'privacy.request_reviewed',id,data.status)
    return {'ok':True}