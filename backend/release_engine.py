"""Immutable presentation bundles; a single CAS is the publication commit point.

Commerce records, customers, sessions and carts are never part of a release.
Candidates are inserted before the active pointer changes. Uncommitted candidates
are not exposed by public reads/history. Rollback creates a new immutable release.
"""
from copy import deepcopy
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from core import db, Input, Doc, stamp, uid
from schemas import Theme, SiteConfig, Page
from permissions import require, authorize

router = APIRouter(prefix='/api/admin/builder', tags=['Atomic site releases'])

class Bundle(Input):
    theme: Theme
    site: SiteConfig
    pages: dict[str, Page] = Field(max_length=80)

    @field_validator('pages')
    @classmethod
    def validate_pages(cls, pages):
        if 'home' not in pages or any(k != p.slug for k, p in pages.items()):
            raise ValueError('A home page and matching page slugs are required')
        return pages

class SaveBundle(Input):
    version: int = Field(ge=1)
    bundle: Bundle

class PublishBundle(Input):
    version: int = Field(ge=1)
    summary: str = Field(default='Published website changes', min_length=3, max_length=240)

class RestoreBundle(PublishBundle):
    revision_id: str = Field(min_length=1, max_length=80)

async def initialize_releases():
    await db.site_workspace.create_index('id', unique=True)
    await db.site_releases.create_index('id', unique=True)
    if await db.site_workspace.find_one({'id':'store'}, {'_id':1}):
        return
    docs = await db.documents.find({}, {'_id':0}).to_list(100)
    by_id = {d['id']:d for d in docs}
    bundle = Bundle(theme=by_id['theme']['published'], site=by_id['site']['published'] or by_id['site']['draft'],
                    pages={d['published']['slug']:d['published'] for d in docs if d['kind']=='page' and d.get('published')}).model_dump()
    rid = uid()
    release = {'id':rid, 'bundle':bundle, 'created_at':stamp(), 'author':'VOLTORA', 'summary':'Initial storefront', 'kind':'initial'}
    await db.site_releases.insert_one(deepcopy(release))
    await db.site_workspace.update_one({'id':'store'}, {'$setOnInsert':{'id':'store','version':1,'draft':bundle,
        'active_revision':rid,'history':[rid],'updated_at':stamp(),'published_at':stamp()}}, upsert=True)

async def state():
    value = await db.site_workspace.find_one({'id':'store'}, {'_id':0})
    if not value:
        raise HTTPException(503, 'The website workspace is initializing. Please retry shortly.')
    return value

async def live_release():
    current = await state()
    release = await db.site_releases.find_one({'id':current['active_revision']}, {'_id':0})
    if not release:
        raise HTTPException(503, 'The active website release is unavailable. Contact the owner.')
    return release

def document_key(doc_id):
    if doc_id in ('theme','site'):
        return doc_id
    if doc_id.startswith('page:'):
        slug=doc_id[5:]
        import re
        if re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            return 'pages.'+slug
    raise HTTPException(404, 'Unknown document')

def bundle_document(bundle, doc_id):
    return bundle.get(doc_id) if doc_id in ('site','theme') else bundle['pages'].get(doc_id[5:])

async def legacy_document(doc_id):
    current=await state()
    live=await db.site_releases.find_one({'id':current['active_revision']}, {'_id':0,'bundle':1})
    draft=bundle_document(current['draft'], doc_id)
    if draft is None:
        raise HTTPException(404,'Document not found')
    return {'id':doc_id,'kind':doc_id if doc_id in ('site','theme') else 'page','draft':draft,
            'published':bundle_document(live['bundle'],doc_id), 'version':current['version'],'updated_at':current['updated_at']}

async def save_legacy(doc_id, value, version):
    key=document_key(doc_id)
    result=await db.site_workspace.update_one({'id':'store','version':version},
        {'$set':{'draft.'+key:value,'updated_at':stamp()},'$inc':{'version':1}})
    if not result.modified_count:
        raise HTTPException(409,'A newer draft exists. Reload or export your local changes before retrying.')
    return {'version':version+1}

@router.get('', response_model=Doc)
async def get_builder(user=Depends(require('content.read'))):
    current=await state()
    live=await db.site_releases.find_one({'id':current['active_revision']}, {'_id':0})
    return {**current,'live':live,'external_actions':False}

@router.put('', response_model=Doc)
async def save_builder(data:SaveBundle, user=Depends(require('content.update'))):
    await authorize(user,'theme.update')
    bundle=data.bundle.model_dump()
    result=await db.site_workspace.update_one({'id':'store','version':data.version},
        {'$set':{'draft':bundle,'updated_at':stamp()},'$inc':{'version':1}})
    if not result.modified_count:
        raise HTTPException(409,'A newer draft was saved in another session. Export your local changes, then load the latest draft.')
    return {'version':data.version+1,'saved_at':stamp()}

async def commit(bundle, current, user, summary, kind, source=None):
    validated=Bundle(**bundle).model_dump()
    release={'id':uid(),'bundle':validated,'created_at':stamp(),'author':user['name'],
             'summary':summary,'kind':kind,'source_revision':source}
    await db.site_releases.insert_one(deepcopy(release))
    # Only this operation changes what visitors see. Failure leaves the old pointer intact.
    result=await db.site_workspace.update_one({'id':'store','version':current['version'],'active_revision':current['active_revision']},
        {'$set':{'active_revision':release['id'],'published_at':release['created_at']},
         '$inc':{'version':1},'$push':{'history':release['id']}})
    if not result.modified_count:
        raise HTTPException(409,'The workspace changed during publication. The candidate was not activated. Review the latest draft.')
    return {'version':current['version']+1,'revision_id':release['id'],'published_at':release['created_at']}

@router.post('/publish', response_model=Doc)
async def publish_builder(data:PublishBundle, user=Depends(require('content.publish'))):
    await authorize(user,'theme.publish')
    current=await state()
    if data.version!=current['version']:
        raise HTTPException(409,'A newer draft exists. Review it before publishing.')
    if (await live_release())['bundle']==current['draft']:
        raise HTTPException(409,'There are no unpublished changes.')
    return await commit(current['draft'],current,user,data.summary,'publish')

@router.get('/revisions', response_model=list[Doc])
async def revisions(user=Depends(require('content.read'))):
    current=await state()
    return await db.site_releases.find({'id':{'$in':current['history']}}, {'_id':0,'bundle':0}).sort('created_at',-1).to_list(200)

@router.get('/revisions/{revision_id}', response_model=Doc)
async def revision(revision_id:str,user=Depends(require('content.read'))):
    current=await state()
    if revision_id not in current['history']:
        raise HTTPException(404,'Published revision not found')
    return await db.site_releases.find_one({'id':revision_id}, {'_id':0})

@router.post('/restore', response_model=Doc)
async def restore(data:RestoreBundle,user=Depends(require('content.update'))):
    await authorize(user,'theme.update')
    old=await revision(data.revision_id,user)
    result=await db.site_workspace.update_one({'id':'store','version':data.version},
        {'$set':{'draft':old['bundle'],'updated_at':stamp()},'$inc':{'version':1}})
    if not result.modified_count:
        raise HTTPException(409,'A newer draft exists. Reload before restoring.')
    return {'version':data.version+1,'draft':old['bundle']}

@router.post('/rollback', response_model=Doc)
async def rollback(data:RestoreBundle,user=Depends(require('content.publish'))):
    await authorize(user,'theme.publish')
    old=await revision(data.revision_id,user)
    current=await state()
    if current['version']!=data.version:
        raise HTTPException(409,'The workspace changed. Review before rolling back.')
    return await commit(old['bundle'],current,user,data.summary,'rollback',old['id'])