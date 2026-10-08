import os
import hmac
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import Field, EmailStr
from pymongo.errors import DuplicateKeyError
from core import db, Input, Doc, uid, stamp, digest, settings, audit
from auth import optional_user, current_user
from permissions import require
from schemas import Address

router=APIRouter(prefix='/api',tags=['Commerce'])

class Line(Input):
    product_id:str
    variant_id:str=Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    quantity:int=Field(ge=1,le=50)
    expected_price:int=Field(ge=0)

class Quote(Input):
    items:list[Line]=Field(min_length=1,max_length=50)
    shipping_id:str='dhaka'
    coupon:str=Field(default='',max_length=80)
    location:Address|None=None
    redeem_points:int=Field(default=0,ge=0)
    use_credit:bool=False

class Checkout(Quote):
    name:str=Field(min_length=2,max_length=100)
    email:EmailStr
    phone:str=Field(min_length=7,max_length=25)
    address:str=Field(min_length=5,max_length=500)
    city:str=Field(min_length=2,max_length=100)
    postal_code:str=Field(default='',max_length=20)
    payment_method:Literal['cod','bank_transfer','stripe','sslcommerz','bkash','nagad','rocket','upay','paypal','mock']
    notes:str=Field(default='',max_length=1000)
    terms:bool
    marketing:bool=False

def rounded(value):return int(Decimal(str(value)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def zone_matches(shipping, location):
    '''A zone without matchers covers everywhere; a zoned zone requires a structured
    location whose district (or division) is listed.'''
    districts=shipping.get('districts') or []
    divisions=shipping.get('divisions') or []
    if not districts and not divisions:return True
    if not location:return False
    if districts:return location.get('district_id') in districts
    return location.get('division_id') in divisions

async def location_snapshot(location):
    '''Resolve structured ids into display names for order records.'''
    if not location or not any([location.division_id,location.district_id,location.upazila_id,location.area_id]):return {}
    out={}
    for key,kind,prefix in [('division_id','division','div:'),('district_id','district','dis:'),('upazila_id','upazila','upa:'),('area_id','area','area:')]:
        value=getattr(location,key)
        if not value:continue
        row=await db.locations.find_one({'id':value},{'_id':0,'name':1,'name_bn':1,'postcode':1,'kind':1}) if value.startswith(prefix) else None
        if row and row['kind']==kind:
            out[key]={'id':value,'name':row['name'],'name_bn':row.get('name_bn',''),'postcode':row.get('postcode','')}
    return out

async def calculate(data,user=None):
    config=await settings()
    if config['mode']!='live':raise HTTPException(503,'The store is not accepting orders right now')
    if len({x.variant_id for x in data.items})!=len(data.items):raise HTTPException(422,'Combine duplicate variants before checkout')
    inv=await db.inventory.find_one({'id':'main'},{'_id':0,'quantities':1}) or {}
    quantities=inv.get('quantities',{})
    rows=[]
    for line in data.items:
        product=await db.products.find_one({'id':line.product_id,'published':True},{'_id':0})
        variant=next((v for v in product['variants'] if v['id']==line.variant_id),None) if product else None
        if not variant:raise HTTPException(409,'An item is no longer available. Please update your bag.')
        if variant['price']!=line.expected_price:raise HTTPException(409,f"The price of {product['name']} has changed. Remove it from your bag and add it again to confirm the new price.")
        if quantities.get(variant['id'],0)<line.quantity:raise HTTPException(409,f"Not enough stock for {product['name']}. Update your quantity.")
        rows.append({'product_id':product['id'],'variant_id':variant['id'],'name':product['name'],'sku':variant['sku'],'category':product['category'],'image':product['images'][0] if product['images'] else '', 'options':variant['options'],'quantity':line.quantity,'price':variant['price'],'total':variant['price']*line.quantity})
    subtotal=sum(x['total'] for x in rows)
    discount=0
    coupon=None
    if data.coupon:
        if not config['features']['coupons']:raise HTTPException(400,'Coupons are currently unavailable')
        coupon=await db.coupons.find_one({'code':data.coupon.upper(),'enabled':True},{'_id':0})
        if not coupon or coupon['used']>=coupon['max_uses'] or subtotal<coupon['min_spend'] or (coupon.get('starts_at') and coupon['starts_at']>stamp()) or (coupon.get('ends_at') and coupon['ends_at']<stamp()):raise HTTPException(400,'This coupon is invalid, expired, or its minimum spend has not been reached')
        eligible=sum(x['total'] for x in rows if (not coupon.get('product_ids') or x['product_id'] in coupon['product_ids']) and (not coupon.get('category_ids') or x['category'] in coupon['category_ids']))
        if not eligible:raise HTTPException(400,'This coupon does not apply to the selected products')
        discount=min(eligible,rounded(eligible*coupon['value']/100) if coupon['type']=='percentage' else coupon['value'])
    points_discount=0;credit_discount=0;points_redeemed=0
    if user and (data.redeem_points>0 or data.use_credit):
        wallet=await db.users.find_one({'id':user['id']},{'_id':0,'points':1,'credit_balance':1}) or {}
        if data.redeem_points>0 and config['features'].get('loyalty'):
            poisha=config.get('loyalty_point_poisha',50)
            points=min(data.redeem_points,wallet.get('points',0))
            capped=min(points*poisha,rounded((subtotal-discount)*0.5))
            points_redeemed=capped//poisha
            points_discount=points_redeemed*poisha
        if data.use_credit and config['features'].get('store_credit'):
            credit_discount=max(0,min(wallet.get('credit_balance',0),subtotal-discount-points_discount))
    shipping=next((s for s in config['shipping'] if s['id']==data.shipping_id and s['enabled']),None)
    if not shipping or (data.shipping_id=='pickup' and not config['features']['pickup']) or (data.shipping_id!='pickup' and not config['features']['shipping']):raise HTTPException(400,'Select an available delivery method')
    location=data.location.model_dump() if data.location else None
    if not zone_matches(shipping,location):raise HTTPException(400,'This delivery option does not cover the selected address')
    fee=0 if shipping['free_above'] and subtotal-discount-points_discount-credit_discount>=shipping['free_above'] else shipping['fee']
    if shipping.get('courier'):
        import providers
        courier=await providers.courier_config(db,shipping['courier'])
        if not courier:raise HTTPException(400,'Courier delivery is temporarily unavailable. Choose another option.')
        try:courier_charge=int((courier.get('config') or {}).get('charge') or 0)
        except ValueError:courier_charge=0
        if courier_charge and not (shipping['free_above'] and subtotal-discount-points_discount-credit_discount>=shipping['free_above']):fee=courier_charge
    net=subtotal-discount-points_discount-credit_discount
    tax=rounded(net*config['tax_rate']/(100+config['tax_rate'])) if config['tax_inclusive'] else rounded(net*config['tax_rate']/100)
    total=net+fee+(0 if config['tax_inclusive'] else tax)
    return {'items':rows,'subtotal':subtotal,'discount':discount,'points_redeemed':points_redeemed,'points_discount':points_discount,'credit_discount':credit_discount,'shipping':fee,'tax':tax,'tax_inclusive':config['tax_inclusive'],'total':total,'currency':config.get('base_currency','BDT'),'coupon':coupon['code'] if coupon else '', 'shipping_method':shipping['name'],'shipping_estimate':shipping['estimate']},config

@router.post('/cart/quote',response_model=Doc)
async def quote(data:Quote,request:Request):
    user=await optional_user(request)
    return (await calculate(data,user))[0]

def access_token(order):
    from core import workspace
    ns=workspace.get()
    sig=hmac.new(os.environ['APP_SECRET'].encode(),(ns+order['id']+order['idempotency_key']).encode(),hashlib.sha256).hexdigest()
    return (ns+'.' if ns else '')+sig

def confirmation(order):
    return {'id':order['id'],'number':order['number'],'access':access_token(order),'status':order['status'],'payment_status':order['payment_status'],'total':order['total'],'currency':order.get('currency','BDT')}

async def release_inventory(order):
    increments={f"quantities.{i['variant_id']}":i['quantity'] for i in order['items']}
    await db.inventory.update_one({'id':'main',f"reservations.{order['id']}":{'$exists':True}},{'$inc':increments,'$unset':{f"reservations.{order['id']}":''}})

@router.post('/checkout',response_model=Doc)
async def checkout(data:Checkout,request:Request,idempotency_key:str=Header(...,min_length=16,max_length=100)):
    user=await optional_user(request)
    from core import RUNTIME_MODE
    if RUNTIME_MODE != 'production' and data.payment_method != 'cod':
        raise HTTPException(403, 'Only unpaid, isolated demonstration orders are available in demo mode.')
    request_hash=digest(json.dumps(data.model_dump(),sort_keys=True))
    prior=await db.orders.find_one({'idempotency_key':idempotency_key},{'_id':0})
    if prior:
        if prior['request_hash']!=request_hash:raise HTTPException(409,'This checkout key was already used with different details')
        if prior['status']=='initiating':raise HTTPException(409,'Order is being processed. Please retry shortly.')
        if prior['status']=='failed':raise HTTPException(409,'This checkout attempt failed. Start a new checkout.')
        if prior['payment_method'] not in ['cod','bank_transfer'] and prior['status'] in ['pending','awaiting_payment']:
            from payments import start_online_payment
            payment=await start_online_payment(prior,request)
            return {**confirmation(prior),'payment':payment}
        return confirmation(prior)
    amounts,config=await calculate(data,user)
    if RUNTIME_MODE == 'production':
        demo_ids=[i.product_id for i in data.items]
        if await db.products.find_one({'id':{'$in':demo_ids},'demo':True},{'_id':1}):
            raise HTTPException(409,'Demo products must be explicitly converted to real inventory before checkout.')
    if user and user.get('ban',{}).get('active'):raise HTTPException(403,'Your account cannot place orders. Contact support.')
    if not user and not config['features']['guest_checkout']:raise HTTPException(401,'Sign in before placing your order')
    if not data.terms:raise HTTPException(422,'Please accept the terms to place an order')
    method=next((p for p in config['payments'] if p['id']==data.payment_method and p['enabled']),None)
    if not method or not config['features'].get(data.payment_method,config['features']['online_payments']):raise HTTPException(400,'This payment method is unavailable')
    if data.payment_method not in ['cod','bank_transfer']:
        import providers
        if not await providers.payment_config(db,data.payment_method):raise HTTPException(503,'This payment provider is not connected. Choose another method.')
    if data.payment_method=='bank_transfer' and not method['instructions'].strip():raise HTTPException(400,'Bank instructions have not been configured')
    if not method['min_amount']<=amounts['total']<=method['max_amount']:raise HTTPException(400,'Order total is outside this payment method’s limits')
    id=uid()
    location_data=await location_snapshot(data.location) if data.location else {}
    customer={k:getattr(data,k) for k in ['name','email','phone','address','city','postal_code']}
    if data.location:
        if data.location.area_id and not data.location.postcode:
            area=await db.locations.find_one({'id':data.location.area_id,'kind':'area'},{'_id':0,'postcode':1})
            if area and area.get('postcode'):
                data.location.postcode=area['postcode']
                if 'area_id' in location_data:location_data['area_id']['postcode']=area['postcode']
            customer['postal_code']=data.location.postcode
        if data.location.address_line:customer['address']=data.location.address_line
        customer['location']=location_data
    transaction_id='tx'+uid()[:16]
    order={**amounts,'id':id,'number':'VT-'+id[:8].upper(),'idempotency_key':idempotency_key,'request_hash':request_hash,'transaction_id':transaction_id,'user_id':user['id'] if user else None,'customer':customer,'payment_method':data.payment_method,'payment_instructions':method['instructions'],'payment_status':'unpaid','status':'initiating','notes':data.notes,'marketing':data.marketing,'created_at':stamp(),'updated_at':stamp(),'history':[],'internal_notes':[],'tracking':'','tracking_source':'staff-entered','stock_released':False}
    try:await db.orders.insert_one(order.copy())
    except DuplicateKeyError:raise HTTPException(409,'Order is being processed. Please retry shortly.')
    query={'id':'main',f'reservations.{id}':{'$exists':False}}
    inc={}
    for item in amounts['items']:
        query[f"quantities.{item['variant_id']}"]={'$gte':item['quantity']}
        inc[f"quantities.{item['variant_id']}"]=-item['quantity']
    reserved=await db.inventory.update_one(query,{'$inc':inc,'$set':{f'reservations.{id}':stamp()}})
    if not reserved.modified_count:
        await db.orders.update_one({'id':id},{'$set':{'status':'failed'}})
        raise HTTPException(409,'Stock changed during checkout. Please review your bag.')
    if amounts['coupon']:
        coupon=await db.coupons.find_one_and_update({'code':amounts['coupon'],'enabled':True,'$expr':{'$lt':['$used','$max_uses']}},{'$inc':{'used':1}},{'_id':0})
        if not coupon:
            await release_inventory(order)
            await db.orders.update_one({'id':id},{'$set':{'status':'failed'}})
            raise HTTPException(409,'This coupon has just reached its limit. Try without it.')
    if amounts['points_redeemed'] or amounts['credit_discount']:
        wallet_query={'id':user['id'] if user else ''}
        if amounts['points_redeemed']:wallet_query['points']={'$gte':amounts['points_redeemed']}
        if amounts['credit_discount']:wallet_query['credit_balance']={'$gte':amounts['credit_discount']}
        wallet_inc={}
        if amounts['points_redeemed']:wallet_inc['points']=-amounts['points_redeemed']
        if amounts['credit_discount']:wallet_inc['credit_balance']=-amounts['credit_discount']
        spent=await db.users.update_one(wallet_query,{'$inc':wallet_inc})
        if not spent.modified_count:
            await release_inventory(order)
            if amounts['coupon']:await db.coupons.update_one({'code':amounts['coupon']},{'$inc':{'used':-1}})
            await db.orders.update_one({'id':id},{'$set':{'status':'failed'}})
            raise HTTPException(409,'Your points or credit balance changed. Please review your bag.')
    status='pending' if data.payment_method=='cod' else 'awaiting_payment'
    history=[{'status':status,'at':stamp(),'note':'Order placed; payment not yet collected'}]
    await db.orders.update_one({'id':id},{'$set':{'status':status,'history':history}})
    order['status']=status
    await db.stock_movements.insert_one({'id':uid(),'order_id':id,'type':'reservation','items':amounts['items'],'created_at':stamp(),'actor':'Checkout'})
    from alerts import send_alert
    await send_alert('order_placed','low',f"New order {order['number']}",f"Customer {order['customer'].get('name','')} · total {order['total']/100:.0f} BDT · payment: {data.payment_method}")
    result=confirmation(order)
    if data.payment_method not in ['cod','bank_transfer']:
        from payments import start_online_payment
        result['payment']=await start_online_payment(order,request)
    return result

async def customer_order(id,request,access):
    user=await optional_user(request)
    order=await db.orders.find_one({'id':id},{'_id':0})
    if not order:raise HTTPException(404,'Order not found')
    owned=user and order.get('user_id')==user['id']
    if not owned and not (access and hmac.compare_digest(access,access_token(order))):raise HTTPException(404,'Order not found')
    return order

@router.get('/orders/{id}',response_model=Doc)
async def read_order(id:str,request:Request,access:str=''):
    order=await customer_order(id,request,access)
    return public_order(order)

def public_order(order):
    result={k:v for k,v in order.items() if k not in ['idempotency_key','request_hash','internal_notes','user_id']}
    result['history']=[{'status':h['status'],'at':h['at'],'note':h.get('note','') if not h.get('actor') else 'Updated by the store team'} for h in order.get('history',[])]
    return result

class BankReference(Input):
    reference:str=Field(min_length=3,max_length=200)

@router.post('/orders/{id}/bank-reference',response_model=Doc)
async def bank_reference(id:str,data:BankReference,request:Request,access:str=''):
    order=await customer_order(id,request,access)
    if order['payment_method']!='bank_transfer' or order['payment_status'] not in ['unpaid','rejected']:raise HTTPException(409,'This order cannot accept a bank reference')
    await db.orders.update_one({'id':id,'payment_status':{'$in':['unpaid','rejected']}},{'$set':{'bank_reference':data.reference,'payment_status':'awaiting_review'}})
    return {'ok':True}

@router.get('/customer/orders',response_model=list[Doc])
async def my_orders(user=Depends(current_user)):
    rows=await db.orders.find({'user_id':user['id']},{'_id':0,'idempotency_key':0,'request_hash':0,'internal_notes':0}).sort('created_at',-1).to_list(200)
    return [public_order(row) for row in rows]

@router.get('/admin/orders',response_model=list[Doc])
async def orders(user=Depends(require('orders.read'))):
    return await db.orders.find({'status':{'$nin':['initiating','failed']}},{'_id':0,'idempotency_key':0,'request_hash':0}).sort('created_at',-1).to_list(1000)

class OrderUpdate(Input):
    status:Literal['pending','awaiting_payment','processing','packed','shipped','out_for_delivery','delivered','cancelled','on_hold']|None=None
    note:str=Field(default='',max_length=2000)
    tracking:str=Field(default='',max_length=200)

TRANSITIONS={'pending':['processing','cancelled','on_hold'],'awaiting_payment':['cancelled','on_hold'],'processing':['packed','cancelled','on_hold'],'packed':['shipped','cancelled','on_hold'],'shipped':['out_for_delivery','delivered','on_hold'],'out_for_delivery':['delivered','on_hold'],'on_hold':['processing','cancelled'],'delivered':[],'cancelled':[]}

@router.patch('/admin/orders/{id}',response_model=Doc)
async def update_order(id:str,data:OrderUpdate,user=Depends(require('orders.update'))):
    order=await db.orders.find_one({'id':id},{'_id':0})
    if not order:raise HTTPException(404,'Order not found')
    update={'$set':{'updated_at':stamp()}}
    if data.status and data.status!=order['status']:
        if data.status not in TRANSITIONS.get(order['status'],[]):raise HTTPException(409,'This status transition is not permitted')
        if data.status in ['processing','packed','shipped','delivered'] and order['payment_method']!='cod' and order['payment_status']!='paid':raise HTTPException(409,'Verify payment before fulfillment')
        update['$set']['status']=data.status
        update['$push']={'history':{'status':data.status,'at':stamp(),'note':data.note,'actor':user['name']}}
    if data.tracking:update['$set']['tracking']=data.tracking
    if data.note:
        update.setdefault('$push',{})['internal_notes']={'text':data.note,'at':stamp(),'actor':user['name']}
    result=await db.orders.update_one({'id':id,'status':order['status']},update)
    if not result.modified_count:raise HTTPException(409,'No change was made; reload this order')
    if data.status=='cancelled':
        await release_inventory(order)
        from alerts import send_alert
        await send_alert('order_cancelled','medium',f"Order {order['number']} cancelled",f"Cancelled by {user['name']}. Reason: {data.note or 'not given'}")
    if data.status=='delivered':await db.inventory.update_one({'id':'main'},{'$unset':{f"reservations.{id}":''}})
    if data.status:
        from accounts import loyalty_revoke
        if data.status=='cancelled':await loyalty_revoke(order)
        if order.get('user_id'):
            from notifications import notify
            await notify(order['user_id'],'order','Order '+order['number']+' updated','Your order status is now: '+data.status.replace('_',' '),'')
    await audit(user,'order.updated',id,data.status or 'note')
    return {'ok':True}

class PaymentAction(Input):
    action:Literal['confirm','reject','refund']
    note:str=Field(min_length=3,max_length=1000)

@router.post('/admin/orders/{id}/payment',response_model=Doc)
async def payment_action(id:str,data:PaymentAction,user=Depends(current_user)):
    from permissions import authorize
    await authorize(user,'payments.refund' if data.action=='refund' else 'payments.update')
    order=await db.orders.find_one({'id':id},{'_id':0})
    if not order:raise HTTPException(404,'Order not found')
    if order['payment_method'] not in ['cod','bank_transfer']:raise HTTPException(409,'Provider confirmation is required')
    if data.action=='refund' and order['payment_status']!='paid':raise HTTPException(409,'Only a collected payment can be refunded')
    if data.action in ['confirm','reject'] and (order['payment_status'] not in ['unpaid','awaiting_review','rejected'] or order['status']=='cancelled'):raise HTTPException(409,'This payment cannot be changed')
    status={'confirm':'paid','reject':'rejected','refund':'refunded'}[data.action]
    change={'payment_status':status,'updated_at':stamp()}
    if data.action=='confirm' and order['status']=='awaiting_payment':change['status']='processing'
    await db.orders.update_one({'id':id,'payment_status':order['payment_status']},{'$set':change,'$push':{'history':{'status':status,'at':stamp(),'note':data.note,'actor':user['name']}}})
    if data.action=='confirm':
        from accounts import loyalty_award
        await loyalty_award({**order,'payment_status':'paid'})
        if order.get('affiliate_code'):
            from affiliates import record_conversion
            await record_conversion(order['affiliate_code'],{**order,'payment_status':'paid'})
        if order.get('user_id'):
            from notifications import notify
            await notify(order['user_id'],'payment','Payment confirmed','Payment for '+order['number']+' was verified.','')
    if data.action=='refund':
        from accounts import loyalty_revoke
        await loyalty_revoke(order)
    await audit(user,'payment.'+data.action,id,data.note)
    return {'ok':True}