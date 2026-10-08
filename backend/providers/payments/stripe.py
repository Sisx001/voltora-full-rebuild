'''Stripe Checkout adapter (hosted Checkout Sessions, PaymentIntents under the hood).
Uses the official stripe SDK pinned in requirements. Webhook signatures are verified
with the webhook signing secret; payment state changes are authoritative only after
verification. Refunds use the Stripe Refund API when eligible.
'''
import stripe
from providers.base import PaymentProvider, register_payment, ProviderError, field

stripe.api_version = '2024-06-20'


@register_payment
class Stripe(PaymentProvider):
    id = 'stripe'
    label = 'Stripe'
    method_ids = ['stripe']
    supports_refund = True
    supports_webhook = True
    docs_url = 'https://stripe.com/docs/payments/checkout'
    config_fields = [
        field('secret_key', 'Secret key (sk_...)', secret=True),
        field('webhook_secret', 'Webhook signing secret (whsec_...)', secret=True, required=False),
    ]
    settings_fields = []

    def api(self, credentials):
        key = credentials.get('secret_key', '')
        if not key:
            raise ProviderError('Stripe secret key is missing')
        return key

    async def validate_config(self, credentials, sandbox):
        try:
            def probe():
                stripe.api_key = self.api(credentials)
                stripe.Balance.retrieve()
            import asyncio
            await asyncio.to_thread(probe)
            return True, 'Stripe key verified (balance endpoint reachable).'
        except stripe.error.AuthenticationError:
            return False, 'Stripe rejected the API key.'
        except Exception as error:
            return False, f'Stripe verification failed: {error}'

    async def initiate(self, order, config, credentials, return_url, cancel_url, webhook_url=''):
        def create():
            stripe.api_key = self.api(credentials)
            return stripe.checkout.Session.create(
                mode='payment',
                success_url=return_url,
                cancel_url=cancel_url,
                client_reference_id=order['id'],
                metadata={'order_id': order['id'], 'transaction_id': order['transaction_id']},
                line_items=[{'quantity': 1, 'price_data': {
                    'currency': 'bdt',
                    'unit_amount': order['total'],
                    'product_data': {'name': ', '.join(i['name'] for i in order['items'][:3])[:120]},
                }}],
            )
        import asyncio
        try:
            session = await asyncio.to_thread(create)
        except stripe.error.StripeError as error:
            raise ProviderError(f'Stripe session failed: {error.user_message or error}')
        return {'redirect_url': session.url, 'session_id': session.id}

    async def verify(self, transaction, credentials, params):
        session_id = params.get('session_id', '') or transaction.get('provider_ref', '')
        if not session_id:
            return 'pending'

        def retrieve():
            stripe.api_key = self.api(credentials)
            return stripe.checkout.Session.retrieve(session_id)
        import asyncio
        try:
            session = await asyncio.to_thread(retrieve)
        except stripe.error.StripeError:
            return 'pending'
        if session.payment_status == 'paid':
            return 'paid'
        if session.payment_status == 'unpaid':
            return 'pending'
        return 'failed'

    async def refund(self, transaction, credentials, amount):
        def refund():
            stripe.api_key = self.api(credentials)
            return stripe.Refund.create(payment_intent=transaction.get('provider_intent', '') or None, charge=transaction.get('provider_charge', '') or None, amount=amount)
        if not (transaction.get('provider_intent') or transaction.get('provider_charge')):
            raise ProviderError('This transaction has no Stripe payment reference to refund')
        import asyncio
        try:
            result = await asyncio.to_thread(refund)
        except stripe.error.StripeError as error:
            raise ProviderError(f'Stripe refund failed: {error.user_message or error}')
        return {'ok': result.status == 'succeeded', 'provider_ref': result.id}

    async def parse_webhook(self, payload, headers, credentials):
        secret = credentials.get('webhook_secret', '')
        signature = headers.get('stripe-signature', '')
        if not secret or not signature:
            return None
        try:
            event = stripe.Webhook.construct_event(payload, signature, secret)
        except (ValueError, stripe.error.SignatureVerificationError) as error:
            raise ProviderError(f'Invalid Stripe webhook signature: {error}')
        data = event.data.object
        kind = event.type
        if kind == 'checkout.session.completed':
            status = 'paid' if data.payment_status == 'paid' else 'pending'
        elif kind in ('checkout.session.async_payment_succeeded',):
            status = 'paid'
        elif kind in ('checkout.session.expired', 'checkout.session.async_payment_failed'):
            status = 'failed'
        else:
            return None
        return {'event_id': event.id, 'type': kind, 'reference': data.metadata.get('transaction_id', '') if data.get('metadata') else '', 'order_id': data.metadata.get('order_id', '') if data.get('metadata') else '', 'status': status, 'session_id': data.id, 'raw': str(event)[:4000]}
