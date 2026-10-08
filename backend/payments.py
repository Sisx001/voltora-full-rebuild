'''Online payment orchestration: transactions, gateway return verification,
authoritative webhooks, refunds, and the admin transaction log.

Money flows: checkout -> adapter.initiate (redirect) -> customer pays on the
provider -> either (a) the storefront posts the return params to
/api/orders/{id}/payment/verify or (b) the provider calls the webhook. Both
paths are idempotent; the order is never marked paid from a return page alone.
'''
import os
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import Field
from pymongo.errors import DuplicateKeyError
from core import db, Doc, Input, uid, stamp, now, audit
from auth import optional_user, current_user
from permissions import require
import providers
from providers import ProviderError
from commerce import customer_order, access_token

router = APIRouter(prefix='/api', tags=['Payments'])
webhook_router = APIRouter(prefix='/api/webhooks/payment', tags=['Payment webhooks'])


async def latest_transaction(order_id):
    return await db.payment_transactions.find_one({'order_id': order_id}, {'_id': 0}, sort=[('created_at', -1)])


async def mark_paid(order_id, note):
    '''Authoritative payment success. Idempotent; moves awaiting_payment -> processing.'''
    order = await db.orders.find_one({'id': order_id}, {'_id': 0})
    if not order or order.get('payment_status') in ('paid', 'refunded'):
        return False
    change = {'payment_status': 'paid', 'updated_at': stamp()}
    if order.get('status') == 'awaiting_payment':
        change['status'] = 'processing'
    await db.orders.update_one({'id': order_id, 'payment_status': {'$nin': ['paid', 'refunded']}}, {'$set': change, '$push': {'history': {'status': 'paid', 'at': stamp(), 'note': note}}})
    try:
        from accounts import loyalty_award
        await loyalty_award({**order, 'payment_status': 'paid'})
        if order.get('affiliate_code'):
            from affiliates import record_conversion
            await record_conversion(order['affiliate_code'], {**order, 'payment_status': 'paid'})
        if order.get('user_id'):
            from notifications import notify
            await notify(order['user_id'], 'payment', 'Payment confirmed', 'Payment for ' + order['number'] + ' was confirmed by the provider.', '')
    except Exception:
        pass
    return True


async def start_online_payment(order, request):
    '''Create a transaction and ask the provider for a payment session.'''
    method_id = order['payment_method']
    config = await providers.payment_config(db, method_id)
    if not config:
        raise HTTPException(503, 'This payment provider is not connected. Choose another method.')
    adapter = providers.get_adapter('payment', config['provider'])
    if not adapter:
        raise HTTPException(503, 'The payment provider is unavailable')
    existing = await db.payment_transactions.find_one({'order_id': order['id'], 'status': 'pending'}, {'_id': 0}, sort=[('created_at', -1)])
    if existing and existing.get('redirect_url'):
        return {'transaction_id': existing['id'], 'redirect_url': existing['redirect_url'], 'provider': existing['provider']}
    origin = os.environ['APP_ORIGIN'].rstrip('/')
    return_url = f"{origin}/order/{order['id']}?access={access_token(order)}&payment=return&tx={order['transaction_id']}"
    cancel_url = f"{origin}/checkout?payment_cancelled={order['number']}"
    webhook_url = f"{origin}/api/webhooks/payment/{config['provider']}"
    transaction = {'id': order['transaction_id'], 'order_id': order['id'], 'order_number': order['number'], 'provider': config['provider'], 'method_id': method_id,
                   'amount': order['total'], 'currency': order['currency'], 'status': 'initiated', 'provider_ref': '', 'provider_config': config.get('config', {}),
                   'sandbox': config.get('sandbox', True), 'logs': [{'at': stamp(), 'note': 'Payment session requested'}], 'created_at': stamp(), 'updated_at': stamp()}
    await db.payment_transactions.insert_one(transaction.copy())
    context = {**order, 'sandbox': config.get('sandbox', True)}
    try:
        result = await adapter.initiate(context, config.get('config', {}), config['unsealed'], return_url, cancel_url, webhook_url)
    except ProviderError as error:
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'failed', 'error': str(error)[:400], 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': str(error)[:300]}}})
        await db.orders.update_one({'id': order['id']}, {'$set': {'payment_error': str(error)[:300]}})
        from alerts import send_alert
        await send_alert('payment_failed', 'high', 'Payment initiation failed', f"Order {order['number']} ({config['provider']}): {error}")
        raise HTTPException(502, str(error))
    update = {'$set': {'status': 'pending', 'updated_at': stamp(), 'redirect_url': result.get('redirect_url', '')}, '$push': {'logs': {'at': stamp(), 'note': 'Redirect issued'}}}
    if result.get('payment_id'):
        update['$set']['provider_ref'] = result['payment_id']
    if result.get('session_id'):
        update['$set']['provider_ref'] = result['session_id']
    if result.get('paypal_order_id'):
        update['$set']['provider_ref'] = result['paypal_order_id']
    await db.payment_transactions.update_one({'id': transaction['id']}, update)
    return {'transaction_id': transaction['id'], 'redirect_url': result.get('redirect_url', ''), 'provider': config['provider']}


class VerifyBody(Input):
    params: dict[str, str] = Field(default_factory=dict)


@router.post('/orders/{id}/payment/verify', response_model=Doc)
async def verify_payment(id: str, data: VerifyBody, request: Request, access: str = ''):
    order = await customer_order(id, request, access)
    if order['payment_method'] in ('cod', 'bank_transfer'):
        raise HTTPException(409, 'This order does not use an online payment method')
    if order['payment_status'] == 'paid':
        return {'status': 'paid'}
    transaction = await db.payment_transactions.find_one({'id': (data.params.get('tx') or '').strip(), 'order_id': id}, {'_id': 0}) or \
        await db.payment_transactions.find_one({'order_id': id, 'status': {'$in': ['pending', 'initiated']}}, {'_id': 0}, sort=[('created_at', -1)])
    if not transaction:
        raise HTTPException(409, 'No pending payment session exists for this order. Start checkout again.')
    config = await providers.payment_config(db, order['payment_method'])
    if not config or config['provider'] != transaction['provider']:
        raise HTTPException(503, 'The payment provider for this order is not currently connected')
    adapter = providers.get_adapter('payment', transaction['provider'])
    try:
        outcome = await adapter.verify({**transaction, 'sandbox': transaction.get('sandbox', True)}, config['unsealed'], data.params)
    except ProviderError as error:
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$push': {'logs': {'at': stamp(), 'note': 'Verify error: ' + str(error)[:250]}}, '$set': {'updated_at': stamp()}})
        raise HTTPException(502, str(error))
    if outcome == 'paid':
        await mark_paid(id, f"Payment confirmed via {config['provider']}")
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'paid', 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': 'Verified after provider return'}}})
        await audit({'id': order.get('user_id') or 'guest', 'name': order['customer']['name']}, 'payment.verified', id, transaction['provider'])
        return {'status': 'paid'}
    if outcome == 'failed':
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'failed', 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': 'Provider reported failure'}}})
        return {'status': 'failed'}
    return {'status': 'pending'}


@webhook_router.post('/{provider}')
async def payment_webhook(provider: str, request: Request):
    payload = await request.body()
    config = await db.provider_configs.find_one({'kind': 'payment', 'provider': provider, 'status': 'connected'}, {'_id': 0})
    if not config:
        raise HTTPException(404, 'Unknown payment provider')
    adapter = providers.get_adapter('payment', provider)
    if not adapter:
        raise HTTPException(404, 'Unknown payment provider')
    try:
        event = await adapter.parse_webhook(payload, dict(request.headers), providers.open_credentials(config.get('credentials')))
    except ProviderError as error:
        raise HTTPException(400, str(error))
    if not event:
        return {'ok': True, 'ignored': True}
    try:
        await db.webhook_events.insert_one({'id': uid(), 'provider': 'payment:' + provider, 'event_id': str(event.get('event_id', ''))[:200], 'type': str(event.get('type', ''))[:100], 'payload': str(event.get('raw', ''))[:5000], 'created_at': stamp(), 'expires_at': now() + timedelta(days=30)})
    except DuplicateKeyError:
        return {'ok': True, 'duplicate': True}
    query = {'id': event.get('reference', '')} if event.get('reference') else {'provider_ref': event.get('session_id', event.get('capture_id', ''))}
    transaction = await db.payment_transactions.find_one({**query, 'provider': provider}, {'_id': 0}) or \
        await db.payment_transactions.find_one({**query}, {'_id': 0})
    if not transaction:
        return {'ok': True, 'matched': False}
    status = event.get('status', '')
    if status == 'paid':
        if event.get('capture_id'):
            await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'provider_capture_id': event['capture_id'], 'updated_at': stamp()}})
        changed = await mark_paid(transaction['order_id'], f'Payment confirmed by {provider} webhook')
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'paid', 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': f'Webhook {event.get("type", "")} marked paid'}}})
        return {'ok': True, 'applied': changed}
    if status == 'failed':
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'failed', 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': f'Webhook reported failure'}}})
        return {'ok': True, 'applied': True}
    if status == 'refunded':
        await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'refunded', 'updated_at': stamp()}})
        await db.orders.update_one({'id': transaction['order_id'], 'payment_status': 'paid'}, {'$set': {'payment_status': 'refunded', 'updated_at': stamp()}, '$push': {'history': {'status': 'refunded', 'at': stamp(), 'note': 'Refund confirmed by provider'}}})
        return {'ok': True, 'applied': True}
    return {'ok': True, 'applied': False}


class RefundBody(Input):
    amount: int = Field(default=0, ge=0)
    note: str = Field(min_length=3, max_length=1000)


@router.post('/admin/orders/{id}/refund', response_model=Doc)
async def refund_online(id: str, data: RefundBody, user=Depends(require('payments.refund'))):
    order = await db.orders.find_one({'id': id}, {'_id': 0})
    if not order:
        raise HTTPException(404, 'Order not found')
    if order['payment_method'] in ('cod', 'bank_transfer'):
        raise HTTPException(409, 'Record COD and bank-transfer refunds from the payment action panel')
    if order['payment_status'] != 'paid':
        raise HTTPException(409, 'Only a collected payment can be refunded')
    transaction = await latest_transaction(id)
    if not transaction or transaction['status'] != 'paid':
        raise HTTPException(409, 'No settled payment transaction exists for this order')
    config = await providers.payment_config(db, order['payment_method'])
    if not config:
        raise HTTPException(503, 'The payment provider is not connected; refund manually in the provider panel')
    adapter = providers.get_adapter('payment', transaction['provider'])
    amount = data.amount if data.amount else order['total']
    if amount > order['total']:
        raise HTTPException(422, 'The refund cannot exceed the order total')
    try:
        result = await adapter.refund({**transaction, 'sandbox': transaction.get('sandbox', True)}, config['unsealed'], amount)
    except ProviderError as error:
        raise HTTPException(502, str(error))
    full = amount >= order['total']
    await db.orders.update_one({'id': id, 'payment_status': 'paid'}, {'$set': {'payment_status': 'refunded' if full else 'paid', 'updated_at': stamp()}, '$push': {'history': {'status': 'refunded', 'at': stamp(), 'note': f"Refund issued via {config['provider']}: {data.note}", 'actor': user['name']}}})
    try:
        from accounts import loyalty_revoke
        await loyalty_revoke(order)
    except Exception:
        pass
    await db.payment_transactions.update_one({'id': transaction['id']}, {'$set': {'status': 'refunded' if full else 'partially_refunded', 'refunded_amount': amount, 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': 'Refund issued: ' + str(result)}}})
    await audit(user, 'payment.refunded', id, f"{amount} via {config['provider']}: {data.note}")
    return {'ok': True}


@router.get('/admin/transactions', response_model=list[Doc])
async def transactions(provider: str = '', status: Literal['initiated', 'pending', 'paid', 'failed', 'refunded', 'partially_refunded'] | None = None, user=Depends(require('payments.read'))):
    query = {}
    if provider:
        query['provider'] = provider
    if status:
        query['status'] = status
    return await db.payment_transactions.find(query, {'_id': 0, 'provider_config': 0}).sort('created_at', -1).to_list(200)
