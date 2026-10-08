'''Simulated payment gateway. Lets the whole checkout -> transaction -> webhook
pipeline run end-to-end (including automated tests) without any real provider.
Verification outcome is controlled from the admin config: outcome = 'paid' | 'fail'.
'''
from providers.base import PaymentProvider, register_payment, field


@register_payment
class MockPayment(PaymentProvider):
    id = 'mock'
    label = 'Test gateway (simulated)'
    method_ids = ['mock']
    supports_refund = True
    supports_webhook = True
    docs_url = ''
    config_fields = []
    settings_fields = [
        field('outcome', 'Simulated verification outcome', required=False, placeholder='paid', help="What verification returns: 'paid' or 'fail'"),
    ]

    async def validate_config(self, credentials, sandbox):
        return True, 'Test gateway is ready. Payments are simulated; no money moves.'

    async def initiate(self, order, config, credentials, return_url, cancel_url, webhook_url=''):
        return {'redirect_url': return_url}

    async def verify(self, transaction, credentials, params):
        outcome = (transaction.get('provider_config') or {}).get('outcome', 'paid')
        return 'paid' if outcome != 'fail' else 'failed'

    async def refund(self, transaction, credentials, amount):
        return {'ok': True, 'note': 'Simulated refund'}
