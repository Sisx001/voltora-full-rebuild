"""Local-only versioned provider configuration; no save-time external requests."""
import asyncio
import uuid
from typing import Literal

from fastapi import HTTPException
from pydantic import Field
from pymongo.errors import DuplicateKeyError

import providers
from core import Input, audit, db, stamp
from vault import seal

Environment = Literal['sandbox', 'production']

# Source-reviewed connection probes only. This is NOT workflow verification.
# Providers not listed cannot be probed through this surface until reviewed.
SANDBOX_PROBES = {'stripe', 'paypal', 'bkash', 'pathao', 'redx'}
NO_SANDBOX = {'smtp', 'steadfast', 'telegram', 'cloudflare'}


class ConfigurationSave(Input):
    credentials: dict[str, str] = Field(default_factory=dict)
    config: dict[str, str] = Field(default_factory=dict)
    sandbox: bool = True
    enabled: bool = False
    expected_version: int = Field(default=0, ge=0)
    clear_credentials: list[str] = Field(default_factory=list)


class ConnectionCheck(Input):
    expected_version: int = Field(ge=1)
    confirmation: Literal['CHECK CONNECTION']


def config_key(kind, provider, channel, environment):
    # Deterministic UUID makes first-insert races conflict on the existing id index.
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'voltora:{kind}:{provider}:{channel}:{environment}'))


def query_for(kind, provider, channel, environment):
    query = {'kind': kind, 'provider': provider}
    if channel:
        query['messaging_kind'] = channel
    query['sandbox'] = {'$ne': False} if environment == 'sandbox' else False
    return query


async def read_config(kind, provider, channel, environment):
    return await db.provider_configs.find_one(query_for(kind, provider, channel, environment), {'_id': 0})


def required_missing(adapter, credentials):
    return [f['key'] for f in adapter.config_fields if f.get('required') and not credentials.get(f['key'])]


def describe(kind, adapter, row, environment):
    import core
    row = row or {}
    credentials = row.get('credentials', {})
    missing = required_missing(adapter, credentials)
    legacy = bool(row and row.get('schema_version') != 2)
    return {
        'id': adapter.id, 'kind': kind, 'messaging_kind': getattr(adapter, 'kind', ''),
        'label': adapter.label, 'docs_url': adapter.docs_url,
        'method_ids': list(getattr(adapter, 'method_ids', [])),
        'supports_refund': bool(getattr(adapter, 'supports_refund', False)),
        'supports_webhook': bool(getattr(adapter, 'supports_webhook', False)),
        'actions': list(getattr(adapter, 'actions', [])),
        'credentials_spec': adapter.config_fields, 'settings_spec': adapter.settings_fields,
        'credentials_masked': adapter.mask_credentials(credentials),
        'configured': bool(credentials), 'credentials_complete': bool(credentials) and not missing,
        'missing_fields': missing, 'enabled': bool(row.get('enabled')), 'sandbox': environment == 'sandbox',
        'environment': environment, 'config': row.get('config', {}), 'version': row.get('version', 0),
        'implementation': 'adapter_present_workflow_unverified',
        'status': 'legacy_review_required' if legacy else row.get('status', 'not_configured'),
        'connection': row.get('connection', {'status': 'unverified'}),
        'workflow': row.get('workflow', {'status': 'unverified'}),
        'health': row.get('health', {'status': 'unknown'}),
        'error': row.get('error', ''), 'last_verified': row.get('last_verified', ''),
        'external_actions_enabled': core.EXTERNAL_ACTIONS,
        'runtime_mode': core.RUNTIME_MODE,
        'connection_check_supported': adapter.id in SANDBOX_PROBES and environment == 'sandbox',
        'sandbox_support': 'available' if adapter.id in SANDBOX_PROBES else 'not_available' if adapter.id in NO_SANDBOX else 'not_reviewed',
        'setup_note': ('Use a dedicated test account. This provider has no general sandbox; controlled verification requires separate approval.'
                       if adapter.id in NO_SANDBOX else 'Save credentials for this environment. A connection check is not an end-to-end workflow test.'),
        'activation_blocker': 'Production activation is a separate owner-reviewed action. Workflow evidence is required.',
        'history': row.get('history', [])[-20:],
    }


def revision_match(row):
    return {'version': row['version']} if 'version' in row else {'version': {'$exists': False}}


async def save_configuration(kind, adapter, channel, data, user):
    environment = 'sandbox' if data.sandbox else 'production'
    row = await read_config(kind, adapter.id, channel, environment)
    current_version = (row or {}).get('version', 0)
    if data.expected_version != current_version:
        raise HTTPException(409, 'Configuration changed. Reload the selected environment before saving.')
    allowed = {f['key'] for f in adapter.config_fields}
    if (set(data.credentials) | set(data.clear_credentials)) - allowed:
        raise HTTPException(422, 'Unknown credential field')
    setting_keys = {f['key'] for f in adapter.settings_fields}
    if set(data.config) - setting_keys:
        raise HTTPException(422, 'Unknown configuration field')
    if any(len(v) > 8000 for v in data.credentials.values()) or any(len(v) > 500 for v in data.config.values()):
        raise HTTPException(422, 'Configuration field exceeds its size limit')
    credentials = dict((row or {}).get('credentials', {}))
    for key in data.clear_credentials:
        credentials.pop(key, None)
    rotated = bool(data.clear_credentials)
    for key, value in data.credentials.items():
        if value:
            credentials[key] = seal(value)
            rotated = True
    config = {**(row or {}).get('config', {}), **data.config}
    changed = not row or rotated or config != row.get('config', {})
    if data.enabled:
        # Save is never an external verification or a way around activation.
        import core
        core.require_external_actions()
        if environment == 'production' and core.RUNTIME_MODE != 'production':
            raise HTTPException(403, 'Production actions are unavailable in this runtime')
        workflow = (row or {}).get('workflow', {})
        if changed or workflow.get('status') != 'verified' or workflow.get('version') != current_version:
            raise HTTPException(409, 'Verify this exact configuration with a controlled end-to-end workflow before enabling.')
    version = current_version + 1
    connection = {'status': 'unverified'} if changed else (row or {}).get('connection', {'status': 'unverified'})
    workflow = {'status': 'unverified'} if changed else (row or {}).get('workflow', {'status': 'unverified'})
    # Unchanged settings retain evidence against the newly reviewed version.
    if not changed:
        connection = {**connection, **({'version': version} if connection.get('version') == current_version else {})}
        workflow = {**workflow, **({'version': version} if workflow.get('version') == current_version else {})}
    event = {'version': version, 'action': 'credentials_rotated' if rotated else 'configuration_saved',
             'at': stamp(), 'actor_id': user['id']}
    doc = {'id': (row or {}).get('id') or config_key(kind, adapter.id, channel, environment),
           'kind': kind, 'provider': adapter.id, 'messaging_kind': channel, 'sandbox': data.sandbox,
           'schema_version': 2, 'version': version, 'method_ids': list(getattr(adapter, 'method_ids', [])),
           'credentials': credentials, 'config': config, 'enabled': data.enabled,
           'status': 'connected' if data.enabled else 'configured' if credentials else 'not_configured',
           'connection': connection, 'workflow': workflow, 'health': {'status': 'unknown'},
           'error': '', 'last_verified': '' if changed else (row or {}).get('last_verified', ''),
           'updated_at': stamp(), 'history': ((row or {}).get('history', []) + [event])[-100:]}
    try:
        if row:
            result = await db.provider_configs.update_one({'id': row['id'], **revision_match(row)}, {'$set': doc})
            if not result.matched_count:
                raise HTTPException(409, 'Configuration changed during save. Reload before retrying.')
        else:
            await db.provider_configs.insert_one(doc.copy())
    except DuplicateKeyError:
        raise HTTPException(409, 'Configuration was created concurrently. Reload before saving.') from None
    await audit(user, 'integration.configuration_saved', doc['id'], f'environment={environment}; version={version}; enabled={data.enabled}')
    return {**describe(kind, adapter, doc, environment), 'message': 'Configuration saved locally. No provider request was sent.'}


async def check_connection(kind, adapter, channel, environment, data, user):
    if environment != 'sandbox' or adapter.id not in SANDBOX_PROBES:
        raise HTTPException(409, 'No reviewed sandbox connection check is available. See provider setup dependencies.')
    row = await read_config(kind, adapter.id, channel, environment)
    if not row or row.get('schema_version') != 2 or row.get('version') != data.expected_version:
        raise HTTPException(409, 'Save and reload this configuration version before checking.')
    if required_missing(adapter, row.get('credentials', {})):
        raise HTTPException(422, 'Complete required credentials before checking the connection.')
    # Atomic lease prevents overlapping probes for the same version. It is not a
    # permission to create charges/messages/shipments and never enables a provider.
    from datetime import timedelta
    from core import now
    lease = str(uuid.uuid4())
    claimed = await db.provider_configs.update_one(
        {'id': row['id'], 'version': data.expected_version,
         '$or': [{'check_until': {'$exists': False}}, {'check_until': {'$lt': stamp()}}]},
        {'$set': {'check_lease': lease, 'check_until': (now() + timedelta(seconds=60)).isoformat()}})
    if not claimed.matched_count:
        raise HTTPException(409, 'A connection check is already in progress. Wait before retrying.')
    try:
        ok, _ = await asyncio.wait_for(adapter.validate_config(providers.open_credentials(row['credentials']), True), timeout=25)
        ok = ok is True
    except Exception:
        ok = False
    # Never persist provider-supplied text: it may contain URLs, keys or bodies.
    message = ('Sandbox connection accepted. End-to-end workflow and delivery remain unverified.' if ok
               else 'Sandbox connection failed. Check credentials, provider access and service availability.')
    evidence = {'status': 'verified' if ok else 'failed', 'version': data.expected_version,
                'environment': environment, 'at': stamp(), 'scope': 'connection_only'}
    result = await db.provider_configs.update_one(
        {'id': row['id'], 'version': data.expected_version, 'check_lease': lease},
        {'$set': {'connection': evidence, 'last_verified': evidence['at'], 'error': '' if ok else message},
         '$unset': {'check_lease': '', 'check_until': ''},
         '$push': {'history': {'$each': [{'action': 'connection_checked', 'version': data.expected_version,
                                         'at': evidence['at'], 'actor_id': user['id'], 'result': evidence['status']}], '$slice': -100}}})
    if not result.matched_count:
        raise HTTPException(409, 'Configuration changed during the check. The result was discarded.')
    await audit(user, 'integration.connection_checked', row['id'], f'version={data.expected_version}; result={evidence["status"]}')
    return {'ok': ok, 'message': message, 'connection': evidence, 'workflow': {'status': 'unverified'}, 'enabled': False}
