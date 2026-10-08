'''Admin management of provider integrations (payment gateways, couriers,
messaging channels). Credentials are write-only: they are sealed at rest and
never returned - the API reports which fields are configured, not their values.
'''
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from core import db, Doc, Input, stamp, audit
from permissions import authorize
from auth import current_user
import providers
from providers import ProviderError
from provider_configuration import (
    ConfigurationSave as ProviderSave, ConnectionCheck, Environment,
    read_config, describe, save_configuration, check_connection, revision_match,
)

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
        if not read and user.get('role') != 'owner':
            raise HTTPException(403, 'Only the owner may manage integration credentials or checks')
        return user
    return dependency


def adapter_or_404(kind: str, provider: str, channel: str = ''):
    if provider == 'mock':
        raise HTTPException(404, 'Test doubles are not operational providers')
    if kind == 'messaging' and channel and channel not in ('sms', 'email'):
        raise HTTPException(422, 'Unknown messaging channel')
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
async def list_providers(kind: Kind, environment: Environment = 'sandbox', user=Depends(kind_guard(True))):
    adapters = providers.registry(kind).values()
    out = []
    for cls in adapters:
        adapter = cls()
        if adapter.id == 'mock':
            continue
        channel = getattr(adapter, 'kind', '') if kind == 'messaging' else ''
        row = await read_config(kind, adapter.id, channel, environment)
        out.append(describe(kind, adapter, row, environment))
    return out


@router.get('/{kind}/{provider}', response_model=Doc)
async def provider_detail(kind: Kind, provider: str, channel: str = '', environment: Environment = 'sandbox', user=Depends(kind_guard(True))):
    adapter = adapter_or_404(kind, provider, channel)
    mk = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    return describe(kind, adapter, await read_config(kind, provider, mk, environment), environment)


async def locate_config_doc(kind: str, provider: str, messaging_kind: str = '', environment: Environment = 'sandbox'):
    return await read_config(kind, provider, messaging_kind, environment)


@router.put('/{kind}/{provider}', response_model=Doc)
async def save_provider(kind: Kind, provider: str, data: ProviderSave, channel: str = '', user=Depends(kind_guard(False))):
    adapter = adapter_or_404(kind, provider, channel)
    mk = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    return await save_configuration(kind, adapter, mk, data, user)


@router.post('/{kind}/{provider}/verify', response_model=Doc)
async def verify_provider(kind: Kind, provider: str, data: ConnectionCheck, channel: str = '', environment: Environment = 'sandbox', user=Depends(kind_guard(False))):
    adapter = adapter_or_404(kind, provider, channel)
    mk = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    return await check_connection(kind, adapter, mk, environment, data, user)


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
async def disconnect_provider(kind: Kind, provider: str, expected_version: int, channel: str = '', environment: Environment = 'sandbox', user=Depends(kind_guard(False))):
    adapter = adapter_or_404(kind, provider, channel)
    mk = messaging_channel(adapter, channel) if kind == 'messaging' else ''
    row = await read_config(kind, provider, mk, environment)
    if not row:
        raise HTTPException(404, 'This provider is not configured')
    if row.get('version', 0) != expected_version:
        raise HTTPException(409, 'Configuration changed. Reload before disabling.')
    result = await db.provider_configs.update_one({'id': row['id'], **revision_match(row)},
        {'$set': {'enabled': False, 'updated_at': stamp()}, '$inc': {'version': 1},
         '$push': {'history': {'$each': [{'action': 'disabled', 'at': stamp(), 'version': expected_version + 1}], '$slice': -100}}})
    if not result.matched_count:
        raise HTTPException(409, 'Configuration changed during disable.')
    await audit(user, f'{kind}_provider.disabled', provider, f'environment={environment}')
    return {'ok': True, 'message': 'Disabled. Credentials and history retained for review.'}
