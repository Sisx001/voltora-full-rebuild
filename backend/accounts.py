'''Customer account extensions: loyalty points, store credit, return requests,
and self-service avatars.

Loyalty model: points are earned on PAID order totals (loyalty_earn_rate points
per 100 BDT) and are worth loyalty_point_poisha each at checkout; redemption is
capped at half the item net. Store credit is a poisha balance issued by staff
(or as a return resolution) and spendable at checkout. Both move atomically.
'''
import os
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from pymongo.errors import DuplicateKeyError
from core import db, Input, Doc, uid, stamp, now, audit, settings, flag
from auth import current_user, optional_user
from permissions import require
import providers
from commerce import customer_order
from datetime import datetime, timezone

router = APIRouter(prefix='/api', tags=['Accounts'])
admin_router = APIRouter(prefix='/api/admin', tags=['Accounts'])


def _expires(days):
    return datetime.fromtimestamp(now().timestamp() + days * 86400, timezone.utc)


async def user_wallet(user_id):
    row = await db.users.find_one({'id': user_id}, {'_id': 0, 'points': 1, 'credit_balance': 1})
    return {'points': (row or {}).get('points', 0), 'credit': (row or {}).get('credit_balance', 0)}


async def loyalty_award(order):
    '''Award points for a paid order (idempotent via ledger unique order event).'''
    config = await settings()
    if not config['features'].get('loyalty', False) or not order.get('user_id'):
        return
    rate = config.get('loyalty_earn_rate', 1)
    if rate <= 0:
        return
    points = int(order['total'] / 100 / 100 * rate)
    if points <= 0:
        return
    event_id = f"earn:{order['id']}"
    if await db.loyalty_ledger.find_one({'event_id': event_id}):
        return
    await db.loyalty_ledger.insert_one({'id': uid(), 'event_id': event_id, 'user_id': order['user_id'], 'delta': points, 'reason': f"Order {order['number']} paid", 'created_at': stamp()})
    await db.users.update_one({'id': order['user_id']}, {'$inc': {'points': points}})


async def loyalty_revoke(order):
    if not order.get('user_id'):
        return
    event_id = f"earn:{order['id']}"
    entry = await db.loyalty_ledger.find_one({'event_id': event_id}, {'_id': 0})
    if not entry:
        return
    if await db.loyalty_ledger.find_one({'event_id': 'revoke:' + order['id']}):
        return
    await db.loyalty_ledger.insert_one({'id': uid(), 'event_id': 'revoke:' + order['id'], 'user_id': order['user_id'], 'delta': -entry['delta'], 'reason': f"Order {order['number']} refunded", 'created_at': stamp()})
    await db.users.update_one({'id': order['user_id']}, {'$inc': {'points': -entry['delta']}})


# ---------- wallet endpoints ----------

@router.get('/customer/wallet', response_model=Doc)
async def wallet(user=Depends(current_user)):
    balance = await user_wallet(user['id'])
    history = await db.loyalty_ledger.find({'user_id': user['id']}, {'_id': 0}).sort('created_at', -1).to_list(30)
    return {**balance, 'history': history}


@router.get('/customer/credit', response_model=Doc)
async def credit_history(user=Depends(current_user)):
    rows = await db.credit_ledger.find({'user_id': user['id']}, {'_id': 0}).sort('created_at', -1).to_list(50)
    return {'balance': await user_wallet(user['id']), 'history': rows}


# ---------- admin: balances + adjustments ----------

@admin_router.get('/loyalty', response_model=list[Doc])
async def loyalty_list(user=Depends(require('loyalty.read'))):
    return await db.users.find({'role': 'customer', '$or': [{'points': {'$gt': 0}}, {'credit_balance': {'$gt': 0}}]}, {'_id': 0, 'id': 1, 'name': 1, 'email': 1, 'points': 1, 'credit_balance': 1}).sort('points', -1).to_list(200)


class WalletAdjust(Input):
    user_id: str = Field(min_length=1, max_length=80)
    points: int = Field(default=0, ge=-1000000, le=1000000)
    credit: int = Field(default=0, ge=-100000000, le=100000000)
    note: str = Field(min_length=3, max_length=300)


@admin_router.post('/loyalty/adjust', response_model=Doc)
async def loyalty_adjust(data: WalletAdjust, user=Depends(require('loyalty.update'))):
    target = await db.users.find_one({'id': data.user_id}, {'_id': 0, 'id': 1, 'points': 1, 'credit_balance': 1})
    if not target:
        raise HTTPException(404, 'Customer not found')
    if data.points:
        await db.loyalty_ledger.insert_one({'id': uid(), 'user_id': data.user_id, 'delta': data.points, 'reason': 'Staff adjustment: ' + data.note, 'created_at': stamp()})
    if data.credit:
        await db.credit_ledger.insert_one({'id': uid(), 'user_id': data.user_id, 'delta': data.credit, 'reason': 'Staff adjustment: ' + data.note, 'created_at': stamp()})
    inc = {}
    if data.points:
        inc['points'] = data.points
    if data.credit:
        inc['credit_balance'] = data.credit
    if inc:
        result = await db.users.find_one_and_update({'id': data.user_id, **({f'points': {'$gte': -data.points}} if data.points < 0 else {}), **({'credit_balance': {'$gte': -data.credit}} if data.credit < 0 else {})}, {'$inc': inc}, return_document=True)
        if not result:
            raise HTTPException(409, 'The adjustment would make the balance negative')
    await audit(user, 'loyalty.adjusted', data.user_id, f"points={data.points} credit={data.credit}: {data.note}")
    return {'ok': True}


# ---------- returns / RMA ----------

class ReturnRequest(Input):
    items: list[str] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=5, max_length=1000)


@router.post('/orders/{id}/return', response_model=Doc)
async def request_return(id: str, data: ReturnRequest, request: Request, access: str = ''):
    if not await flag('returns'):
        raise HTTPException(403, 'Return requests are currently unavailable')
    order = await customer_order(id, request, access)
    if order['status'] not in ('delivered', 'shipped', 'out_for_delivery'):
        raise HTTPException(409, 'Only delivered or shipped orders can start a return')
    if await db.return_requests.find_one({'order_id': id, 'status': {'$in': ['requested', 'approved', 'received']}}):
        raise HTTPException(409, 'A return request already exists for this order')
    valid_items = [i['variant_id'] for i in order['items']]
    unknown = [x for x in data.items if x not in valid_items]
    if unknown:
        raise HTTPException(422, 'Some items are not part of this order')
    row = {'id': uid(), 'order_id': id, 'order_number': order['number'], 'user_id': order.get('user_id'),
           'email': order['customer']['email'], 'items': data.items, 'reason': data.reason,
           'status': 'requested', 'resolution': '', 'note': '', 'created_at': stamp(), 'updated_at': stamp()}
    await db.return_requests.insert_one(row.copy())
    await audit({'id': order.get('user_id') or 'guest', 'name': order['customer']['name']}, 'return.requested', id, data.reason[:200])
    from alerts import send_alert
    await send_alert('return_requested', 'low', f"Return requested on {order['number']}", f"{len(data.items)} item(s). Reason: {data.reason[:200]}")
    return row


@router.get('/customer/returns', response_model=list[Doc])
async def my_returns(user=Depends(current_user)):
    return await db.return_requests.find({'user_id': user['id']}, {'_id': 0}).sort('created_at', -1).to_list(50)


@admin_router.get('/returns', response_model=list[Doc])
async def returns_list(user=Depends(require('returns.read'))):
    return await db.return_requests.find({}, {'_id': 0}).sort('created_at', -1).to_list(200)


class ReturnUpdate(Input):
    status: Literal['requested', 'approved', 'rejected', 'received', 'refunded', 'credited']
    note: str = Field(default='', max_length=500)


@admin_router.put('/returns/{id}', response_model=Doc)
async def return_update(id: str, data: ReturnUpdate, user=Depends(require('returns.update'))):
    row = await db.return_requests.find_one({'id': id}, {'_id': 0})
    if not row:
        raise HTTPException(404, 'Return request not found')
    await db.return_requests.update_one({'id': id}, {'$set': {'status': data.status, 'note': data.note, 'updated_at': stamp()}})
    order = await db.orders.find_one({'id': row['order_id']}, {'_id': 0})
    if data.status in ('refunded', 'credited') and order:
        if data.status == 'credited' and order.get('user_id'):
            await db.credit_ledger.insert_one({'id': uid(), 'user_id': order['user_id'], 'delta': order['total'], 'reason': f"Return credit for {order['number']}", 'created_at': stamp()})
            await db.users.update_one({'id': order['user_id']}, {'$inc': {'credit_balance': order['total']}})
            await loyalty_revoke(order)
        if data.status == 'refunded':
            await db.orders.update_one({'id': order['id'], 'payment_status': 'paid'}, {'$set': {'payment_status': 'refunded', 'updated_at': stamp()}, '$push': {'history': {'status': 'refunded', 'at': stamp(), 'note': 'Return refund: ' + data.note}}})
            await loyalty_revoke(order)
        await db.orders.update_one({'id': order['id']}, {'$push': {'history': {'status': order['status'], 'at': stamp(), 'note': f'Return {data.status}: {data.note}'}}})
        if order.get('user_id'):
            from notifications import notify
            await notify(order['user_id'], 'return', f'Return {data.status}', f"Your return for {order['number']} was {data.status}.", '/account')
    await audit(user, 'return.updated', id, f"{data.status}: {data.note}"[:200])
    return {'ok': True}


# ---------- moderation: ban / suspension ----------

class BanInput(Input):
    reason: str = Field(min_length=3, max_length=500)
    days: int = Field(default=0, ge=0, le=3650, description='0 = permanent')
    notify_user: bool = True


@admin_router.post('/customers/{id}/ban', response_model=Doc)
async def ban_customer(id: str, data: BanInput, user=Depends(require('customers.update'))):
    target = await db.users.find_one({'id': id, 'role': 'customer'}, {'_id': 0})
    if not target:
        raise HTTPException(404, 'Customer not found')
    from datetime import datetime, timezone
    until = ''
    if data.days > 0:
        until = datetime.fromtimestamp(now().timestamp() + data.days * 86400, timezone.utc).isoformat()
    ban = {'active': True, 'reason': data.reason[:500], 'days': data.days, 'until': until,
           'banned_at': stamp(), 'banned_by': user['id']}
    await db.users.update_one({'id': id}, {'$set': {'ban': ban}})
    await db.sessions.delete_many({'user_id': id})
    await audit(user, 'customer.banned', id, f'{data.reason} ({data.days or "permanent"} days)')
    if data.notify_user and target.get('email'):
        from notifications import send_email, TEMPLATES
        subject, body = TEMPLATES.get('account_suspended', ('Account suspended', 'Your account has been suspended.'))
        await send_email(target['email'], subject, body, {'reason': data.reason})
    return {'ok': True, 'ban': ban}


@admin_router.post('/customers/{id}/unban', response_model=Doc)
async def unban_customer(id: str, user=Depends(require('customers.update'))):
    result = await db.users.update_one({'id': id, 'role': 'customer'}, {'$set': {'ban.active': False}, '$unset': {'ban.reason': '', 'ban.until': ''}})
    if not result.matched_count:
        raise HTTPException(404, 'Customer not found')
    await audit(user, 'customer.unbanned', id)
    return {'ok': True}


@admin_router.get('/customers/{id}/timeline', response_model=Doc)
async def customer_timeline(id: str, user=Depends(require('customers.read'))):
    target = await db.users.find_one({'id': id}, {'_id': 0, 'email': 1, 'name': 1, 'created_at': 1, 'ban': 1, 'phone': 1})
    if not target:
        raise HTTPException(404, 'Customer not found')
    items = [{'at': target.get('created_at', ''), 'kind': 'account', 'text': 'Account created'}]
    for o in await db.orders.find({'user_id': id}, {'_id': 0, 'id': 1, 'number': 1, 'status': 1, 'payment_status': 1, 'total': 1, 'created_at': 1}).sort('created_at', -1).to_list(50):
        items.append({'at': o['created_at'], 'kind': 'order', 'text': f"Order {o['number']} — {o['status']} ({o['payment_status']})", 'ref': o['id']})
    for h in await db.login_history.find({'user_id': id}, {'_id': 0, 'created_at': 1, 'success': 1, 'method': 1, 'ip': 1}).sort('created_at', -1).to_list(30):
        items.append({'at': h.get('created_at', ''), 'kind': 'login', 'text': ('Sign-in' if h.get('success') else 'Failed sign-in') + f" via {h.get('method', '?')}"})
    for r in await db.return_requests.find({'user_id': id}, {'_id': 0, 'order_number': 1, 'status': 1, 'created_at': 1}).sort('created_at', -1).to_list(20):
        items.append({'at': r['created_at'], 'kind': 'return', 'text': f"Return for {r.get('order_number', '?')} — {r['status']}"})
    for c in await db.conversations.find({'user_id': id}, {'_id': 0, 'subject': 1, 'status': 1, 'created_at': 1}).sort('created_at', -1).to_list(20):
        items.append({'at': c['created_at'], 'kind': 'support', 'text': f"Support: {c.get('subject', '')[:60]} ({c.get('status', '')})"})
    items.sort(key=lambda x: x.get('at', ''), reverse=True)
    return {'customer': target, 'timeline': items[:80], 'note': 'Merged from real records. Consent-gated activity events are not linked to accounts.'}


# ---------- notification center ----------

@router.get('/notifications', response_model=Doc)
async def notifications(user=Depends(current_user)):
    from notifications import user_notifications
    rows = await user_notifications(user['id'])
    return {'items': rows, 'unread': sum(1 for r in rows if not r.get('read'))}


@router.post('/notifications/{id}/read', response_model=Doc)
async def notification_read(id: str, user=Depends(current_user)):
    await db.notifications.update_one({'id': id, 'user_id': user['id']}, {'$set': {'read': True}})
    return {'ok': True}


@router.post('/notifications/read-all', response_model=Doc)
async def notifications_read_all(user=Depends(current_user)):
    await db.notifications.update_many({'user_id': user['id'], 'read': False}, {'$set': {'read': True}})
    return {'ok': True}


# ---------- avatar ----------

@router.post('/customer/avatar', response_model=Doc)
async def upload_avatar(request: Request, user=Depends(current_user)):
    from PIL import Image
    import io
    content_type = request.headers.get('content-type', '')
    if 'multipart/form-data' not in content_type:
        raise HTTPException(422, 'Upload the image as multipart form data')
    form = await request.form()
    upload = form.get('file')
    if upload is None or not hasattr(upload, 'read'):
        raise HTTPException(422, 'No image file was provided')
    raw = await upload.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(413, 'Avatars are limited to 2 MB')
    from media import store_image
    doc = await store_image(raw,'Profile image',user['name']+' profile image','Avatars',user)
    await db.users.update_one({'id': user['id']}, {'$set': {'avatar': doc['url']}})
    return {'url': doc['url']}
