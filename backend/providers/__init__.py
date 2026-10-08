'''Provider registry. Importing this package auto-discovers every adapter
module under providers/payments, providers/couriers and providers/messaging.

Provider configuration lives in the `provider_configs` collection:
{'id': 'payment:mock' | 'courier:pathao' | 'messaging:smtp', 'kind': 'payment'|'courier'|'messaging',
 'messaging_kind': 'sms'|'email' (messaging only), 'provider': <adapter id>, 'method_ids': [...],
 'enabled': bool, 'sandbox': bool, 'credentials': {field: sealed}, 'config': {...},
 'status': 'connected'|'error'|'not_configured', 'last_verified': iso, 'error': '', 'updated_at': iso}
'''
import importlib
import pkgutil

from providers.base import (PAYMENTS, COURIERS, MESSAGING, NOTIFICATIONS, CAPTCHAS, INFRA, ProviderError, field, setting,
                            Base, PaymentProvider, CourierProvider, MessagingAdapter, NotificationProvider, CaptchaProvider, InfraProvider)

KINDS = ('payment', 'courier', 'messaging', 'notification', 'captcha', 'infra')


def _load():
    for pkg in ('providers.payments', 'providers.couriers', 'providers.messaging', 'providers.notifications', 'providers.captcha', 'providers.infra'):
        try:
            module = importlib.import_module(pkg)
        except ModuleNotFoundError:
            continue
        for info in pkgutil.iter_modules(module.__path__):
            # Operational runtimes never discover test doubles, including sandbox.
            if info.name == 'mock':
                continue
            importlib.import_module(f'{pkg}.{info.name}')


_load()


def registry(kind):
    if kind == 'payment':
        return PAYMENTS
    if kind == 'courier':
        return COURIERS
    if kind == 'messaging':
        return MESSAGING
    if kind == 'notification':
        return NOTIFICATIONS
    if kind == 'captcha':
        return CAPTCHAS
    if kind == 'infra':
        return INFRA
    raise KeyError(kind)


def get_adapter(kind, provider_id):
    if provider_id == 'mock':
        return None
    reg = registry(kind)
    if kind == 'messaging':
        sms, email = reg.get(('sms', provider_id)), reg.get(('email', provider_id))
        return (sms or email)() if (sms or email) else None
    cls = reg.get(provider_id)
    return cls() if cls else None


def runtime_environment_filter():
    from core import RUNTIME_MODE
    return {'sandbox': False if RUNTIME_MODE == 'production' else {'$ne': False}}


def operational_row(row):
    """Reject saved test doubles and environment crossover, including legacy rows."""
    from core import RUNTIME_MODE
    if not row or row.get('provider') == 'mock':
        return False
    if RUNTIME_MODE == 'production' and row.get('sandbox', True):
        return False
    if RUNTIME_MODE != 'production' and not row.get('sandbox', True):
        return False
    if not get_adapter(row.get('kind'), row.get('provider')):
        return False
    # New configurations require independent workflow evidence; old real adapters
    # remain intact pending explicit owner migration, never silently rewritten.
    if row.get('schema_version') == 2:
        evidence = row.get('workflow', {})
        if evidence.get('status') != 'verified' or evidence.get('version') != row.get('version'):
            return False
    return True


async def notification_config(db):
    from core import EXTERNAL_ACTIONS
    if not EXTERNAL_ACTIONS:
        return None
    row = await db.provider_configs.find_one({'kind': 'notification', 'enabled': True, 'status': 'connected', **runtime_environment_filter()}, {'_id': 0})
    if not operational_row(row):
        return None
    row['unsealed'] = open_credentials(row.get('credentials'))
    return row


async def infra_config(db, provider_id=None):
    from core import require_external_actions
    require_external_actions()
    query = {'kind': 'infra', 'enabled': True, 'status': 'connected', **runtime_environment_filter()}
    if provider_id:
        query['provider'] = provider_id
    row = await db.provider_configs.find_one(query, {'_id': 0})
    if not operational_row(row):
        return None
    row['unsealed'] = open_credentials(row.get('credentials'))
    return row


async def captcha_config(db):
    from core import EXTERNAL_ACTIONS
    if not EXTERNAL_ACTIONS:
        return None
    row = await db.provider_configs.find_one({'kind': 'captcha', 'enabled': True, 'status': 'connected', **runtime_environment_filter()}, {'_id': 0})
    if not operational_row(row):
        return None
    row['unsealed'] = open_credentials(row.get('credentials'))
    return row


def seal_credentials(credentials: dict) -> dict:
    from vault import seal
    return {k: seal(str(v)) for k, v in (credentials or {}).items() if str(v) != ''}


def open_credentials(stored: dict) -> dict:
    from vault import unseal
    from cryptography.fernet import InvalidToken
    out = {}
    for k, v in (stored or {}).items():
        try:
            out[k] = unseal(v)
        except (InvalidToken, Exception):
            out[k] = ''
    return out


async def payment_config(db, method_id):
    '''Enabled+connected payment provider serving the given checkout method id, unsealed.'''
    from core import require_external_actions
    require_external_actions()
    row = await db.provider_configs.find_one({'kind': 'payment', 'method_ids': method_id, 'enabled': True, 'status': 'connected', **runtime_environment_filter()}, {'_id': 0})
    if not operational_row(row):
        return None
    row['unsealed'] = open_credentials(row.get('credentials'))
    return row


async def courier_config(db, courier_id=None):
    from core import require_external_actions
    require_external_actions()
    query = {'kind': 'courier', 'enabled': True, 'status': 'connected', **runtime_environment_filter()}
    if courier_id:
        query['provider'] = courier_id
    row = await db.provider_configs.find_one(query, {'_id': 0})
    if not operational_row(row):
        return None
    row['unsealed'] = open_credentials(row.get('credentials'))
    return row


async def messaging_config(db, kind):
    from core import EXTERNAL_ACTIONS
    if not EXTERNAL_ACTIONS:
        return None
    row = await db.provider_configs.find_one({'kind': 'messaging', 'messaging_kind': kind, 'enabled': True, 'status': 'connected', **runtime_environment_filter()}, {'_id': 0})
    if not operational_row(row):
        return None
    row['unsealed'] = open_credentials(row.get('credentials'))
    return row


async def active_payment_methods(db):
    '''Checkout method ids currently payable, with provider + sandbox metadata.'''
    from core import EXTERNAL_ACTIONS
    if not EXTERNAL_ACTIONS:
        return []
    rows = await db.provider_configs.find({'kind': 'payment', 'enabled': True, 'status': 'connected', **runtime_environment_filter()}, {'_id': 0}).to_list(50)
    return [{k: row[k] for k in ('provider', 'method_ids', 'sandbox') if k in row}
            for row in rows if operational_row(row)]


async def any_connected(db, kind, messaging_kind=None):
    query = {'kind': kind, 'enabled': True, 'status': 'connected', **runtime_environment_filter()}
    if messaging_kind:
        query['messaging_kind'] = messaging_kind
    from core import EXTERNAL_ACTIONS
    if not EXTERNAL_ACTIONS:
        return False
    rows = await db.provider_configs.find(query, {'_id': 0}).to_list(50)
    return any(operational_row(row) for row in rows)
