'''Steadfast Courier adapter - simple API key + secret booking.
Live docs: https://steadfast.com.bd/user/docs/api (merchant panel).
'''
import httpx
from providers.base import CourierProvider, register_courier, ProviderError, field

BASE = 'https://steadfast.com.bd/api/v1'


@register_courier
class Steadfast(CourierProvider):
    id = 'steadfast'
    label = 'Steadfast Courier'
    supports_webhook = False
    docs_url = 'https://steadfast.com.bd/'
    config_fields = [
        field('api_key', 'API key'),
        field('secret_key', 'Secret key', secret=True),
    ]
    settings_fields = []

    def headers(self, credentials):
        return {'Api-Key': credentials.get('api_key', ''), 'Secret-Key': credentials.get('secret_key', ''), 'Content-Type': 'application/json', 'Accept': 'application/json'}

    async def validate_config(self, credentials, sandbox):
        # Steadfast has no status endpoint; validate by listing a known-missing consignment
        # and expecting an authorized response rather than 401/403.
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(BASE + '/status_by_trackingcode/__probe__', headers=self.headers(credentials))
            if response.status_code in (401, 403):
                return False, 'Steadfast rejected the API key or secret.'
            return True, 'Steadfast credentials accepted.'
        except Exception as error:
            return False, f'Steadfast verification failed: {error}'

    async def create_shipment(self, order, config, credentials, parcel):
        body = {'invoice': order['transaction_id'][:40], 'recipient_name': order['customer']['name'],
                'recipient_phone': order['customer'].get('phone', ''),
                'recipient_address': f"{order['customer'].get('address', '')}, {order['customer'].get('city', '')}",
                'cod_amount': round(parcel.get('cod_amount', 0) / 100, 2),
                'note': parcel.get('description', '')[:150], 'delivery_type': parcel.get('delivery_type', 0)}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(BASE + '/create_order', json=body, headers=self.headers(credentials))
                created = response.json()
        except Exception as error:
            raise ProviderError(f'Steadfast booking failed: {error}')
        consignment = created.get('consignment', {})
        tracking = consignment.get('tracking_code', '')
        if not tracking:
            raise ProviderError(created.get('message') or 'Steadfast did not return a tracking code')
        return {'consignment_id': tracking, 'status': 'booked', 'tracking_url': 'https://steadfast.com.bd/t/' + tracking}

    async def track(self, config, credentials, consignment_id):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(BASE + '/status_by_trackingcode/' + consignment_id, headers=self.headers(credentials))
                body = response.json()
        except Exception as error:
            raise ProviderError(f'Steadfast tracking failed: {error}')
        delivery = str(body.get('delivery_status', '')).lower()
        mapped = {'delivered': 'delivered', 'returned': 'returned', 'cancelled': 'cancelled', 'in_review': 'booked', 'picked': 'picked_up'}.get(delivery, 'in_transit')
        return {'status': mapped, 'history': [{'status': delivery or 'unknown', 'at': body.get('updated_at', ''), 'note': f"Steadfast: {body.get('delivery_status', 'unknown')}"}]}

    async def cancel_shipment(self, config, credentials, consignment_id):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(BASE + '/cancel_order', json={'consignment_id': consignment_id}, headers=self.headers(credentials))
        except Exception as error:
            raise ProviderError(f'Steadfast cancellation failed: {error}')
        return {'ok': True}
