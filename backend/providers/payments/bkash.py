'''bKash Tokenized Checkout adapter (direct bKash merchant account).
Sandbox: https://developer.bka.sh - tokenized checkout, mode '0011' (checkout).
The customer completes payment on bKash's hosted page and is redirected back to
the callback URL with paymentID/status; execution completes the transaction.
'''
import httpx
from providers.base import PaymentProvider, register_payment, ProviderError, field

SANDBOX = 'https://tokenized.sandbox.bka.sh/v1.2.0-tokenized'
LIVE = 'https://tokenized.pay.bka.sh/v1.2.0-tokenized'


@register_payment
class Bkash(PaymentProvider):
    id = 'bkash'
    label = 'bKash'
    method_ids = ['bkash']
    supports_refund = True
    supports_webhook = False  # tokenized checkout returns via callback URL, not webhooks
    docs_url = 'https://developer.bka.sh/docs/tokenized-checkout-overview'
    config_fields = [
        field('app_key', 'App key'),
        field('app_secret', 'App secret', secret=True),
        field('username', 'API username', secret=True),
        field('password', 'API password', secret=True),
    ]
    settings_fields = []

    def base(self, sandbox):
        return SANDBOX if sandbox else LIVE

    def headers(self, credentials, id_token=''):
        return {'Content-Type': 'application/json', 'Accept': 'application/json',
                'username': credentials.get('username', ''), 'password': credentials.get('password', ''),
                **({'Authorization': id_token} if id_token else {})}

    async def grant(self, client, base, credentials):
        response = await client.post(base + '/checkout/token/grant', json={'app_key': credentials.get('app_key', ''), 'app_secret': credentials.get('app_secret', '')}, headers=self.headers(credentials))
        body = response.json()
        token = body.get('id_token', '')
        if not token:
            raise ProviderError(body.get('statusMessage') or 'bKash rejected the app credentials')
        return token

    async def validate_config(self, credentials, sandbox):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                await self.grant(client, self.base(sandbox), credentials)
            return True, 'bKash credentials verified (token granted).'
        except ProviderError as error:
            return False, str(error)
        except Exception as error:
            return False, f'bKash verification failed: {error}'

    async def initiate(self, order, config, credentials, return_url, cancel_url, webhook_url=''):
        base = self.base(order.get('sandbox', True))
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self.grant(client, base, credentials)
                body = {'mode': '0011',
                        'payerReference': order['customer'].get('phone', '') or order['customer']['email'],
                        'callbackURL': return_url,
                        'amount': f"{order['total'] / 100:.2f}",
                        'currency': 'BDT',
                        'intent': 'sale',
                        'merchantInvoiceNumber': order['transaction_id'][:50]}
                response = await client.post(base + '/checkout/create', json=body, headers=self.headers(credentials, token))
                created = response.json()
        except ProviderError:
            raise
        except Exception as error:
            raise ProviderError(f'bKash payment creation failed: {error}')
        if created.get('statusCode') != '0000' or not created.get('bkashURL'):
            raise ProviderError(created.get('statusMessage') or 'bKash did not return a payment URL')
        return {'redirect_url': created['bkashURL'], 'payment_id': created.get('paymentID', '')}

    async def verify(self, transaction, credentials, params):
        base = self.base(transaction.get('sandbox', True))
        payment_id = params.get('paymentID', '') or transaction.get('provider_ref', '')
        if not payment_id:
            return 'pending'
        if str(params.get('status', '')).lower() == 'cancel':
            return 'failed'
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self.grant(client, base, credentials)
                response = await client.post(base + '/checkout/execute', json={'paymentID': payment_id}, headers=self.headers(credentials, token))
                body = response.json()
        except Exception as error:
            raise ProviderError(f'bKash execution failed: {error}')
        if body.get('transactionStatus') == 'Completed':
            return 'paid'
        if body.get('statusCode') in ('5001', 'failed') or body.get('transactionStatus') == 'Failed':
            return 'failed'
        return 'pending'

    async def refund(self, transaction, credentials, amount):
        base = self.base(transaction.get('sandbox', True))
        payment_id = transaction.get('provider_ref', '')
        trx_id = transaction.get('provider_trx_id', '')
        if not payment_id or not trx_id:
            raise ProviderError('This transaction has no bKash reference to refund')
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                token = await self.grant(client, base, credentials)
                response = await client.post(base + '/checkout/payment/refund', json={'paymentID': payment_id, 'trxID': trx_id, 'amount': f"{amount / 100:.2f}", 'reason': 'Store refund', 'sku': 'refund'}, headers=self.headers(credentials, token))
                body = response.json()
        except Exception as error:
            raise ProviderError(f'bKash refund failed: {error}')
        if body.get('transactionStatus') != 'Completed':
            raise ProviderError(body.get('statusMessage') or 'bKash refund was not completed')
        return {'ok': True, 'provider_trx_id': body.get('trxID', '')}

    async def parse_webhook(self, payload, headers, credentials):
        return None
