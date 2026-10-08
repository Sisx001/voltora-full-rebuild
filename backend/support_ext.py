'''Support ecosystem extensions: departments, tags, canned replies, conversation
attachments (private), AI reply suggestions, and support analytics.
'''
import re
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from core import db, Input, Doc, uid, stamp, now, audit, flag
from auth import current_user
from permissions import require

router = APIRouter(prefix='/api', tags=['Support extensions'])
admin_router = APIRouter(prefix='/api/admin/support', tags=['Support extensions'])


# ---------------- departments ----------------

class Department(Input):
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default='', max_length=300)
    enabled: bool = True


@admin_router.get('/departments', response_model=list[Doc])
async def list_departments(user=Depends(require('support.read'))):
    return await db.departments.find({}, {'_id': 0}).sort('name', 1).to_list(50)


@admin_router.post('/departments', response_model=Doc)
async def create_department(data: Department, user=Depends(require('support.update'))):
    if await db.departments.find_one({'name': data.name}):
        raise HTTPException(409, 'A department with this name exists')
    row = {'id': uid(), **data.model_dump(), 'created_at': stamp()}
    await db.departments.insert_one(row.copy())
    await audit(user, 'support.department_created', row['id'], data.name)
    return row


@admin_router.delete('/departments/{id}', response_model=Doc)
async def delete_department(id: str, user=Depends(require('support.update'))):
    result = await db.departments.delete_one({'id': id})
    if not result.deleted_count:
        raise HTTPException(404, 'Department not found')
    await db.conversations.update_many({'department': id}, {'$unset': {'department': ''}})
    await audit(user, 'support.department_deleted', id)
    return {'ok': True}


# ---------------- canned replies ----------------

class CannedReply(Input):
    title: str = Field(min_length=2, max_length=80)
    text: str = Field(min_length=2, max_length=2000)


@admin_router.get('/canned', response_model=list[Doc])
async def list_canned(user=Depends(require('support.read'))):
    return await db.canned_replies.find({}, {'_id': 0}).sort('title', 1).to_list(100)


@admin_router.post('/canned', response_model=Doc)
async def create_canned(data: CannedReply, user=Depends(require('support.update'))):
    row = {'id': uid(), **data.model_dump(), 'created_at': stamp()}
    await db.canned_replies.insert_one(row.copy())
    return row


@admin_router.delete('/canned/{id}', response_model=Doc)
async def delete_canned(id: str, user=Depends(require('support.update'))):
    result = await db.canned_replies.delete_one({'id': id})
    if not result.deleted_count:
        raise HTTPException(404, 'Canned reply not found')
    return {'ok': True}


# ---------------- conversation metadata: tags + department ----------------

class ConversationMeta(Input):
    status: Literal['open', 'resolved'] = 'open'
    priority: Literal['low', 'normal', 'high'] = 'normal'
    assigned_to: str = Field(default='', max_length=80)
    department: str = Field(default='', max_length=60)
    tags: list[str] = Field(default_factory=list, max_length=8)


@admin_router.put('/{id}/meta', response_model=Doc)
async def update_meta(id: str, data: ConversationMeta, user=Depends(require('support.update'))):
    row = await db.conversations.find_one({'id': id}, {'_id': 0})
    if not row:
        raise HTTPException(404, 'Conversation not found')
    update = {**data.model_dump(), 'updated_at': stamp()}
    if data.status == 'resolved' and row.get('status') != 'resolved':
        update['resolved_at'] = stamp()
    if data.status == 'open':
        update.pop('resolved_at', None)
    await db.conversations.update_one({'id': id}, {'$set': update})
    await audit(user, 'support.meta_updated', id)
    return {'ok': True}


# ---------------- attachments ----------------

@router.post('/support/conversations/{id}/attachments', response_model=Doc)
async def upload_attachment(id: str, request: Request, user=Depends(current_user)):
    conversation = await db.conversations.find_one({'id': id}, {'_id': 0})
    if not conversation or conversation.get('user_id') != user['id']:
        raise HTTPException(404, 'Conversation not found')
    form = await request.form()
    upload = form.get('file')
    if upload is None or not hasattr(upload, 'read'):
        raise HTTPException(422, 'No image file was provided')
    raw = await upload.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, 'Attachments are limited to 5 MB')
    if await db.attachments.count_documents({'uploader':user['id']})>=20:
        raise HTTPException(413, 'Limit of 20 support attachments per account')
    from media import process_image
    from bson import Binary
    import asyncio
    content,width,height=await asyncio.to_thread(process_image,raw)
    attachment_id=uid()
    await db.attachment_blobs.insert_one({'id':attachment_id,'data':Binary(content)})
    doc={'id':attachment_id,'conversation_id':id,'uploader':user['id'],'name':str(getattr(upload,'filename','image'))[:120],'created_at':stamp()}
    await db.attachments.insert_one(doc.copy())
    await db.messages.insert_one({'id': uid(), 'conversation_id': id, 'sender': 'customer', 'name': user['name'], 'text': f'[image: {doc["name"]}]', 'attachment_id': attachment_id, 'internal': False, 'created_at': stamp()})
    await db.conversations.update_one({'id': id}, {'$set': {'updated_at': stamp()}})
    return {'id': attachment_id}


@router.get('/support/attachments/{id}')
async def read_attachment(id: str, request: Request, user=Depends(current_user)):
    doc = await db.attachments.find_one({'id': id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Attachment not found')
    conversation = await db.conversations.find_one({'id': doc['conversation_id']}, {'_id': 0, 'user_id': 1})
    is_owner = conversation and conversation.get('user_id') == user['id']
    is_staff = 'support.read' in (user.get('permissions') or [])
    if not is_owner and not is_staff:
        raise HTTPException(404, 'Attachment not found')
    blob=await db.attachment_blobs.find_one({'id':id})
    if not blob:raise HTTPException(404,'Attachment content is no longer available')
    from fastapi import Response
    return Response(content=bytes(blob['data']),media_type='image/webp',headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})


# ---------------- analytics ----------------

@admin_router.get('/analytics', response_model=Doc)
async def support_analytics(days: int = 30, user=Depends(require('support.read'))):
    await audit(user, 'support.analytics_viewed')
    cutoff = (now() - timedelta(days=min(180, max(7, days)))).isoformat()
    pipeline = [
        {'$match': {'created_at': {'$gte': cutoff}}},
        {'$group': {'_id': {'day': {'$substr': ['$created_at', 0, 10]}}, 'conversations': {'$sum': 1}, 'ai_conversations': {'$sum': {'$cond': [{'$eq': ['$mode', 'ai']}, 1, 0]}}}},
        {'$sort': {'_id.day': 1}},
    ]
    daily = await db.conversations.aggregate(pipeline).to_list(200)
    totals = {
        'open': await db.conversations.count_documents({'status': 'open', 'created_at': {'$gte': cutoff}}),
        'resolved': await db.conversations.count_documents({'status': 'resolved', 'created_at': {'$gte': cutoff}}),
        'ai_mode': await db.conversations.count_documents({'mode': 'ai', 'created_at': {'$gte': cutoff}}),
        'escalated': await db.conversations.count_documents({'mode': 'human', 'created_at': {'$gte': cutoff}}),
        'high_priority': await db.conversations.count_documents({'priority': 'high', 'status': 'open'}),
    }
    # response + resolution times from timestamps
    rows = await db.conversations.find({'created_at': {'$gte': cutoff}}, {'_id': 0, 'created_at': 1, 'first_response_at': 1, 'resolved_at': 1}).to_list(2000)
    from datetime import datetime
    def avg_minutes(pairs):
        values = []
        for start, end in pairs:
            try:
                delta = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60
                values.append(max(0, delta))
            except Exception:
                pass
        return round(sum(values) / len(values)) if values else None
    response_pairs = [(r['created_at'], r['first_response_at']) for r in rows if r.get('first_response_at')]
    resolution_pairs = [(r['created_at'], r['resolved_at']) for r in rows if r.get('resolved_at')]
    return {'daily': [{'date': d['_id']['day'], 'conversations': d['conversations'], 'ai': d['ai_conversations']} for d in daily],
            'totals': totals,
            'avg_first_response_minutes': avg_minutes(response_pairs),
            'avg_resolution_minutes': avg_minutes(resolution_pairs)}
