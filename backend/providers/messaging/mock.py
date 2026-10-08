'''Simulated SMS + email channels. Messages are recorded in the provider
config's log instead of being sent - used for testing notification flows.
'''
from providers.base import MessagingAdapter, register_messaging


@register_messaging
class MockSMS(MessagingAdapter):
    id = 'mock'
    kind = 'sms'
    label = 'Test SMS (logged, not sent)'
    config_fields = []
    settings_fields = []

    async def validate_config(self, credentials, sandbox):
        return True, 'Test SMS is ready. Messages are logged, not delivered.'

    async def send(self, credentials, to, subject, body):
        return {'ok': True, 'note': 'Test double only; no delivery'}


@register_messaging
class MockEmail(MessagingAdapter):
    id = 'mock'
    kind = 'email'
    label = 'Test email (logged, not sent)'
    config_fields = []
    settings_fields = []

    async def validate_config(self, credentials, sandbox):
        return True, 'Test email is ready. Messages are logged, not delivered.'

    async def send(self, credentials, to, subject, body):
        return {'ok': True, 'note': 'Test double only; no delivery'}
