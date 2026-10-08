'''Pathao Courier (Hermes API) adapter. OAuth password grant, then order booking
against a configured store. City/zone/area ids are Pathao's own service-area
numbers - provide defaults in settings and override per shipment if needed.
Live docs: https://courier.pathao.com (merchant panel) / developer docs.
'''
import httpx
from providers.base import CourierProvider, register_courier, ProviderError, field

SANDBOX = 'https://hermes-api.p-stageenv.xyz'
LIVE = 'https://api-hermes.pathao.com'


@register_courier
class Pathao(CourierProvider):
    id = 'pathao'
    label = 'Pathao Courier'
    supports_webhook = False  # status pulled via track (webhook events are manual)
    docs_url = 'https://pathao.com/bn/courier/'
    config_fields = [
        field('client_id', 'Client ID'),
        field('client_secret', 'Client secret', secret=True),
        field('username', 'API username (email)', secret=True),
        field('password', 'API password', secret=True),
    ]
    settings_fields = [
        field('store_id', 'Store ID (numeric)', placeholder='12345'),
        field('default_city_id', 'Default city ID', required=False, placeholder='1'),
        field('default_zone_id', 'Default zone ID', required=False, placeholder='253'),
        field('default_area_id', 'Default area ID', required=False, placeholder='456'),
    ]

    def base(self, sandbox):
        return SANDBOX if sandbox else LIVE

    async def token(self, client, base, credentials):
        response = await client.post(base + '/oauth/token', json={'client_id': credentials.get('client_id', ''), 'client_secret': credentials.get('client_secret', ''), 'username': credentials.get('username', ''), 'password': credentials.get('password', ''), 'grant_type': 'password'})
        body = response.json()
        token = body.get('access_token', '')
        if not token:
            raise ProviderError(body.get('message') or 'Pathao rejected the API credentials')
        return token

    async def validate_config(self, credentials, sandbox):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await self.token(client, self.base(sandbox), credentials)
            return True, 'Pathao credentials verified (token granted).'
        except ProviderError as error:
            return False, str(error)
        except Exception as error:
            return False, f'Pathao verification failed: {error}'

    async def create_shipment(self, order, config, credentials, parcel):
        base = self.base(order.get('sandbox', True))
        if not config.get('store_id'):
            raise ProviderError('Configure a Pathao store ID before booking shipments')
        body = {'store_id': int(config['store_id']), 'merchant_order_id': order['transaction_id'][:60],
                'recipient_name': order['customer']['name'], 'recipient_phone': order['customer'].get('phone', ''),
                'recipient_address': f"{order['customer'].get('address', '')}, {order['customer'].get('city', '')}",
                'delivery_type': parcel.get('delivery_type', 48), 'item_type': parcel.get('item_type', 2),
                'item_quantity': sum(i['quantity'] for i in order['items']),
                'item_weight': parcel.get('weight') or 1, 'item_desc': parcel.get('description', '')[:200],
                'amount_to_collect': int(parcel.get('cod_amount', 0))}
        for src, dst in [('city_id', 'default_city_id'), ('zone_id', 'default_zone_id'), ('area_id', 'default_area_id')]:
            value = parcel.get(src) or config.get(dst)
            if value:
                body[f'recipient_{src}'] = int(value)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self.token(client, base, credentials)
                response = await client.post(base + '/aladdin/api/v1/orders', json=body, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                created = response.json()
        except Exception as error:
            raise ProviderError(f'Pathao booking failed: {error}')
        data = created.get('data', created)
        consignment = data.get('consignment_id', '')
        if not consignment:
            raise ProviderError(created.get('message') or 'Pathao did not return a consignment id')
        return {'consignment_id': consignment, 'status': 'picked_up' if data.get('delivery_status') in ('Accepted', 'Picked_Up') else 'booked', 'tracking_url': ''}

    async def track(self, config, credentials, consignment_id):
        base = 'https://api-hermes.pathao.com' if consignment_id else ''
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token = await self.token(client, base, credentials)
                response = await client.get(base + '/aladdin/api/v1/orders/' + consignment_id, headers={'Authorization': 'Bearer ' + token})
                body = response.json()
        except Exception as error:
            raise ProviderError(f'Pathao tracking failed: {error}')
        data = body.get('data', {})
        status = str(data.get('delivery_status', '')).lower()
        mapped = {'delivered': 'delivered', 'returned': 'returned', 'cancelled': 'cancelled', 'picked_up': 'picked_up', 'in_transit': 'in_transit'}.get(status, 'in_transit')
        return {'status': mapped, 'history': [{'status': status or 'unknown', 'at': data.get('updated_at', ''), 'note': f"Pathao: {data.get('delivery_status', 'unknown')}"}]}

    async def cancel_shipment(self, config, credentials, consignment_id):
        base = 'https://api-hermes.pathao.com'
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token = await self.token(client, base, credentials)
                response = await client.post(base + f"/aladdin/api/v1/orders/{consignment_id}/cancel", headers={'Authorization': 'Bearer ' + token})
        except Exception as error:
            raise ProviderError(f'Pathao cancellation failed: {error}')
        return {'ok': True}
