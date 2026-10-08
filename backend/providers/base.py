'''Provider adapter contracts and registries.

A provider is one payment gateway, courier company, or messaging channel.
Adapters subclass the bases below and self-register; the core application
never imports a concrete adapter. Adding a provider means adding one file
under providers/payments, providers/couriers or providers/messaging - the
package loader (providers/__init__.py) auto-discovers it.

Credentials at rest: every value inside a provider config's `credentials`
dict is Fernet-sealed (vault.seal) and only unsealed inside adapters via
providers.open_credentials.
'''

PAYMENTS = {}
COURIERS = {}
MESSAGING = {}
NOTIFICATIONS = {}
CAPTCHAS = {}
INFRA = {}


def register_payment(cls):
    PAYMENTS[cls.id] = cls
    return cls


def register_courier(cls):
    COURIERS[cls.id] = cls
    return cls


def register_messaging(cls):
    MESSAGING[(cls.kind, cls.id)] = cls
    return cls


def register_notification(cls):
    NOTIFICATIONS[cls.id] = cls
    return cls


def register_captcha(cls):
    CAPTCHAS[cls.id] = cls
    return cls


def register_infra(cls):
    INFRA[cls.id] = cls
    return cls


class ProviderError(Exception):
    '''Raised by adapters for expected, user-visible failures.'''


def field(key, label, secret=False, required=True, placeholder='', help=''):
    return {'key': key, 'label': label, 'secret': secret, 'required': required, 'placeholder': placeholder, 'help': help}


def setting(key, label, type='text', options=None, default='', help='', required=True, placeholder=''):
    return {'key': key, 'label': label, 'type': type, 'options': options or [], 'default': default, 'help': help, 'required': required, 'placeholder': placeholder}


class Base:
    id = ''
    label = ''
    docs_url = ''
    config_fields: list = []     # credential fields the admin must supply
    settings_fields: list = []   # non-secret knobs edited in the admin panel

    def mask_credentials(self, credentials: dict) -> dict:
        return {f['key']: {'configured': bool((credentials or {}).get(f['key']))} for f in self.config_fields}


class PaymentProvider(Base):
    # checkout payment_method ids this adapter fulfils (e.g. an aggregator serves several)
    method_ids: list = []
    supports_refund = False
    supports_webhook = False

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        '''Return (ok, message). Called with unsealed credentials before enabling or on demand.'''
        return True, 'Credentials stored. This provider does not perform live verification.'

    async def initiate(self, order: dict, config: dict, credentials: dict, return_url: str, cancel_url: str, webhook_url: str = '') -> dict:
        '''Start a payment for a persisted order. Return {'redirect_url':...} for hosted
        checkout or {'params':{...}} for client-side flows. Raise ProviderError on failure.'''
        raise NotImplementedError

    async def verify(self, transaction: dict, credentials: dict, params: dict) -> str:
        '''Resolve a transaction after gateway return or webhook. Return 'paid'|'failed'|'pending'.'''
        raise NotImplementedError

    async def refund(self, transaction: dict, credentials: dict, amount: int) -> dict:
        raise ProviderError('Refunds are not supported by this provider')

    async def parse_webhook(self, payload: bytes, headers: dict, credentials: dict) -> dict | None:
        '''Return {'event_id','type','reference','status','amount'} or None to ignore.
        Must verify signatures; raise ProviderError on invalid signatures.'''
        return None


class CourierProvider(Base):
    supports_webhook = False

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        return True, 'Credentials stored. This provider does not perform live verification.'

    async def create_shipment(self, order: dict, config: dict, credentials: dict, parcel: dict) -> dict:
        '''Return {'consignment_id','status','tracking_url'} for the pickup/delivery booking.'''
        raise NotImplementedError

    async def track(self, config: dict, credentials: dict, consignment_id: str) -> dict:
        '''Return {'status','history':[{'status','at','note'}]}.'''
        raise NotImplementedError

    async def cancel_shipment(self, config: dict, credentials: dict, consignment_id: str) -> dict:
        raise ProviderError('Cancellation is not supported by this courier')

    async def parse_webhook(self, payload: bytes, headers: dict, credentials: dict) -> dict | None:
        return None


class MessagingAdapter(Base):
    kind = 'sms'  # 'sms' | 'email'

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        return True, 'Credentials stored. This provider does not perform live verification.'

    async def send(self, credentials: dict, to: str, subject: str, body: str) -> dict:
        raise NotImplementedError


class NotificationProvider(Base):
    '''Outbound alert channels (Telegram etc.). Events are filtered by the
    alerts dispatcher using the provider's non-secret `events` setting.'''
    events_help = 'admin_login, admin_login_failed, payment_failed, courier_failed, security_flag'

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        return True, 'Credentials stored. This provider does not perform live verification.'

    async def send_alert(self, credentials: dict, title: str, body: str, severity: str) -> dict:
        raise NotImplementedError


class CaptchaProvider(Base):
    '''Pluggable anti-bot verification. site_key is public; secret stays sealed.'''

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        return True, 'Credentials stored. This provider does not perform live verification.'

    def site_key(self, credentials: dict) -> str:
        return credentials.get('site_key', '')

    def script_url(self) -> str:
        return ''

    async def verify(self, credentials: dict, token: str, remote_ip: str) -> bool:
        raise NotImplementedError


class InfraProvider(Base):
    '''Infrastructure integrations (Cloudflare etc.). Real API actions only —
    each action must be declared in the adapter's `actions` list and performs a
    live authenticated call against the provider.'''

    actions: list = []   # e.g. ['purge_cache', 'dev_mode'] -> POST /api/admin/infra/<id>/<action>

    async def validate_config(self, credentials: dict, sandbox: bool) -> tuple:
        return True, 'Credentials stored. This provider does not perform live verification.'

    async def action(self, credentials: dict, config: dict, action: str, params: dict) -> dict:
        raise ProviderError(f'Unknown action "{action}" for this integration')
