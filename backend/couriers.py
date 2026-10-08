'''Courier shipment orchestration: booking from the admin order view, tracking
synchronization, cancellation, webhooks, and courier-backed delivery zones.

A shipping zone with `courier` set to a provider id becomes a courier-backed
option at checkout: the charge comes from the courier config (`charge` field)
and booking happens when staff create the shipment.
'''
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from pymongo.errors import DuplicateKeyError
from core import db, Doc, Input, uid, stamp, now, audit
from datetime import timedelta
from auth import optional_user
from permissions import require
from commerce import customer_order
import providers
from providers import ProviderError

router = APIRouter(prefix='/api', tags=['Couriers'])
webhook_router = APIRouter(prefix='/api/webhooks/courier', tags=['Courier webhooks'])

SHIPMENT_STATUS_TO_ORDER = {'picked_up': 'shipped', 'in_transit': 'shipped', 'out_for_delivery': 'out_for_delivery', 'delivered': 'delivered'}
ORDER_TRANSITIONS = {'pending': ['processing', 'cancelled', 'on_hold'], 'awaiting_payment': ['cancelled', 'on_hold'], 'processing': ['packed', 'cancelled', 'on_hold'], 'packed': ['shipped', 'cancelled', 'on_hold'], 'shipped': ['out_for_delivery', 'delivered', 'on_hold'], 'out_for_delivery': ['delivered', 'on_hold'], 'on_hold': ['processing', 'cancelled'], 'delivered': [], 'cancelled': []}


class ShipmentRequest(Input):
    courier: str = Field(min_length=2, max_length=40)
    weight: int = Field(default=1000, ge=1, le=100000)
    description: str = Field(default='Electronics', min_length=1, max_length=200)
    cod_amount: int = Field(default=0, ge=0)
    auto_status: bool = True
    fields: dict[str, str] = Field(default_factory=dict)


@router.post('/admin/orders/{id}/shipment', response_model=Doc)
async def create_shipment(id: str, data: ShipmentRequest, user=Depends(require('couriers.update'))):
    order = await db.orders.find_one({'id': id}, {'_id': 0})
    if not order:
        raise HTTPException(404, 'Order not found')
    if order['status'] in ('cancelled', 'delivered'):
        raise HTTPException(409, 'This order cannot be shipped')
    existing = await db.shipments.find_one({'order_id': id, 'status': {'$nin': ['cancelled', 'returned']}}, {'_id': 0})
    if existing:
        raise HTTPException(409, f"Shipment {existing.get('consignment_id', existing['id'])} is already active for this order")
    config = await providers.courier_config(db, data.courier)
    if not config:
        raise HTTPException(503, 'This courier is not connected. Configure it under Couriers.')
    adapter = providers.get_adapter('courier', data.courier)
    shipment = {'id': uid(), 'order_id': id, 'order_number': order['number'], 'provider': data.courier,
                'consignment_id': '', 'status': 'booking', 'tracking_history': [], 'cod_amount': data.cod_amount,
                'parcel': {'weight': data.weight, 'description': data.description, **data.fields},
                'sandbox': config.get('sandbox', True), 'logs': [{'at': stamp(), 'note': 'Booking requested'}],
                'created_at': stamp(), 'updated_at': stamp()}
    await db.shipments.insert_one(shipment.copy())
    context = {**order, 'sandbox': config.get('sandbox', True)}
    try:
        result = await adapter.create_shipment(context, config.get('config', {}), config['unsealed'], {'weight': data.weight, 'description': data.description, 'cod_amount': data.cod_amount, **data.fields})
    except ProviderError as error:
        await db.shipments.update_one({'id': shipment['id']}, {'$set': {'status': 'failed', 'error': str(error)[:400], 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': str(error)[:300]}}})
        from alerts import send_alert
        await send_alert('courier_failed', 'high', 'Courier booking failed', f"Order {order['number']} via {data.courier}: {error}")
        raise HTTPException(502, str(error))
    await db.shipments.update_one({'id': shipment['id']}, {'$set': {'consignment_id': result.get('consignment_id', ''), 'status': result.get('status', 'booked'), 'tracking_url': result.get('tracking_url', ''), 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': f"Booked: {result.get('consignment_id', '')}"}}})
    tracking = result.get('consignment_id', '')
    await db.orders.update_one({'id': id}, {'$set': {'tracking': tracking, 'tracking_source': f"courier:{data.courier}"}})
    await audit(user, 'shipment.created', id, f"{data.courier}:{tracking}")
    moved = ''
    if data.auto_status and tracking:
        moved = await advance_order_status(order, 'shipped', user, f"Shipment booked with {data.courier} ({tracking})")
    return {'id': shipment['id'], 'consignment_id': tracking, 'tracking_url': result.get('tracking_url', ''), 'status': result.get('status', 'booked'), 'order_status': moved or order['status']}


async def advance_order_status(order, target, actor, note):
    '''FSM-safe move used by courier sync; never overrides payment guards.'''
    if target == order['status'] or target not in ORDER_TRANSITIONS.get(order['status'], []):
        return ''
    if target in ('processing', 'packed', 'shipped', 'delivered') and order['payment_method'] != 'cod' and order['payment_status'] != 'paid':
        return ''
    await db.orders.update_one({'id': order['id'], 'status': order['status']}, {'$set': {'status': target, 'updated_at': stamp()}, '$push': {'history': {'status': target, 'at': stamp(), 'note': note, 'actor': actor.get('name', 'Courier sync')}}})
    return target


@router.get('/admin/shipments', response_model=list[Doc])
async def shipments(user=Depends(require('couriers.read'))):
    return await db.shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(200)


@router.post('/admin/shipments/{id}/track', response_model=Doc)
async def track_shipment(id: str, user=Depends(require('couriers.update'))):
    shipment = await db.shipments.find_one({'id': id}, {'_id': 0})
    if not shipment:
        raise HTTPException(404, 'Shipment not found')
    if not shipment.get('consignment_id'):
        raise HTTPException(409, 'This shipment was never booked')
    config = await providers.courier_config(db, shipment['provider'])
    if not config:
        raise HTTPException(503, 'This courier is no longer connected')
    adapter = providers.get_adapter('courier', shipment['provider'])
    try:
        result = await adapter.track(config.get('config', {}), config['unsealed'], shipment['consignment_id'])
    except ProviderError as error:
        await db.shipments.update_one({'id': id}, {'$push': {'logs': {'at': stamp(), 'note': 'Track error: ' + str(error)[:250]}}})
        raise HTTPException(502, str(error))
    events = result.get('history', [])
    await db.shipments.update_one({'id': id}, {'$set': {'status': result.get('status', shipment['status']), 'tracking_history': events, 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': 'Tracked: ' + result.get('status', 'unknown')}}})
    order = await db.orders.find_one({'id': shipment['order_id']}, {'_id': 0})
    if order:
        target = SHIPMENT_STATUS_TO_ORDER.get(result.get('status', ''))
        if target:
            await advance_order_status(order, target, {'name': shipment['provider'].title() + ' sync'}, f"Courier status: {result.get('status')}")
            if target == 'delivered':
                await db.inventory.update_one({'id': 'main'}, {'$unset': {f"reservations.{shipment['order_id']}": ''}})
    return {'status': result.get('status'), 'history': events}


@router.post('/admin/shipments/{id}/cancel', response_model=Doc)
async def cancel_shipment(id: str, user=Depends(require('couriers.update'))):
    shipment = await db.shipments.find_one({'id': id}, {'_id': 0})
    if not shipment:
        raise HTTPException(404, 'Shipment not found')
    if shipment['status'] in ('cancelled', 'delivered'):
        raise HTTPException(409, 'This shipment can no longer be cancelled')
    config = await providers.courier_config(db, shipment['provider'])
    if config and shipment.get('consignment_id'):
        adapter = providers.get_adapter('courier', shipment['provider'])
        try:
            await adapter.cancel_shipment(config.get('config', {}), config['unsealed'], shipment['consignment_id'])
        except ProviderError as error:
            raise HTTPException(502, str(error))
    await db.shipments.update_one({'id': id}, {'$set': {'status': 'cancelled', 'updated_at': stamp()}, '$push': {'logs': {'at': stamp(), 'note': 'Cancelled by staff'}}})
    await audit(user, 'shipment.cancelled', shipment['order_id'], shipment.get('consignment_id', ''))
    return {'ok': True}


@router.get('/orders/{id}/shipment', response_model=Doc)
async def order_shipment(id: str, request: Request, access: str = ''):
    order = await customer_order(id, request, access)
    shipment = await db.shipments.find_one({'order_id': id, 'status': {'$nin': ['cancelled']}}, {'_id': 0, 'logs': 0}, sort=[('created_at', -1)])
    if not shipment:
        return {'shipment': None}
    return {'shipment': {'provider': shipment['provider'], 'consignment_id': shipment.get('consignment_id', ''), 'status': shipment['status'], 'tracking_history': shipment.get('tracking_history', []), 'tracking_url': shipment.get('tracking_url', '')}}


@webhook_router.post('/{provider}')
async def courier_webhook(provider: str, request: Request):
    config = await db.provider_configs.find_one({'kind': 'courier', 'provider': provider, 'status': 'connected'}, {'_id': 0})
    if not config:
        raise HTTPException(404, 'Unknown courier')
    adapter = providers.get_adapter('courier', provider)
    if not adapter:
        raise HTTPException(404, 'Unknown courier')
    payload = await request.body()
    try:
        event = await adapter.parse_webhook(payload, dict(request.headers), providers.open_credentials(config.get('credentials')))
    except ProviderError as error:
        raise HTTPException(400, str(error))
    if not event or not event.get('consignment_id'):
        return {'ok': True, 'ignored': True}
    shipment = await db.shipments.find_one({'consignment_id': event['consignment_id'], 'provider': provider}, {'_id': 0})
    if not shipment:
        return {'ok': True, 'matched': False}
    try:
        await db.webhook_events.insert_one({'id': uid(), 'provider': 'courier:' + provider, 'event_id': str(event.get('event_id') or event['consignment_id'] + ':' + str(event.get('status', '')))[:200], 'type': 'courier_status', 'payload': str(event.get('raw', ''))[:5000], 'created_at': stamp(), 'expires_at': now() + timedelta(days=30)})
    except DuplicateKeyError:
        return {'ok': True, 'duplicate': True}
    status = event.get('status', '')
    await db.shipments.update_one({'id': shipment['id']}, {'$set': {'status': status, 'updated_at': stamp()}, '$push': {'tracking_history': {'status': status, 'at': stamp(), 'note': event.get('note', 'Webhook')}}})
    order = await db.orders.find_one({'id': shipment['order_id']}, {'_id': 0})
    if order:
        target = SHIPMENT_STATUS_TO_ORDER.get(status)
        if target:
            await advance_order_status(order, target, {'name': provider.title() + ' sync'}, f"Courier webhook: {status}")
    return {'ok': True}
