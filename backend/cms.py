import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, ValidationError
from core import db, Doc, Input, uid, stamp, now, digest, audit
from schemas import Page, Theme, SiteConfig
from permissions import require, authorize
from auth import current_user

router=APIRouter(prefix='/api',tags=['CMS and themes'])

async def document(id):
    from release_engine import legacy_document
    return await legacy_document(id)

async def can_edit(user,doc,action):
    await authorize(user,('theme.' if doc['kind']=='theme' else 'content.')+action)

@router.get('/pages/{slug}',response_model=Doc)
async def page(slug:str,preview:str=''):
    doc=await document('page:'+slug)
    if preview:
        if not await db.previews.find_one({'document_id':doc['id'],'token_hash':digest(preview),'expires_at':{'$gt':now()},'revoked':False}): raise HTTPException(404,'Preview has expired')
        return doc['draft']
    if not doc.get('published'): raise HTTPException(404,'Page not found')
    return doc['published']

@router.get('/admin/documents',response_model=list[Doc])
async def documents(user=Depends(require('content.read'))):
    from release_engine import state, legacy_document
    current=await state()
    return [await legacy_document('page:'+slug) for slug in current['draft']['pages']]

@router.get('/admin/documents/{doc_id}',response_model=Doc)
async def get_document(doc_id:str,user=Depends(current_user)):
    doc=await document(doc_id)
    await can_edit(user,doc,'read')
    return doc

class Save(Input):
    value:dict
    version:int=Field(ge=1)

@router.put('/admin/documents/{doc_id}',response_model=Doc)
async def save_document(doc_id:str,data:Save,user=Depends(current_user)):
    doc=await document(doc_id)
    await can_edit(user,doc,'update')
    try: value=(Theme if doc['kind']=='theme' else SiteConfig if doc['kind']=='site' else Page)(**data.value).model_dump()
    except ValidationError as e: raise HTTPException(422,str(e))
    if doc['kind']=='page' and value['slug']!=doc_id.removeprefix('page:'):
        raise HTTPException(422,'Page slug is immutable; create a new page to change its address')
    from release_engine import save_legacy
    return await save_legacy(doc_id,value,data.version)

@router.post('/admin/pages',response_model=Doc)
async def new_page(data:Page,user=Depends(require('content.update'))):
    from release_engine import state, save_legacy, legacy_document
    current=await state()
    if data.slug in current['draft']['pages']:
        raise HTTPException(409,'Page slug is already used')
    if len(current['draft']['pages'])>=80:
        raise HTTPException(422,'The workspace supports up to 80 pages')
    await save_legacy('page:'+data.slug,data.model_dump(),current['version'])
    return await legacy_document('page:'+data.slug)
    if await db.documents.find_one({'id':'page:'+data.slug}): raise HTTPException(409,'Page slug is already used')
    doc={'id':'page:'+data.slug,'kind':'page','draft':data.model_dump(),'published':None,'version':1,'updated_at':stamp()}
    await db.documents.insert_one(doc.copy())
    await audit(user,'page.created',doc['id'])
    return doc

class Publish(Input):
    version:int
    summary:str=Field(default='Published changes',max_length=240)

@router.post('/admin/documents/{doc_id}/publish',response_model=Doc)
async def publish(doc_id:str,data:Publish,user=Depends(current_user)):
    raise HTTPException(409,'Open Website builder → Publish to review and publish one atomic site release.')
    doc=await document(doc_id)
    await can_edit(user,doc,'publish')
    revision={'id':uid(),'document_id':doc_id,'value':doc['draft'],'previous':doc.get('published'),'created_at':stamp(),'author':user['name'],'summary':data.summary,'version':data.version+1}
    r=await db.documents.update_one({'id':doc_id,'version':data.version},{'$set':{'published':doc['draft'],'published_at':stamp()},'$inc':{'version':1}})
    if not r.modified_count: raise HTTPException(409,'A newer draft exists. Reload before publishing.')
    await db.revisions.insert_one(revision)
    await audit(user,'content.published',doc_id,data.summary)
    return {'version':data.version+1}

@router.get('/admin/documents/{doc_id}/revisions',response_model=list[Doc])
async def revisions(doc_id:str,user=Depends(current_user)):
    doc=await document(doc_id)
    await can_edit(user,doc,'read')
    return await db.revisions.find({'document_id':doc_id},{'_id':0}).sort('created_at',-1).to_list(100)

class Restore(Input):
    revision_id:str
    version:int

@router.post('/admin/documents/{doc_id}/restore',response_model=Doc)
async def restore(doc_id:str,data:Restore,user=Depends(current_user)):
    doc=await document(doc_id)
    await can_edit(user,doc,'update')
    rev=await db.revisions.find_one({'id':data.revision_id,'document_id':doc_id},{'_id':0})
    if not rev: raise HTTPException(404,'Revision not found')
    result=await db.documents.update_one({'id':doc_id,'version':data.version},{'$set':{'draft':rev['value']},'$inc':{'version':1}})
    if not result.modified_count: raise HTTPException(409,'A newer draft exists')
    await audit(user,'content.revision_restored',doc_id)
    return {'version':data.version+1,'draft':rev['value']}

@router.post('/admin/documents/{doc_id}/discard',response_model=Doc)
async def discard(doc_id:str,data:Publish,user=Depends(current_user)):
    doc=await document(doc_id)
    await can_edit(user,doc,'update')
    if not doc.get('published'): raise HTTPException(409,'This page has never been published')
    result=await db.documents.update_one({'id':doc_id,'version':data.version},{'$set':{'draft':doc['published']},'$inc':{'version':1}})
    if not result.modified_count: raise HTTPException(409,'A newer draft exists')
    return {'version':data.version+1,'draft':doc['published']}

@router.post('/admin/documents/{doc_id}/preview',response_model=Doc)
async def preview(doc_id:str,user=Depends(current_user)):
    doc=await document(doc_id)
    await can_edit(user,doc,'read')
    token=secrets.token_urlsafe(32)
    id=uid()
    await db.previews.insert_one({'id':id,'document_id':doc_id,'token_hash':digest(token),'expires_at':now()+timedelta(minutes=30),'revoked':False})
    path='/' if doc_id in ['theme','page:home','site'] else '/pages/'+doc_id.removeprefix('page:')
    return {'token':token,'id':id,'path':path,'expires_in':1800}

@router.delete('/admin/previews/{id}',response_model=Doc)
async def revoke(id:str,user=Depends(current_user)):
    preview=await db.previews.find_one({'id':id},{'_id':0})
    if not preview: raise HTTPException(404,'Preview not found')
    await can_edit(user,await document(preview['document_id']),'update')
    await db.previews.update_one({'id':id},{'$set':{'revoked':True}})
    return {'ok':True}

@router.get('/admin/themes',response_model=list[Doc])
async def themes(user=Depends(require('theme.read'))):
    return await db.themes.find({},{'_id':0}).to_list(100)

@router.post('/admin/themes',response_model=Doc)
async def custom_theme(data:Theme,user=Depends(require('theme.update'))):
    value=data.model_dump()
    value['id']='custom-'+uid()
    await db.themes.insert_one(value.copy())
    await audit(user,'theme.created',value['id'])
    return value