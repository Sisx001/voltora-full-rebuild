'''SSLCommerz hosted checkout adapter. Serves the sslcommerz method id plus the
aggregated nagad/rocket/upay method ids (visible as separate checkout options but
all processed through the merchant's SSLCommerz account).
Sandbox docs: https://developer.sslcommerz.com/doc/v4/index.html
'''
import httpx
from decimal import Decimal, InvalidOperation
from providers.base import PaymentProvider, register_payment, ProviderError, field, setting

SANDBOX = 'https://sandbox.sslcommerz.com'
LIVE = 'https://securepay.sslcommerz.com'


@register_payment
class SSLCommerz(PaymentProvider):
    id = 'sslcommerz'
    label = 'SSLCommerz'
    method_ids = ['sslcommerz', 'nagad', 'rocket', 'upay']
    supports_refund = False  # refunds are recorded manually from the merchant panel
    supports_webhook = True
    docs_url = 'https://developer.sslcommerz.com/doc/v4/index.html'
    config_fields = [
        field('store_id', 'Store ID'),
        field('store_passwd', 'Store password (API)', secret=True),
    ]
    settings_fields = []

    def base(self, sandbox):
        return SANDBOX if sandbox else LIVE

    async def validate_config(self, credentials, sandbox):
        data = {'store_id': credentials.get('store_id', ''), 'store_passwd': credentials.get('store_passwd', ''), 'format': 'json'}
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self.base(sandbox) + '/validator/api/merchantinfo.php', params=data)
            body = response.json() if 'json' in response.headers.get('content-type', '') else {}
            if response.status_code == 200 and body.get('status') in ('SUCCESS', 'ACTIVE', 'alive'):
                return True, 'SSLCommerz credentials verified.'
            return False, 'SSLCommerz rejected the credentials. Check the store ID and password.'
        except Exception as error:
            return False, f'SSLCommerz verification failed: {error}'

    async def initiate(self, order, config, credentials, return_url, cancel_url, webhook_url=''):
        payload = {
            'store_id': credentials.get('store_id', ''),
            'store_passwd': credentials.get('store_passwd', ''),
            'total_amount': f"{order['total'] / 100:.2f}",
            'currency': 'BDT',
            'tran_id': order['transaction_id'],
            'success_url': return_url,
            'fail_url': cancel_url,
            'cancel_url': cancel_url,
            'ipn_url': webhook_url,
            'shipping_method': 'Courier',
            'product_name': ', '.join(i['name'] for i in order['items'][:5])[:250],
            'product_category': 'Electronics',
            'product_profile': 'physical-goods',
            'cus_name': order['customer']['name'],
            'cus_email': order['customer']['email'],
            'cus_add1': order['customer'].get('address', ''),
            'cus_city': order['customer'].get('city', ''),
            'cus_postcode': order['customer'].get('postal_code', ''),
            'cus_country': 'Bangladesh',
            'cus_phone': order['customer'].get('phone', ''),
            'ship_name': order['customer']['name'],
            'ship_add1': order['customer'].get('address', ''),
            'ship_city': order['customer'].get('city', ''),
            'ship_country': 'Bangladesh',
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(self.base(order.get('sandbox', True)) + '/gwprocess/v4/api.php', data=payload)
            body = response.json()
        except Exception as error:
            raise ProviderError(f'SSLCommerz session failed: {error}')
        if body.get('status') != 'SUCCESS' or not body.get('GatewayPageURL'):
            raise ProviderError(body.get('failedreason') or 'SSLCommerz did not return a payment page')
        return {'redirect_url': body['GatewayPageURL']}

    async def verify(self, transaction, credentials, params):
        val_id = params.get('val_id', '')
        if not val_id:
            return 'pending'
        query = {'val_id': val_id, 'store_id': credentials.get('store_id', ''), 'store_passwd': credentials.get('store_passwd', ''), 'format': 'json'}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(self.base(transaction.get('sandbox', True)) + '/validator/api/validationserverAPI.php', params=query)
        body = response.json()
        status = body.get('status', '')
        if status in ('VALID', 'VALIDATED'):
            try:
                amount = Decimal(str(body.get('amount', ''))) * 100
                expected = Decimal(str(transaction['amount']))
            except (InvalidOperation, KeyError, ValueError):
                raise ProviderError('Payment verification did not include a valid amount')
            if (not amount.is_finite() or amount != expected
                    or body.get('tran_id') != transaction.get('id')
                    or body.get('currency') != transaction.get('currency')):
                raise ProviderError('Payment does not match the expected transaction, amount and currency')
            return 'paid'
        if status in ('FAILED', 'CANCELLED', 'EXPIRED'):
            return 'failed'
        return 'pending'

    async def parse_webhook(self, payload, headers, credentials):
        '''SSLCommerz IPN posts form fields; the val_id is re-validated server-side by
        the verify path before any order state changes.'''
        from urllib.parse import parse_qs
        text = payload.decode('utf-8', 'ignore') if isinstance(payload, bytes) else str(payload)
        form = {k: v[0] for k, v in parse_qs(text).items()}
        val_id = form.get('val_id', '')
        if not val_id:
            return None
        return {'event_id': f"ipn:{val_id}:{form.get('status', '')}", 'type': form.get('status', ''),
                'reference': form.get('tran_id', ''), 'status': form.get('status', ''), 'amount': form.get('amount', ''), 'raw': text[:4000]}
