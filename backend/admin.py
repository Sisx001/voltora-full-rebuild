import csv
import io
import time
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field, EmailStr
from pymongo.errors import DuplicateKeyError
from core import db, Doc, Input, uid, stamp, now, audit, settings
from schemas import Settings
from permissions import require, ROLES, authorize
from auth import current_user, hasher
import providers

router=APIRouter(prefix='/api/admin',tags=['Administration'])

@router.get('/overview',response_model=Doc)
async def overview(user=Depends(require('analytics.read'))):
    orders=await db.orders.find({'status':{'$nin':['failed','initiating']}},{'_id':0}).to_list(10000)
    inventory=await db.inventory.find_one({'id':'main'},{'_id':0}) or {}
    products=await db.products.find({},{'_id':0,'id':1,'name':1,'images':1,'variants':1}).to_list(1000)
    low=[]
    for p in products:
        for v in p['variants']:
            stock=inventory.get('quantities',{}).get(v['id'],0)
            if stock<10:low.append({'name':p['name'],'sku':v['sku'],'stock':stock,'id':v['id']})
    collected=sum(o['total'] for o in orders if o['payment_status']=='paid')
    daily={}
    for o in orders:
        date=o['created_at'][:10]
        daily.setdefault(date,{'date':date,'orders':0,'revenue':0})
        daily[date]['orders']+=1
        if o['payment_status']=='paid':daily[date]['revenue']+=o['total']
    top={}
    for o in orders:
        if o['status']=='cancelled':continue
        for i in o['items']:
            if i['product_id'] not in top:top[i['product_id']]={'name':i['name'],'quantity':0,'revenue':0,'image':i['image']}
            top[i['product_id']]['quantity']+=i['quantity']
            if o['payment_status']=='paid':top[i['product_id']]['revenue']+=i['total']
    return {'activity':await db.audit_logs.find({},{'_id':0}).sort('created_at',-1).limit(4).to_list(4),'revenue':collected,'orders':len(orders),'customers':await db.users.count_documents({'role':'customer'}),'products':len(products),'average_order':round(sum(o['total'] for o in orders)/len(orders)) if orders else 0,'unpaid':sum(1 for o in orders if o['payment_status'] not in ['paid','refunded']),'support':await db.conversations.count_documents({'status':'open'}),'low_stock':low[:12],'recent_orders':[{k:o[k] for k in ['id','number','total','status','payment_status','created_at']} for o in sorted(orders,key=lambda x:x['created_at'],reverse=True)[:6]],'daily':sorted(daily.values(),key=lambda d:d['date']),'top_products':sorted(top.values(),key=lambda x:x['quantity'],reverse=True)[:5]}

@router.get('/settings',response_model=Doc)
async def get_settings(user=Depends(current_user)):
    if not any(p in user_permissions(user) for p in ['settings.read','payments.read','shipping.read']):
        await authorize(user,'settings.read')
    elif user['role']!='customer' and not user['session_mfa']:
        raise HTTPException(403,'Two-factor authentication is required')
    return await db.settings.find_one({'id':'store'},{'_id':0})

def user_permissions(user):return user.get('permissions') if isinstance(user.get('permissions'),list) else ROLES.get(user['role'],[])

async def available_roles():
    custom=await db.roles.find({},{'_id':0,'id':1,'permissions':1}).to_list(100)
    return {**{rid:list(perms) for rid,perms in ROLES.items() if rid not in ('owner','customer')},**{r['id']:r.get('permissions',[]) for r in custom}}

class SettingsSave(Input):
    value:Settings
    version:int=Field(ge=1)

@router.put('/settings',response_model=Doc)
async def save_settings(data:SettingsSave,user=Depends(require('settings.update'))):
    value=data.value.model_dump()
    current=await settings()
    if value.get('base_currency','BDT')!=current.get('base_currency','BDT'):
        raise HTTPException(422,'Use Market & settlement settings to change the base currency safely')
    if not any(c['code']==value.get('base_currency','BDT') and c['rate']==1 and c['enabled'] for c in value['currencies']):
        raise HTTPException(422,'The selling currency must be enabled at rate 1')
    from core import RUNTIME_MODE
    if RUNTIME_MODE!='production':
        value['demo_catalog']=True
    if value['features']['ai_chat'] or value['features']['ai_authoring']:
        if not await db.integrations.find_one({'id':'deepseek','connected':True}):raise HTTPException(422,'Connect an AI provider before enabling AI features')
    if not value['features']['support']:value['features']['ai_chat']=False
    if value['features']['online_payments'] and not await providers.any_connected(db,'payment'):
        raise HTTPException(422,'Connect and enable a payment provider before accepting online payments')
    r=await db.settings.update_one({'id':'store','version':data.version},{'$set':{'value':value},'$inc':{'version':1}})
    if not r.modified_count:raise HTTPException(409,'Settings were changed by another editor. Reload before saving.')
    await audit(user,'settings.updated')
    return {'version':data.version+1}

class PaymentSave(Input):
    payments:list
    version:int

@router.put('/payment-settings',response_model=Doc)
async def payment_settings(data:PaymentSave,user=Depends(require('payments.update'))):
    from schemas import PaymentMethod
    values=[PaymentMethod(**p).model_dump() for p in data.payments]
    connected=set()
    for row in await providers.active_payment_methods(db):connected.update(row.get('method_ids',[]))
    offline=['cod','bank_transfer']
    if any(p['enabled'] and p['id'] not in offline and p['id'] not in connected for p in values):
        raise HTTPException(422,'An online method is enabled without a connected provider. Configure the provider first.')
    result=await db.settings.update_one({'id':'store','version':data.version},{'$set':{'value.payments':values},'$inc':{'version':1}})
    if not result.modified_count:raise HTTPException(409,'Settings changed. Reload to continue.')
    await audit(user,'payments.configuration_updated')
    return {'version':data.version+1}

@router.get('/catalog/{kind}',response_model=list[Doc])
async def list_catalog(kind:Literal['categories','brands','collections'],user=Depends(require('catalog.read'))):
    return await db[kind].find({},{'_id':0}).to_list(500)

class Taxonomy(Input):
    name:str=Field(min_length=2,max_length=100)
    slug:str=Field(pattern=r'^[a-z0-9-]+$')
    description:str=Field(default='',max_length=2000)
    image:str=Field(default='',max_length=2000)
    icon:str=Field(default='Grid2X2',max_length=40)
    enabled:bool=True
    parent_id:str=Field(default='',max_length=80)
    position:int=0
    demo_industry:str=Field(default='',max_length=40)
    seo_title:str=Field(default='',max_length=180)

@router.post('/catalog/{kind}',response_model=Doc)
async def create_taxonomy(kind:Literal['categories','brands','collections'],data:Taxonomy,user=Depends(require('catalog.update'))):
    if await db[kind].find_one({'slug':data.slug}):raise HTTPException(409,'This slug is already used')
    row={'id':data.slug,**data.model_dump()}
    await db[kind].insert_one(row.copy())
    await audit(user,kind+'.created',row['id'])
    return row

@router.put('/catalog/{kind}/{id}',response_model=Doc)
async def update_taxonomy(kind:Literal['categories','brands','collections'],id:str,data:Taxonomy,user=Depends(require('catalog.update'))):
    if data.parent_id==id:raise HTTPException(422,'A category cannot be its own parent')
    parent=data.parent_id
    visited={id}
    while parent:
        if parent in visited:raise HTTPException(422,'Category hierarchy cannot contain a cycle')
        visited.add(parent)
        ancestor=await db[kind].find_one({'id':parent},{'_id':0})
        if not ancestor:raise HTTPException(422,'Parent category does not exist')
        parent=ancestor.get('parent_id','')
    update=data.model_dump()
    if not update.get('demo_industry'):update.pop('demo_industry',None)
    await db[kind].update_one({'id':id},{'$set':update})
    await audit(user,kind+'.updated',id)
    return {'ok':True}

@router.get('/inventory',response_model=Doc)
async def inventory(user=Depends(require('inventory.read'))):
    inv=await db.inventory.find_one({'id':'main'},{'_id':0,'quantities':1}) or {}
    products=await db.products.find({},{'_id':0}).to_list(1000)
    items=[{'id':v['id'],'product_id':p['id'],'name':p['name'],'sku':v['sku'],'options':v['options'],'stock':inv.get('quantities',{}).get(v['id'],0),'image':p['images'][0] if p['images'] else ''} for p in products for v in p['variants']]
    return {'items':items,'movements':await db.stock_movements.find({},{'_id':0}).sort('created_at',-1).to_list(100)}

class Adjustment(Input):
    variant_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    adjustment:int=Field(ge=-100000,le=100000)
    reason:str=Field(min_length=3,max_length=300)

@router.post('/inventory/adjust',response_model=Doc)
async def adjust(data:Adjustment,user=Depends(require('inventory.update'))):
    if not await db.products.find_one({'variants.id':data.variant_id}):raise HTTPException(404,'Variant not found')
    q={'id':'main'}
    if data.adjustment<0:q[f'quantities.{data.variant_id}']={'$gte':-data.adjustment}
    result=await db.inventory.update_one(q,{'$inc':{f'quantities.{data.variant_id}':data.adjustment}})
    if not result.modified_count:raise HTTPException(409,'Adjustment would result in negative stock, or no change was made')
    await db.stock_movements.insert_one({'id':uid(),**data.model_dump(),'actor':user['name'],'type':'adjustment','created_at':stamp()})
    await audit(user,'inventory.adjusted',data.variant_id,data.reason)
    return {'ok':True}

class Coupon(Input):
    code:str=Field(pattern=r'^[A-Z0-9-]{2,30}$')
    type:Literal['percentage','fixed']='percentage'
    value:int=Field(gt=0)
    min_spend:int=Field(default=0,ge=0)
    max_uses:int=Field(default=100,ge=1)
    enabled:bool=True
    starts_at:str=''
    ends_at:str=''
    product_ids:list[str]=Field(default_factory=list,max_length=100)
    category_ids:list[str]=Field(default_factory=list,max_length=100)

@router.get('/coupons',response_model=list[Doc])
async def coupons(user=Depends(require('coupons.read'))):
    return await db.coupons.find({},{'_id':0}).to_list(500)

@router.post('/coupons',response_model=Doc)
async def create_coupon(data:Coupon,user=Depends(require('coupons.update'))):
    if data.type=='percentage' and data.value>100:raise HTTPException(422,'Percentage cannot exceed 100')
    if await db.coupons.find_one({'code':data.code}):raise HTTPException(409,'Coupon already exists')
    row={'id':uid(),'used':0,**data.model_dump()}
    await db.coupons.insert_one(row.copy())
    await audit(user,'coupon.created',row['id'])
    return row

@router.put('/coupons/{id}',response_model=Doc)
async def update_coupon(id:str,data:Coupon,user=Depends(require('coupons.update'))):
    if data.type=='percentage' and data.value>100:raise HTTPException(422,'Percentage cannot exceed 100')
    other=await db.coupons.find_one({'code':data.code,'id':{'$ne':id}})
    if other:raise HTTPException(409,'Coupon code already exists')
    await db.coupons.update_one({'id':id},{'$set':data.model_dump()})
    await audit(user,'coupon.updated',id)
    return {'ok':True}

@router.get('/customers',response_model=list[Doc])
async def customers(user=Depends(require('customers.read'))):
    return await db.users.find({'role':'customer'},{'_id':0,'id':1,'name':1,'email':1,'created_at':1}).to_list(1000)

@router.get('/team',response_model=Doc)
async def team(user=Depends(require('roles.read'))):
    return {'roles':await available_roles(),'members':await db.users.find({'role':{'$ne':'customer'}},{'_id':0,'id':1,'name':1,'email':1,'role':1,'mfa_enabled':1,'disabled':1}).sort('created_at',1).to_list(100)}

class Staff(Input):
    name:str=Field(min_length=2,max_length=80)
    email:EmailStr
    password:str=Field(min_length=12,max_length=128)
    role:str=Field(min_length=2,max_length=40)

@router.post('/team',response_model=Doc)
async def invite(data:Staff,user=Depends(require('roles.update'))):
    if data.role not in await available_roles():raise HTTPException(422,'Unknown role')
    staff={'id':uid(),'name':data.name,'email':data.email.lower(),'password_hash':hasher.hash(data.password),'role':data.role,'created_at':stamp(),'mfa_enabled':False,'addresses':[]}
    try:await db.users.insert_one(staff)
    except DuplicateKeyError:raise HTTPException(409,'Email is already registered')
    await audit(user,'staff.created',staff['id'],data.role)
    return {'ok':True}

class RoleUpdate(Input):
    role:str=Field(min_length=2,max_length=40)
    disabled:bool=False

@router.put('/team/{id}',response_model=Doc)
async def role_update(id:str,data:RoleUpdate,user=Depends(require('roles.update'))):
    target=await db.users.find_one({'id':id})
    if not target or target['role']=='owner':raise HTTPException(403,'Owner access cannot be changed here')
    if data.role not in await available_roles():raise HTTPException(422,'Unknown role')
    await db.users.update_one({'id':id},{'$set':{'role':data.role,'disabled':data.disabled}})
    await db.sessions.delete_many({'user_id':id})
    await audit(user,'staff.role_changed',id,data.role)
    return {'ok':True}

@router.get('/audit',response_model=list[Doc])
async def audit_log(user=Depends(require('audit.read'))):
    await audit(user,'audit.viewed')
    return await db.audit_logs.find({},{'_id':0}).sort('created_at',-1).to_list(300)

@router.get('/security',response_model=Doc)
async def security(user=Depends(require('security.read'))):
    await audit(user,'security.viewed')
    start=time.monotonic()
    await db.command('ping')
    import providers
    payments='connected' if await providers.any_connected(db,'payment') else 'not_configured'
    email_status='connected' if await providers.any_connected(db,'messaging','email') else 'not_configured'
    sms='connected' if await providers.any_connected(db,'messaging','sms') else 'not_configured'
    couriers='connected' if await providers.any_connected(db,'courier') else 'not_configured'
    return {'database':{'status':'healthy','latency_ms':round((time.monotonic()-start)*1000,2)},'sessions':await db.sessions.find({'expires_at':{'$gt':now()}},{'_id':0,'token_hash':0,'csrf':0}).to_list(100),'login_attempts':await db.login_attempts.find({},{'_id':0,'key':0}).sort('created_at',-1).to_list(100),'mfa_enabled':user.get('mfa_enabled',False),'integrations':[{'name':'Online payments','status':payments},{'name':'DeepSeek','status':'connected' if await db.integrations.find_one({'id':'deepseek','connected':True}) else 'not_configured'},{'name':'Email delivery','status':email_status},{'name':'SMS delivery','status':sms},{'name':'Couriers','status':couriers}]}

@router.delete('/security/sessions/{id}',response_model=Doc)
async def revoke_staff(id:str,user=Depends(require('security.update'))):
    await db.sessions.delete_one({'id':id})
    await audit(user,'session.revoked',id)
    return {'ok':True}

@router.get('/export/orders')
async def export(user=Depends(require('orders.export'))):
    orders=await db.orders.find({},{'_id':0,'number':1,'created_at':1,'total':1,'status':1,'payment_status':1}).to_list(10000)
    buffer=io.StringIO()
    w=csv.writer(buffer)
    w.writerow(['Order','Date','Total BDT','Status','Payment'])
    for o in orders:w.writerow([o['number'],o['created_at'],o['total']/100,o['status'],o['payment_status']])
    await audit(user,'orders.exported',detail=str(len(orders)))
    return Response(buffer.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=voltora-orders.csv'})

@router.get('/reviews',response_model=list[Doc])
async def moderate_reviews(user=Depends(require('products.read'))):
    return await db.reviews.find({},{'_id':0}).sort('created_at',-1).to_list(300)

class Moderation(Input):
    status:Literal['published','rejected']

@router.put('/reviews/{id}',response_model=Doc)
async def moderation(id:str,data:Moderation,user=Depends(require('products.publish'))):
    await db.reviews.update_one({'id':id},{'$set':{'status':data.status}})
    await audit(user,'review.moderated',id,data.status)
    return {'ok':True}