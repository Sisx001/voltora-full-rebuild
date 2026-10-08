'''Admin management of provider integrations (payment gateways, couriers,
messaging channels). Credentials are write-only: they are sealed at rest and
never returned - the API reports which fields are configured, not their values.
'''
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from core import db, Doc, Input, stamp, audit
from permissions import require, authorize
from auth import current_user
import providers
from providers import ProviderError

router = APIRouter(prefix='/api/admin/providers', tags=['Integrations'])

READ_PERMISSION = {'payment': 'payments.read', 'courier': 'couriers.read', 'messaging': 'settings.read', 'notification': 'settings.read', 'captcha': 'settings.read', 'infra': 'settings.read'}
WRITE_PERMISSION = {'payment': 'payments.update', 'courier': 'couriers.update', 'messaging': 'settings.update', 'notification': 'settings.update', 'captcha': 'settings.update', 'infra': 'settings.update'}
Kind = Literal['payment', 'courier', 'messaging', 'notification', 'captcha', 'infra']


def kind_guard(read: bool):
    '''Permission gate resolved per-request from the path's `kind` parameter.
    (A dynamic require(READ_PERMISSION[kind]) default would evaluate at import time.)'''
    mapping = READ_PERMISSION if read else WRITE_PERMISSION
    async def dependency(kind: str, user=Depends(current_user)):
        action = mapping.get(kind)
        if not action:
            raise HTTPException(404, 'Unknown provider kind')
        await authorize(user, action)
        return user
    return dependency


def adapter_or_404(kind: str, provider: str, channel: str = ''):
    if kind == 'messaging' and channel:
        cls = providers.MESSAGING.get((channel, provider))
        if not cls:
            raise HTTPException(404, 'Unknown provider')
        return cls()
    adapter = providers.get_adapter(kind, provider)
    if not adapter:
        raise HTTPException(404, 'Unknown provider')
    return adapter


def messaging_channel(adapter, channel: str) -> str:
    '''The channel a messaging config belongs to (sms|email); query param wins, else adapter default.'''
    if channel in ('sms', 'email'):
        return channel
    return getattr(adapter, 'kind', '')


async def saved_config(kind: str, provider: str, messaging_kind: str = ''):
    query = {'kind': kind, 'provider': provider}
    if messaging_kind:
        query['messaging_kind'] = messaging_kind
    return await db.provider_configs.find_one(query, {'_id': 0})


def summary(kind: str, adapter, row: dict | None):
    return {
        'id': adapter.id, 'kind': kind, 'messaging_kind': getattr(adapter, 'kind', ''),
        'label': adapter.label, 'docs_url': adapter.docs_url,
        'method_ids': list(getattr(adapter, 'method_ids', [])),
        'supports_refund': bool(getattr(adapter, 'supports_refund', False)),
        'supports_webhook': bool(getattr(adapter, 'supports_webhook', False)),
        'actions': list(getattr(adapter, 'actions', [])),
        'credentials_spec': adapter.config_fields, 'settings_spec': adapter.settings_fields,
        'configured': bool(row and row.get('credentials')),
        'enabled': bool((row or {}).get('enabled')), 'sandbox': bool((row or {}).get('sandbox', True)),
        'config': (row or {}).get('config', {}), 'status': (row or {}).get('status', 'not_configured'),
        'error': (row or {}).get('error', ''), 'last_verified': (row or {}).get('last_verified', ''),
    }


@router.get('/{kind}', response_model=list[Doc])
async def list_providers(kind: Kind, user=Depends(require('settings.read'))):
    saved_rows = await db.provider_configs.find({'kind': kind}, {'_id': 0}).to_list(50)
    if kind == 'messaging':
        by_key = {(s.get('messaging_kind'), s['provider']): s for s in saved_rows}
        return [summary('messaging', cls(), by_key.get((cls().kind, cls().id))) for cls in providers.MESSAGING.values()]
    saved = {r['provider']: r for r in saved_rows}
    return [summary(kind, cls(), saved.get(cls.id)) for cls in providers.registry(kind).values()]


@router.get('/{kind}/{provider}', response_model=Doc)
async def provider_detail(kind: Kind, provider: str, channel: str = '', user=Depends(kind_guard(True))):
    adapter = adapter_or_404(kind, provider, channel)
    mk = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    row = await saved_config(kind, provider, mk)
    out = summary(kind, adapter, row)
    out['credentials_masked'] = adapter.mask_credentials((row or {}).get('credentials'))
    return out


class ProviderSave(Input):
    credentials: dict[str, str] = Field(default_factory=dict)
    config: dict[str, str] = Field(default_factory=dict)
    sandbox: bool = True
    enabled: bool = False


async def locate_config_doc(kind: str, provider: str, messaging_kind: str = ''):
    return await db.provider_configs.find_one({'kind': kind, 'provider': provider, **({'messaging_kind': messaging_kind} if messaging_kind else {})}, {'_id': 0})


@router.put('/{kind}/{provider}', response_model=Doc)
async def save_provider(kind: Kind, provider: str, data: ProviderSave, channel: str = '', user=Depends(kind_guard(False))):
    from core import require_external_actions
    require_external_actions()
    adapter = adapter_or_404(kind, provider, channel)
    messaging_kind = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    row = await locate_config_doc(kind, provider, messaging_kind)
    credentials = {**(row or {}).get('credentials', {})}
    for spec in adapter.config_fields:
        value = (data.credentials or {}).get(spec['key'], '')
        if value != '':
            from vault import seal
            credentials[spec['key']] = seal(value)
        elif spec['required'] and spec['key'] not in credentials:
            raise HTTPException(422, f"{spec['label']} is required")
    config = {**(row or {}).get('config', {}), **{k: str(v)[:500] for k, v in (data.config or {}).items()}}
    status, error, message = (row or {}).get('status', 'not_configured'), (row or {}).get('error', ''), ''
    if data.enabled:
        ok, message = await adapter.validate_config(providers.open_credentials(credentials), data.sandbox)
        if not ok:
            raise HTTPException(422, message)
        status, error = 'connected', ''
    elif credentials:
        status = 'connected' if (row or {}).get('status') == 'connected' else 'not_configured'
    doc = {'id': f'messaging:{messaging_kind}:{provider}' if messaging_kind else f'{kind}:{provider}', 'kind': kind, 'provider': provider,
           'messaging_kind': messaging_kind, 'method_ids': list(getattr(adapter, 'method_ids', [])),
           'enabled': data.enabled, 'sandbox': data.sandbox, 'credentials': credentials, 'config': config,
           'status': 'connected' if data.enabled else (status if credentials else 'not_configured'), 'error': error,
           'last_verified': stamp() if data.enabled else (row or {}).get('last_verified', ''), 'updated_at': stamp()}
    await db.provider_configs.update_one({'kind': kind, 'provider': provider, **({'messaging_kind': messaging_kind} if messaging_kind else {})}, {'$set': doc}, upsert=True)
    await audit(user, f'{kind}_provider.saved', provider, f"enabled={data.enabled} sandbox={data.sandbox} {message}"[:400])
    out = summary(kind, adapter, doc)
    out['credentials_masked'] = adapter.mask_credentials(credentials)
    out['message'] = message
    return out


@router.post('/{kind}/{provider}/verify', response_model=Doc)
async def verify_provider(kind: Kind, provider: str, channel: str = '', user=Depends(kind_guard(False))):
    from core import require_external_actions
    require_external_actions()
    adapter = adapter_or_404(kind, provider, channel)
    messaging_kind = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    row = await locate_config_doc(kind, provider, messaging_kind)
    if not row or not row.get('credentials'):
        raise HTTPException(422, 'Save credentials before testing the connection')
    try:
        ok, message = await adapter.validate_config(providers.open_credentials(row.get('credentials')), row.get('sandbox', True))
    except ProviderError as err:
        ok, message = False, str(err)
    await db.provider_configs.update_one({'kind': kind, 'provider': provider, **({'messaging_kind': messaging_kind} if messaging_kind else {})},
                                         {'$set': {'status': 'connected' if ok else 'error', 'error': '' if ok else message, 'last_verified': stamp()}})
    await audit(user, f'{kind}_provider.verified', provider, message)
    return {'ok': ok, 'message': message, 'status': 'connected' if ok else 'error'}


class InfraAction(Input):
    params: dict = Field(default_factory=dict)


@router.post('/{kind}/{provider}/actions/{action}', response_model=Doc)
async def run_provider_action(kind: Kind, provider: str, action: str, data: InfraAction, user=Depends(kind_guard(False))):
    '''Live infra actions (e.g. Cloudflare purge cache / dev mode). Only declared
    adapter actions are accepted; every call is audited and hits the real API.'''
    from core import require_external_actions
    require_external_actions()
    if kind != 'infra':
        raise HTTPException(404, 'Actions are only available for infrastructure integrations')
    adapter = adapter_or_404(kind, provider)
    if action not in getattr(adapter, 'actions', []):
        raise HTTPException(404, f'This integration has no "{action}" action')
    row = await locate_config_doc(kind, provider)
    if not row or not row.get('credentials') or not row.get('enabled'):
        raise HTTPException(422, 'Connect and enable the integration first')
    try:
        result = await adapter.action(providers.open_credentials(row.get('credentials')), row.get('config', {}), action, data.params)
    except ProviderError as err:
        raise HTTPException(502, str(err))
    await audit(user, f'infra_{action}', provider, str(result.get('message', ''))[:200])
    return {**result, 'action': action}


@router.delete('/{kind}/{provider}', response_model=Doc)
async def disconnect_provider(kind: Kind, provider: str, channel: str = '', user=Depends(kind_guard(False))):
    adapter = adapter_or_404(kind, provider, channel)
    messaging_kind = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    result = await db.provider_configs.delete_one({'kind': kind, 'provider': provider, **({'messaging_kind': messaging_kind} if messaging_kind else {})})
    if not result.deleted_count:
        raise HTTPException(404, 'This provider is not configured')
    await audit(user, f'{kind}_provider.disconnected', provider)
    return {'ok': True}
