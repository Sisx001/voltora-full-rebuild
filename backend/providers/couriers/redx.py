'''RedX Courier adapter - token-based open API.
Sandbox: https://open-api-stage.redx.com.bd/v1.0.0, live: https://open-api.redx.com.bd/v1.0.0.
Requires a pickup location id (configured in the RedX merchant panel).
'''
import httpx
from providers.base import CourierProvider, register_courier, ProviderError, field

SANDBOX = 'https://open-api-stage.redx.com.bd/v1.0.0'
LIVE = 'https://open-api.redx.com.bd/v1.0.0'


@register_courier
class RedX(CourierProvider):
    id = 'redx'
    label = 'RedX Courier'
    supports_webhook = False
    docs_url = 'https://redx.com.bd/'
    config_fields = [
        field('api_token', 'API token', secret=True),
    ]
    settings_fields = [
        field('pickup_area_id', 'Pickup location ID (from RedX panel)', placeholder='12345'),
    ]

    def base(self, sandbox):
        return SANDBOX if sandbox else LIVE

    def headers(self, credentials):
        return {'API-TOKEN': credentials.get('api_token', ''), 'Content-Type': 'application/json', 'Accept': 'application/json'}

    async def validate_config(self, credentials, sandbox):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(self.base(sandbox) + '/pickup-address', headers=self.headers(credentials))
            if response.status_code in (401, 403):
                return False, 'RedX rejected the API token.'
            response.raise_for_status()
            return True, 'RedX token verified (pickup locations reachable).'
        except Exception as error:
            return False, f'RedX verification failed: {error}'

    async def create_shipment(self, order, config, credentials, parcel):
        if not config.get('pickup_area_id'):
            raise ProviderError('Configure a RedX pickup location ID before booking shipments')
        body = {'pickup_area_id': int(config['pickup_area_id']),
                'customer_name': order['customer']['name'], 'customer_phone': order['customer'].get('phone', ''),
                'customer_area_id': int(parcel['customer_area_id']) if parcel.get('customer_area_id') else None,
                'customer_address': f"{order['customer'].get('address', '')}, {order['customer'].get('city', '')}",
                'weight': parcel.get('weight') or 1000, 'invoice_id': order['transaction_id'][:40],
                'cash_collection_amount': round(parcel.get('cod_amount', 0) / 100, 2),
                'parcel_detail': parcel.get('description', 'Electronics')[:100],
                'is_insured': bool(parcel.get('insured', False)), 'delivery_type': parcel.get('delivery_type', 0)}
        body = {k: v for k, v in body.items() if v is not None}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.base(order.get('sandbox', True)) + '/parcels', json=body, headers=self.headers(credentials))
                created = response.json()
        except Exception as error:
            raise ProviderError(f'RedX booking failed: {error}')
        tracking = str(created.get('tracking_id', '') or created.get('parcel_id', ''))
        if not tracking:
            raise ProviderError(created.get('message', created.get('detail', '')) or 'RedX did not return a parcel id')
        return {'consignment_id': tracking, 'status': 'booked', 'tracking_url': 'https://redx.com.bd/track-parcel/?tracking_id=' + tracking}

    async def track(self, config, credentials, consignment_id):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(self.base(True) + f'/parcels/{consignment_id}/track', headers=self.headers(credentials))
                body = response.json()
        except Exception as error:
            raise ProviderError(f'RedX tracking failed: {error}')
        events = body.get('tracking', body if isinstance(body, list) else [])
        status = str((events[-1] if events else {}).get('parcel_status', body.get('parcel_status', ''))).lower() if isinstance(events, list) else 'in_transit'
        mapped = {'delivered': 'delivered', 'returned': 'returned', 'cancelled': 'cancelled', 'picked_up': 'picked_up'}.get(status, 'in_transit')
        history = [{'status': e.get('parcel_status', ''), 'at': e.get('created_at', ''), 'note': e.get('parcel_status', '')} for e in (events if isinstance(events, list) else [])][-10:]
        return {'status': mapped, 'history': history or [{'status': status, 'at': '', 'note': 'RedX status'}]}

    async def cancel_shipment(self, config, credentials, consignment_id):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await client.post(self.base(True) + f'/parcels/{consignment_id}/cancel', headers=self.headers(credentials))
        except Exception as error:
            raise ProviderError(f'RedX cancellation failed: {error}')
        return {'ok': True}
