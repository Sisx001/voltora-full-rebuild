'''One-page offer pages (/offer/<code>) + per-page analytics.

The owner generates a dedicated, standalone shareable page for one product:
own layout, own CTA, optional coupon/countdown/trust sections, inline
streamlined checkout (variant -> quantity -> address -> payment -> done).
Tracks views, CTA clicks, checkouts and purchases per page (hashed visitor,
30-day retention). Optionally attributes orders to an affiliate code.

Server-side rules are absolute: product price, stock, coupon validity and
totals are revalidated at checkout exactly like the main store.'''
import os
import hmac
import hashlib
import json
import secrets
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import Field, EmailStr
from pymongo.errors import DuplicateKeyError
from core import db, Input, Doc, uid, stamp, now, audit, settings, flag, digest
from auth import optional_user
from permissions import require
from commerce import calculate, release_inventory, confirmation, access_token, zone_matches
from schemas import Address
import providers

router = APIRouter(prefix='/api', tags=['Offer pages'])
admin_router = APIRouter(prefix='/api/admin/offers', tags=['Offer pages'])

CODE_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'


def new_code():
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(6))


async def get_offer(code: str):
    offer = await db.offer_pages.find_one({'code': code.lower(), 'active': True}, {'_id': 0})
    if not offer:
        raise HTTPException(404, 'This offer page does not exist or is no longer active')
    return offer


# ---------------- admin CRUD ----------------

class OfferSave(Input):
    product_id: str = Field(min_length=1, max_length=80)
    variant_id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=2, max_length=180)
    subtitle: str = Field(default='', max_length=300)
    description: str = Field(default='', max_length=5000)
    coupon: str = Field(default='', max_length=80)
    cta_text: str = Field(default='Order now', min_length=2, max_length=60)
    layout: Literal['product_first', 'checkout_first'] = 'product_first'
    countdown_ends_at: str = Field(default='', max_length=30)
    show_trust: bool = True
    show_faq: bool = True
    show_warranty: bool = True
    show_returns: bool = True
    affiliate_code: str = Field(default='', max_length=40)
    active: bool = True


@admin_router.get('', response_model=list[Doc])
async def list_offers(user=Depends(require('marketing.read'))):
    rows = await db.offer_pages.find({}, {'_id': 0}).sort('created_at', -1).to_list(200)
    counts = {}
    for r in await db.offer_events.aggregate([
        {'$group': {'_id': {'offer': '$offer_id', 'event': '$event'}, 'count': {'$sum': 1}}}
    ]).to_list(500):
        counts[(r['_id']['offer'], r['_id']['event'])] = r['count']
    for row in rows:
        row['views'] = counts.get((row['id'], 'view'), 0)
        row['orders'] = counts.get((row['id'], 'purchase'), 0)
        if not row.get('active') and row.get('paused_reason'):
            row['status_note'] = row['paused_reason']
    return rows


@admin_router.post('', response_model=Doc)
async def create_offer(data: OfferSave, user=Depends(require('marketing.update'))):
    product = await db.products.find_one({'id': data.product_id, 'published': True}, {'_id': 0})
    if not product or not any(v['id'] == data.variant_id for v in product['variants']):
        raise HTTPException(422, 'Select a published product variant')
    if data.coupon and not await db.coupons.find_one({'code': data.coupon.upper(), 'enabled': True}):
        raise HTTPException(422, 'That coupon does not exist or is disabled')
    for attempt in range(6):
        code = new_code()
        if not await db.offer_pages.find_one({'code': code}):
            break
    row = {'id': uid(), 'code': code, **data.model_dump(), 'views': 0, 'created_at': stamp(), 'updated_at': stamp()}
    await db.offer_pages.insert_one(row.copy())
    await audit(user, 'offer.created', row['id'], f"{code} -> {product['name']}")
    return row


@admin_router.put('/{id}', response_model=Doc)
async def update_offer(id: str, data: OfferSave, user=Depends(require('marketing.update'))):
    row = await db.offer_pages.find_one({'id': id}, {'_id': 0})
    if not row:
        raise HTTPException(404, 'Offer not found')
    await db.offer_pages.update_one({'id': id}, {'$set': {**data.model_dump(), 'updated_at': stamp()}})
    await audit(user, 'offer.updated', id)
    return {'ok': True}


@admin_router.delete('/{id}', response_model=Doc)
async def delete_offer(id: str, user=Depends(require('marketing.update'))):
    result = await db.offer_pages.delete_one({'id': id})
    if not result.deleted_count:
        raise HTTPException(404, 'Offer not found')
    await audit(user, 'offer.deleted', id)
    return {'ok': True}


@admin_router.get('/{id}/analytics', response_model=Doc)
async def offer_analytics(id: str, user=Depends(require('marketing.read'))):
    offer = await db.offer_pages.find_one({'id': id}, {'_id': 0})
    if not offer:
        raise HTTPException(404, 'Offer not found')
    by_event = {r['_id']: r['count'] for r in await db.offer_events.aggregate([
        {'$match': {'offer_id': id}},
        {'$group': {'_id': '$event', 'count': {'$sum': 1}}},
    ]).to_list(20)}
    uniques = len(await db.offer_events.distinct('visitor', {'offer_id': id}))
    devices = await db.offer_events.aggregate([
        {'$match': {'offer_id': id, 'event': 'view'}},
        {'$group': {'_id': '$device', 'count': {'$sum': 1}}}, {'$sort': {'count': -1}},
    ]).to_list(6)
    daily = await db.offer_events.aggregate([
        {'$match': {'offer_id': id}},
        {'$group': {'_id': {'day': {'$substr': ['$created_at', 0, 10]}, 'event': '$event'}, 'count': {'$sum': 1}}},
    ]).to_list(200)
    days = {}
    for d in daily:
        days.setdefault(d['_id']['day'], {'date': d['_id']['day'], 'views': 0, 'purchases': 0})
        if d['_id']['event'] == 'view':
            days[d['_id']['day']]['views'] += d['count']
        if d['_id']['event'] == 'purchase':
            days[d['_id']['day']]['purchases'] += d['count']
    views, purchases = by_event.get('view', 0), by_event.get('purchase', 0)
    return {'offer': {'code': offer['code'], 'title': offer['title']},
            'views': views, 'cta_clicks': by_event.get('click_cta', 0), 'checkouts': by_event.get('begin_checkout', 0),
            'purchases': purchases, 'unique_visitors': uniques,
            'conversion_rate': round(purchases / views * 100, 1) if views else 0,
            'devices': [{'device': d['_id'] or 'unknown', 'count': d['count']} for d in devices],
            'daily': sorted(days.values(), key=lambda x: x['date'])}


# ---------------- public page ----------------

@router.get('/offer/{code}', response_model=Doc)
async def offer_page(code: str, ref: str = ''):
    offer = await get_offer(code)
    product = await db.products.find_one({'id': offer['product_id'], 'published': True}, {'_id': 0})
    if not product:
        raise HTTPException(404, 'The product for this offer is no longer available')
    config = await settings()
    variant = next((v for v in product['variants'] if v['id'] == offer['variant_id']), product['variants'][0])
    inv = await db.inventory.find_one({'id': 'main'}, {'_id': 0, 'quantities': 1}) or {}
    stock = inv.get('quantities', {}).get(variant['id'], 0)
    connected_methods = set()
    for row in await providers.active_payment_methods(db):
        connected_methods.update(row.get('method_ids', []))
    payments = [{'id': p['id'], 'label': p['label'], 'available': p['enabled'] and ((p['id'] == 'cod' and config['features']['cod']) or (p['id'] == 'bank_transfer' and config['features']['bank_transfer']) or (p['id'] not in ('cod', 'bank_transfer') and config['features'].get('online_payments', False) and p['id'] in connected_methods))} for p in config['payments']]
    shipping = [s for s in config['shipping'] if s.get('enabled')]
    return {'offer': {k: offer.get(k, '') for k in ['code', 'title', 'subtitle', 'description', 'coupon', 'cta_text', 'layout', 'countdown_ends_at', 'show_trust', 'show_faq', 'show_warranty', 'show_returns', 'affiliate_code']},
            'product': {'id': product['id'], 'name': product['name'], 'slug': product['slug'], 'image': product['images'][0] if product['images'] else '', 'images': product['images'][:4], 'specs': product.get('specs', {}), 'warranty': product.get('warranty', '')},
            'variant': {'id': variant['id'], 'options': variant['options'], 'price': variant['price'], 'stock': stock},
            'shipping': shipping, 'payments': payments,
            'currency': 'BDT', 'store': {'brand': config['brand'], 'announcement': config.get('announcement', '')}}


class OfferTrack(Input):
    event: Literal['view', 'click_cta', 'begin_checkout', 'purchase']
    visitor_id: str = Field(pattern=r'^[a-zA-Z0-9-]{8,80}$')
    referrer: str = Field(default='', max_length=300)


@router.post('/offer/{code}/track', response_model=Doc)
async def offer_track(code: str, data: OfferTrack):
    offer = await db.offer_pages.find_one({'code': code.lower(), 'active': True}, {'_id': 0, 'id': 1})
    if not offer:
        return {'recorded': False}
    await db.offer_events.insert_one({'id': uid(), 'offer_id': offer['id'], 'event': data.event,
                                      'visitor': digest(data.visitor_id)[:24], 'referrer': data.referrer[:300],
                                      'created_at': stamp(),
                                      'expires_at': now() + timedelta(days=30)})
    return {'recorded': True}


class OfferCheckout(Input):
    variant_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(ge=1, le=50)
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=25)
    address: str = Field(min_length=5, max_length=500)
    city: str = Field(min_length=2, max_length=100)
    postal_code: str = Field(default='', max_length=20)
    location: Address | None = None
    shipping_id: str = Field(default='dhaka', max_length=40)
    payment_method: Literal['cod', 'bank_transfer', 'stripe', 'sslcommerz', 'bkash', 'nagad', 'rocket', 'upay', 'paypal', 'mock']
    notes: str = Field(default='', max_length=1000)
    terms: bool
    ref: str = Field(default='', max_length=40)


@router.post('/offer/{code}/checkout', response_model=Doc)
async def offer_checkout(code: str, data: OfferCheckout, request: Request, idempotency_key: str = Header(..., min_length=16, max_length=100)):
    offer = await get_offer(code)
    config = await settings()
    if config['mode'] != 'live':
        raise HTTPException(503, 'The store is not accepting orders right now')
    if not data.terms:
        raise HTTPException(422, 'Please accept the terms to place an order')
    product = await db.products.find_one({'id': offer['product_id'], 'published': True}, {'_id': 0})
    if not product:
        raise HTTPException(404, 'This product is no longer available')
    variant = next((v for v in product['variants'] if v['id'] == data.variant_id), None)
    if not variant:
        raise HTTPException(409, 'That variant is no longer available')

    prior = await db.orders.find_one({'idempotency_key': idempotency_key}, {'_id': 0})
    if prior:
        if prior['request_hash'] != digest(json.dumps(data.model_dump(), sort_keys=True)):
            raise HTTPException(409, 'This checkout key was already used with different details')
        return confirmation(prior)

    coupon = offer.get('coupon', '')
    quote_data = type('Q', (), {'items': [type('L', (), {'product_id': product['id'], 'variant_id': variant['id'], 'quantity': data.quantity, 'expected_price': variant['price']})()],
                                'shipping_id': data.shipping_id, 'coupon': coupon, 'location': data.location,
                                'redeem_points': 0, 'use_credit': False})()
    try:
        amounts, config = await calculate(quote_data)
    except HTTPException:
        raise

    method = next((p for p in config['payments'] if p['id'] == data.payment_method and p['enabled']), None)
    if not method:
        raise HTTPException(400, 'This payment method is unavailable')
    if data.payment_method not in ('cod', 'bank_transfer'):
        import providers as _p
        if not await _p.payment_config(db, data.payment_method):
            raise HTTPException(503, 'This payment provider is not connected. Choose another method.')
    if not method['min_amount'] <= amounts['total'] <= method['max_amount']:
        raise HTTPException(400, 'Order total is outside this payment method’s limits')

    affiliate_code = (data.ref or offer.get('affiliate_code', '')).strip()[:40]
    if affiliate_code and not await db.affiliates.find_one({'code': affiliate_code.upper(), 'status': 'active'}):
        affiliate_code = ''

    order_id = uid()
    transaction_id = 'tx' + uid()[:16]
    location_data = {}
    customer = {'name': data.name, 'email': data.email, 'phone': data.phone, 'address': data.address, 'city': data.city, 'postal_code': data.postal_code}
    if data.location:
        from commerce import location_snapshot
        location_data = await location_snapshot(data.location)
        if location_data:
            customer['location'] = location_data
    order = {**amounts, 'id': order_id, 'number': 'VT-' + order_id[:8].upper(), 'idempotency_key': idempotency_key,
             'request_hash': digest(json.dumps(data.model_dump(), sort_keys=True)), 'transaction_id': transaction_id,
             'user_id': None, 'customer': customer, 'payment_method': data.payment_method,
             'payment_instructions': method['instructions'], 'payment_status': 'unpaid', 'status': 'initiating',
             'notes': data.notes, 'marketing': False, 'source': 'offer', 'offer_id': offer['id'], 'offer_code': offer['code'],
             'affiliate_code': affiliate_code,
             'created_at': stamp(), 'updated_at': stamp(), 'history': [], 'internal_notes': [],
             'tracking': '', 'tracking_source': 'staff-entered', 'stock_released': False}
    try:
        await db.orders.insert_one(order.copy())
    except DuplicateKeyError:
        raise HTTPException(409, 'Order is being processed. Please retry shortly.')

    query = {'id': 'main', f"reservations.{order_id}": {'$exists': False}, f"quantities.{variant['id']}": {'$gte': data.quantity}}
    reserved = await db.inventory.update_one(query, {'$inc': {f"quantities.{variant['id']}": -data.quantity}, '$set': {f"reservations.{order_id}": stamp()}})
    if not reserved.modified_count:
        await db.orders.update_one({'id': order_id}, {'$set': {'status': 'failed'}})
        raise HTTPException(409, 'Stock changed during checkout. Please try again.')

    if amounts['coupon']:
        coupon_row = await db.coupons.find_one_and_update({'code': amounts['coupon'], 'enabled': True, '$expr': {'$lt': ['$used', '$max_uses']}}, {'$inc': {'used': 1}}, {'_id': 0})
        if not coupon_row:
            await release_inventory(order)
            await db.orders.update_one({'id': order_id}, {'$set': {'status': 'failed'}})
            raise HTTPException(409, 'The offer coupon just reached its limit.')

    status = 'pending' if data.payment_method == 'cod' else 'awaiting_payment'
    await db.orders.update_one({'id': order_id}, {'$set': {'status': status, 'history': [{'status': status, 'at': stamp(), 'note': 'Order placed via offer page' + (f' (ref {affiliate_code})' if affiliate_code else '')}]}})
    order['status'] = status
    await db.stock_movements.insert_one({'id': uid(), 'order_id': order_id, 'type': 'reservation', 'items': amounts['items'], 'created_at': stamp(), 'actor': f"Offer:{offer['code']}"})
    await db.offer_events.insert_one({'id': uid(), 'offer_id': offer['id'], 'event': 'purchase', 'visitor': '', 'referrer': '', 'created_at': stamp(), 'expires_at': now() + timedelta(days=30)})
    result = confirmation(order)
    if data.payment_method not in ('cod', 'bank_transfer'):
        from payments import start_online_payment
        result['payment'] = await start_online_payment(order, request)
    return result
