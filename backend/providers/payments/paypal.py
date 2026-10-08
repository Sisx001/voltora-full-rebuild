'''PayPal Orders v2 adapter. PayPal does not settle in BDT, so the store converts
the BDT total using an owner-maintained rate before creating the order - the
converted amount is recorded on the transaction for the receipt trail.
'''
import base64
import httpx
from providers.base import PaymentProvider, register_payment, ProviderError, field, setting

SANDBOX = 'https://api-m.sandbox.paypal.com'
LIVE = 'https://api-m.paypal.com'
# PayPal does not support BDT; sellers choose the settlement currency and rate.
SUPPORTED = {'USD': '$', 'EUR': '€', 'GBP': '£'}


@register_payment
class PayPal(PaymentProvider):
    id = 'paypal'
    label = 'PayPal'
    method_ids = ['paypal']
    supports_refund = True
    supports_webhook = True
    docs_url = 'https://developer.paypal.com/docs/api/orders/v2/'
    config_fields = [
        field('client_id', 'Client ID'),
        field('client_secret', 'Client secret', secret=True),
    ]
    settings_fields = [
        setting('currency', 'Settlement currency', options=sorted(SUPPORTED), default='USD', help='PayPal cannot settle in BDT; orders are converted'),
        setting('units_per_bdt', 'Currency units per 1 BDT', required=False, default='0.0082', help='e.g. 0.0082 USD per BDT - maintained by the owner'),
    ]

    def base(self, sandbox):
        return SANDBOX if sandbox else LIVE

    def auth(self, credentials):
        pair = f"{credentials.get('client_id', '')}:{credentials.get('client_secret', '')}".encode()
        return {'Authorization': 'Basic ' + base64.b64encode(pair).decode(), 'Content-Type': 'application/x-www-form-urlencoded'}

    async def token(self, client, base, credentials):
        response = await client.post(base + '/v1/oauth2/token', data={'grant_type': 'client_credentials'}, headers=self.auth(credentials))
        body = response.json()
        if 'access_token' not in body:
            raise ProviderError('PayPal rejected the client credentials')
        return body['access_token']

    def converted(self, order, config):
        try:
            rate = float(config.get('units_per_bdt') or 0)
        except ValueError:
            rate = 0
        currency = (config.get('currency') or 'USD').upper()
        if currency not in SUPPORTED or rate <= 0:
            raise ProviderError(f'Configure a supported settlement currency ({", ".join(SUPPORTED)}) and a conversion rate before accepting PayPal')
        return currency, round(order['total'] / 100 * rate, 2)

    async def validate_config(self, credentials, sandbox):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await self.token(client, self.base(sandbox), credentials)
            return True, 'PayPal credentials verified (token granted).'
        except ProviderError as error:
            return False, str(error)
        except Exception as error:
            return False, f'PayPal verification failed: {error}'

    async def initiate(self, order, config, credentials, return_url, cancel_url, webhook_url=''):
        currency, amount = self.converted(order, config.get('config', {}) or config)
        base = self.base(order.get('sandbox', True))
        body = {'intent': 'CAPTURE', 'purchase_units': [{'reference_id': order['transaction_id'], 'custom_id': order['id'], 'description': f"VOLTORA order {order['number']}"[:127], 'amount': {'currency_code': currency, 'value': f'{amount:.2f}'}}],
                'application_context': {'return_url': return_url, 'cancel_url': cancel_url, 'shipping_preference': 'NO_SHIPPING'}}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self.token(client, base, credentials)
                response = await client.post(base + '/v2/checkout/orders', json=body, headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
                created = response.json()
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f'PayPal order creation failed: {error}')
        if created.get('status') != 'CREATED':
            raise ProviderError('PayPal did not create the order')
        link = next((l['href'] for l in created.get('links', []) if l['rel'] == 'approve'), '')
        if not link:
            raise ProviderError('PayPal returned no approval link')
        return {'redirect_url': link, 'paypal_order_id': created['id'], 'converted': {'currency': currency, 'amount': amount}}

    async def verify(self, transaction, credentials, params):
        token_id = params.get('token', '') or transaction.get('provider_ref', '')
        if not token_id:
            return 'pending'
        base = self.base(transaction.get('sandbox', True))
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                access = await self.token(client, base, credentials)
                response = await client.get(base + '/v2/checkout/orders/' + token_id, headers={'Authorization': 'Bearer ' + access})
                body = response.json()
        except Exception as error:
            raise ProviderError(f'PayPal verification failed: {error}')
        status = body.get('status', '')
        if status == 'COMPLETED':
            return 'paid'
        if status in ('APPROVED', 'CREATED'):
            return 'pending'
        return 'failed'

    async def refund(self, transaction, credentials, amount):
        pc = transaction.get('provider_config') or {}
        try:
            rate = float(pc.get('units_per_bdt') or 0)
        except ValueError:
            rate = 0
        currency = (pc.get('currency') or 'USD').upper()
        if rate <= 0 or currency not in SUPPORTED:
            raise ProviderError('No conversion rate was recorded for this transaction; refund manually in the PayPal panel')
        capture_id = transaction.get('provider_capture_id', '')
        if not capture_id:
            raise ProviderError('This transaction has no PayPal capture reference to refund')
        base = self.base(transaction.get('sandbox', True))
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                access = await self.token(client, base, credentials)
                response = await client.post(base + f'/v2/payments/captures/{capture_id}/refund', json={'amount': {'currency_code': currency, 'value': f'{amount / 100 * rate:.2f}'}}, headers={'Authorization': 'Bearer ' + access})
                body = response.json()
        except Exception as error:
            raise ProviderError(f'PayPal refund failed: {error}')
        if body.get('status') not in ('COMPLETED', 'PENDING'):
            raise ProviderError('PayPal refund was not accepted')
        return {'ok': True, 'provider_ref': body.get('id', '')}

    async def parse_webhook(self, payload, headers, credentials):
        import json as _json
        try:
            event = _json.loads(payload.decode('utf-8', 'ignore') if isinstance(payload, bytes) else payload)
        except Exception:
            return None
        kind = event.get('event_type', '')
        resource = event.get('resource', {}) or {}
        status = {'CHECKOUT.ORDER.COMPLETED': 'paid', 'CHECKOUT.ORDER.APPROVED': 'pending', 'PAYMENT.CAPTURE.COMPLETED': 'paid', 'PAYMENT.CAPTURE.DENIED': 'failed', 'PAYMENT.CAPTURE.REFUNDED': 'refunded'}.get(kind)
        if not status:
            return None
        return {'event_id': event.get('id', ''), 'type': kind,
                'reference': resource.get('custom_id', '') or (resource.get('purchase_units') or [{}])[0].get('reference_id', ''),
                'capture_id': resource.get('id', '') if kind.startswith('PAYMENT.CAPTURE') else '',
                'status': status, 'raw': str(event)[:4000]}
