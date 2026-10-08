import re
from datetime import timedelta
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import Field
from pymongo.errors import DuplicateKeyError
from core import db, Doc, Input, settings, flag, stamp, uid, audit, digest, now
from schemas import Product
from auth import current_user
from permissions import require

router=APIRouter(prefix='/api',tags=['Catalog'])

async def enrich(products):
    inventory=await db.inventory.find_one({'id':'main'},{'_id':0,'quantities':1}) or {}
    quantities=inventory.get('quantities',{})
    for p in products:
        p['stock']=sum(quantities.get(v['id'],0) for v in p['variants'])
        for v in p['variants']:
            v['stock']=quantities.get(v['id'],0)
        reviews=await db.reviews.find({'product_id':p['id'],'status':'published'},{'_id':0,'rating':1}).to_list(1000)
        p['review_count']=len(reviews)
        p['rating']=round(sum(r['rating'] for r in reviews)/len(reviews),1) if reviews else None
    return products

@router.get('/store',response_model=Doc)
async def store(preview:str='',theme_preview:str=''):
    s=await settings()
    from release_engine import live_release, legacy_document
    release=await live_release()
    bundle=release['bundle']
    output={'settings':s,'theme':bundle['theme'],'home':bundle['pages']['home'],'site':bundle['site'],'preview':False,'revision_id':release['id']}
    if preview:
        token=await db.previews.find_one({'token_hash':digest(preview),'expires_at':{'$gt':now()},'revoked':False},{'_id':0})
        if not token: raise HTTPException(404,'This preview has expired or was revoked')
        doc=await legacy_document(token['document_id'])
        output['preview']=True
        if doc['kind']=='theme':
            output['theme']=doc['draft']
            # industry flows change theme + homepage together: preview both drafts
            home_doc=await db.documents.find_one({'id':'page:home'},{'_id':0,'draft':1})
            if home_doc: output['home']=home_doc['draft']
        elif doc['id']=='page:home': output['home']=doc['draft']
        elif doc['id']=='site': output['site']=doc['draft']
    if theme_preview:
        preset=await db.themes.find_one({'id':theme_preview},{'_id':0})
        if not preset:raise HTTPException(404,'Theme not found')
        output['theme']=preset
        output['preview']=True
        # Structural header/footer values must follow the preset rather than live overrides.
        if output.get('site'):
            output['site']['header']['layout']=preset['header_style']
            output['site']['footer']['style']=preset['footer_style']
    # Unconfigured online adapters are never advertised as available.
    import providers
    connected=set()
    for row in await providers.active_payment_methods(db):
        connected.update(row.get('method_ids',[]))
    for p in s['payments']:
        online=p['id'] not in ['cod','bank_transfer']
        p['available']=p['enabled'] and ((p['id']=='cod' and s['features']['cod']) or (p['id']=='bank_transfer' and s['features']['bank_transfer'] and bool(p['instructions'].strip())) or (online and s['features'].get('online_payments',False) and p['id'] in connected))
        p['status']='ready' if p['available'] else ('connected' if online and p['id'] in connected else ('not_configured' if online else 'disabled'))
    output['categories']=await db.categories.find({'enabled':True},{'_id':0}).sort('position',1).to_list(200)
    output['brands']=await db.brands.find({'enabled':{'$ne':False}},{'_id':0}).to_list(100)
    return output

@router.get('/products',response_model=Doc)
async def products(q:str=Query('',max_length=150),category:str='',brand:str='',sort:str='featured',min_price:int=0,max_price:int=1000000000,in_stock:bool=False,ids:str='',page:int=Query(1,ge=1),limit:int=Query(12,ge=1,le=100)):
    query={'published':True}
    if q:
        if not await flag('search'): raise HTTPException(403,'Search is currently unavailable')
        regex={'$regex':re.escape(q),'$options':'i'}
        query['$or']=[{f:regex} for f in ['name','sku','brand','category','description']]
    if category: query['category']=category
    if brand: query['brand']=brand
    if ids: query['id']={'$in':ids.split(',')[:100]}
    query['price']={'$gte':min_price,'$lte':max_price}
    if in_stock:
        inv=await db.inventory.find_one({'id':'main'},{'_id':0,'quantities':1}) or {}
        query['variants.id']={'$in':[k for k,v in inv.get('quantities',{}).items() if v>0]}
    sorting={'price_asc':[('price',1)],'price_desc':[('price',-1)],'newest':[('created_at',-1)],'name':[('name',1)]}.get(sort,[('featured',-1),('id',1)])
    total=await db.products.count_documents(query)
    rows=await db.products.find(query,{'_id':0}).sort(sorting).skip((page-1)*limit).limit(limit).to_list(limit)
    return {'items':await enrich(rows),'total':total,'page':page,'pages':max(1,(total+limit-1)//limit)}

@router.get('/products/{slug}',response_model=Doc)
async def product(slug:str):
    row=await db.products.find_one({'slug':slug,'published':True},{'_id':0})
    if not row: raise HTTPException(404,'Product not found')
    return (await enrich([row]))[0]

@router.get('/products/{product_id}/reviews',response_model=list[Doc])
async def reviews(product_id:str):
    if not await flag('reviews'): return []
    return await db.reviews.find({'product_id':product_id,'status':'published'},{'_id':0,'user_id':0}).sort('created_at',-1).to_list(100)

class Review(Input):
    rating:int=Field(ge=1,le=5)
    text:str=Field(min_length=10,max_length=3000)

@router.post('/products/{product_id}/reviews',response_model=Doc)
async def review(product_id:str,data:Review,user=Depends(current_user)):
    if not await flag('reviews'): raise HTTPException(403,'Reviews are unavailable')
    if not await db.products.find_one({'id':product_id,'published':True}): raise HTTPException(404,'Product not found')
    purchased=bool(await db.orders.find_one({'user_id':user['id'],'items.product_id':product_id,'status':'delivered'}))
    try:
        await db.reviews.insert_one({'id':uid(),'product_id':product_id,'user_id':user['id'],'name':user['name'],'verified':purchased,'status':'pending','created_at':stamp(),**data.model_dump()})
    except DuplicateKeyError: raise HTTPException(409,'You have already reviewed this product')
    return {'message':'Your review has been submitted for moderation'}

@router.get('/admin/products',response_model=list[Doc])
async def admin_products(user=Depends(require('products.read'))):
    return await enrich(await db.products.find({},{'_id':0}).sort('updated_at',-1).to_list(1000))

@router.get('/admin/products/{product_id}/draft',response_model=Doc)
async def product_draft(product_id:str,user=Depends(require('products.read'))):
    draft=await db.product_drafts.find_one({'id':product_id},{'_id':0})
    if not draft: raise HTTPException(404,'Product not found')
    return draft

class ProductSave(Input):
    value:Product
    version:int=Field(ge=0)

@router.post('/admin/products',response_model=Doc)
async def create_product(data:Product,user=Depends(require('products.update'))):
    id=uid()
    row={**data.model_dump(),'id':id,'published':False,'version':1,'created_at':stamp(),'updated_at':stamp()}
    try: await db.products.insert_one(row.copy())
    except DuplicateKeyError: raise HTTPException(409,'Slug or SKU is already used')
    await db.product_drafts.insert_one({'id':id,'value':data.model_dump(),'version':1})
    updates={f'quantities.{v.id}':0 for v in data.variants}
    await db.inventory.update_one({'id':'main'},{'$set':updates},upsert=True)
    await audit(user,'product.created',id)
    return {'id':id,'version':1}

@router.put('/admin/products/{product_id}/draft',response_model=Doc)
async def save_product(product_id:str,data:ProductSave,user=Depends(require('products.update'))):
    r=await db.product_drafts.update_one({'id':product_id,'version':data.version},{'$set':{'value':data.value.model_dump()},'$inc':{'version':1}})
    if not r.modified_count: raise HTTPException(409,'Another editor changed this product. Reload before saving.')
    await audit(user,'product.draft_saved',product_id)
    return {'version':data.version+1}

@router.post('/admin/products/{product_id}/publish',response_model=Doc)
async def publish_product(product_id:str,user=Depends(require('products.publish'))):
    draft=await db.product_drafts.find_one({'id':product_id},{'_id':0})
    if not draft: raise HTTPException(404,'Product not found')
    old=await db.products.find_one({'id':product_id},{'_id':0})
    try:
        await db.products.update_one({'id':product_id},{'$set':{**draft['value'],'published':True,'updated_at':stamp(),'version':draft['version']}})
    except DuplicateKeyError: raise HTTPException(409,'Slug or SKU is already used')
    await db.revisions.insert_one({'id':uid(),'document_id':'product:'+product_id,'value':old,'created_at':stamp(),'author':user['name'],'summary':'Product published'})
    await audit(user,'product.published',product_id)
    return {'ok':True}

@router.delete('/admin/products/{product_id}',response_model=Doc)
async def archive_product(product_id:str,user=Depends(require('products.update'))):
    await db.products.update_one({'id':product_id},{'$set':{'published':False,'updated_at':stamp()}})
    await audit(user,'product.archived',product_id)
    return {'ok':True}