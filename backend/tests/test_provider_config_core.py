"""Core provider configuration tests with in-memory test doubles (no real DB or network)."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from provider_configuration import (
    ConfigurationSave,
    ConnectionCheck,
    check_connection,
    config_key,
    describe,
    query_for,
    read_config,
    required_missing,
    save_configuration,
)
from providers_admin import (
    adapter_or_404,
    disconnect_provider,
    save_provider,
)


class MockAdapter:
    """Test double adapter for provider configuration tests."""
    def __init__(self, provider_id='stripe', label='Stripe'):
        self.id = provider_id
        self.label = label
        self.docs_url = f'https://docs.{provider_id}.com'
        self.method_ids = ['card', 'wallet']
        self.supports_refund = True
        self.supports_webhook = True
        self.config_fields = [
            {'key': 'api_key', 'label': 'API Key', 'required': True, 'type': 'password'},
            {'key': 'secret_key', 'label': 'Secret Key', 'required': True, 'type': 'password'},
        ]
        self.settings_fields = [
            {'key': 'webhook_url', 'label': 'Webhook URL', 'type': 'url'},
        ]

    def mask_credentials(self, credentials):
        return {k: '***' if v else '' for k, v in credentials.items()}

    async def validate_config(self, credentials, is_sandbox):
        """Test double - returns success without real API call."""
        if credentials.get('api_key') == 'fail':
            return False, 'Connection failed'
        return True, 'Connected'


class FakeCollection:
    """In-memory collection fake supporting exact query operators/update CAS/duplicate UUID."""
    def __init__(self):
        self.docs = {}
        self.next_id = 1

    async def find_one(self, query, projection=None):
        # Match documents by query
        for doc in self.docs.values():
            if self._matches(doc, query):
                result = doc.copy()
                if projection and '_id' in projection and projection['_id'] == 0:
                    result.pop('_id', None)
                return result
        return None

    async def insert_one(self, doc):
        doc_id = doc.get('id')
        if doc_id in self.docs:
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError('Duplicate key error')
        doc['_id'] = self.next_id
        self.next_id += 1
        self.docs[doc_id] = doc.copy()
        return MagicMock(inserted_id=doc['_id'])

    async def update_one(self, query, update):
        for doc in self.docs.values():
            if self._matches(doc, query):
                # Apply $set
                if '$set' in update:
                    doc.update(update['$set'])
                # Apply $inc
                if '$inc' in update:
                    for key, value in update['$inc'].items():
                        doc[key] = doc.get(key, 0) + value
                # Apply $unset
                if '$unset' in update:
                    for key in update['$unset']:
                        doc.pop(key, None)
                # Apply $push
                if '$push' in update:
                    for key, value in update['$push'].items():
                        if '$each' in value:
                            items = value['$each']
                            slice_val = value.get('$slice', None)
                            if key not in doc:
                                doc[key] = []
                            doc[key].extend(items)
                            if slice_val and slice_val < 0:
                                doc[key] = doc[key][slice_val:]
                        else:
                            if key not in doc:
                                doc[key] = []
                            doc[key].append(value)
                return MagicMock(matched_count=1, modified_count=1)
        return MagicMock(matched_count=0, modified_count=0)

    async def delete_many(self, query):
        to_delete = [doc_id for doc_id, doc in self.docs.items() if self._matches(doc, query)]
        for doc_id in to_delete:
            del self.docs[doc_id]
        return MagicMock(deleted_count=len(to_delete))

    def _matches(self, doc, query):
        for key, value in query.items():
            if key == '$or':
                if not any(self._matches(doc, sub_query) for sub_query in value):
                    return False
            elif key.startswith('$'):
                continue
            elif isinstance(value, dict):
                if '$ne' in value:
                    if doc.get(key) == value['$ne']:
                        return False
                elif '$lt' in value:
                    if not (key in doc and doc[key] < value['$lt']):
                        return False
                elif '$exists' in value:
                    if value['$exists'] and key not in doc:
                        return False
                    if not value['$exists'] and key in doc:
                        return False
                else:
                    if doc.get(key) != value:
                        return False
            else:
                if doc.get(key) != value:
                    return False
        return True


@pytest.fixture
def fake_db():
    """Fake database with in-memory collections."""
    class FakeDB:
        def __init__(self):
            self.provider_configs = FakeCollection()
            self.audit_logs = FakeCollection()

        def __getitem__(self, name):
            if name == 'provider_configs':
                return self.provider_configs
            elif name == 'audit_logs':
                return self.audit_logs
            return FakeCollection()

        def __getattr__(self, name):
            return self[name]

    return FakeDB()


@pytest.fixture
def mock_user():
    """Test user fixture."""
    return {
        'id': 'test-owner-id',
        'email': 'owner@test.com',
        'role': 'owner',
        'mfa_verified': True,
    }


@pytest.fixture
def mock_adapter():
    """Mock adapter fixture."""
    return MockAdapter()


# Test: Mock provider rejection

def test_adapter_or_404_rejects_mock_provider():
    """Mock provider should return 404, not be operational."""
    with pytest.raises(HTTPException) as exc:
        adapter_or_404('payment', 'mock')
    assert exc.value.status_code == 404
    assert 'Test doubles are not operational providers' in str(exc.value.detail)


def test_adapter_or_404_rejects_mock_courier():
    """Mock courier should return 404."""
    with pytest.raises(HTTPException) as exc:
        adapter_or_404('courier', 'mock')
    assert exc.value.status_code == 404


def test_adapter_or_404_rejects_mock_messaging():
    """Mock messaging should return 404."""
    with pytest.raises(HTTPException) as exc:
        adapter_or_404('messaging', 'mock', 'sms')
    assert exc.value.status_code == 404


# Test: Configuration key generation

def test_config_key_deterministic():
    """Config key should be deterministic UUID5 for concurrent first-save handling."""
    key1 = config_key('payment', 'stripe', '', 'sandbox')
    key2 = config_key('payment', 'stripe', '', 'sandbox')
    assert key1 == key2
    assert isinstance(uuid.UUID(key1), uuid.UUID)


def test_config_key_different_environments():
    """Different environments should generate different keys."""
    sandbox_key = config_key('payment', 'stripe', '', 'sandbox')
    prod_key = config_key('payment', 'stripe', '', 'production')
    assert sandbox_key != prod_key


# Test: Query generation

def test_query_for_sandbox():
    """Query should filter for sandbox environment."""
    query = query_for('payment', 'stripe', '', 'sandbox')
    assert query['kind'] == 'payment'
    assert query['provider'] == 'stripe'
    assert query['sandbox'] == {'$ne': False}


def test_query_for_production():
    """Query should filter for production environment."""
    query = query_for('payment', 'stripe', '', 'production')
    assert query['sandbox'] is False


# Test: Save configuration

@pytest.mark.asyncio
async def test_save_configuration_first_save(fake_db, mock_adapter, mock_user):
    """First save should create new configuration with version 1."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()):
        data = ConfigurationSave(
            credentials={'api_key': 'test-key', 'secret_key': 'test-secret'},
            config={'webhook_url': 'https://example.com/webhook'},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        
        result = await save_configuration('payment', mock_adapter, '', data, mock_user)
        
        assert result['version'] == 1
        assert result['configured'] is True
        assert result['enabled'] is False
        assert result['environment'] == 'sandbox'
        assert 'Configuration saved locally' in result['message']
        assert 'No provider request was sent' in result['message']


@pytest.mark.asyncio
async def test_save_configuration_increments_version(fake_db, mock_adapter, mock_user):
    """Subsequent saves should increment version."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()):
        data1 = ConfigurationSave(
            credentials={'api_key': 'key1', 'secret_key': 'secret1'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        result1 = await save_configuration('payment', mock_adapter, '', data1, mock_user)
        assert result1['version'] == 1
        
        data2 = ConfigurationSave(
            credentials={'api_key': 'key2'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=1,
        )
        result2 = await save_configuration('payment', mock_adapter, '', data2, mock_user)
        assert result2['version'] == 2


@pytest.mark.asyncio
async def test_save_configuration_version_conflict(fake_db, mock_adapter, mock_user):
    """Should reject save with stale expected_version."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()):
        data1 = ConfigurationSave(
            credentials={'api_key': 'key1', 'secret_key': 'secret1'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        await save_configuration('payment', mock_adapter, '', data1, mock_user)
        
        data2 = ConfigurationSave(
            credentials={'api_key': 'key2'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,  # Stale version
        )
        
        with pytest.raises(HTTPException) as exc:
            await save_configuration('payment', mock_adapter, '', data2, mock_user)
        assert exc.value.status_code == 409
        assert 'Configuration changed' in str(exc.value.detail)


@pytest.mark.asyncio
async def test_save_configuration_seals_credentials(fake_db, mock_adapter, mock_user):
    """Credentials should be sealed (encrypted) at rest."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        data = ConfigurationSave(
            credentials={'api_key': 'plaintext-key', 'secret_key': 'plaintext-secret'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        
        await save_configuration('payment', mock_adapter, '', data, mock_user)
        
        row = await fake_db.provider_configs.find_one({'provider': 'stripe'})
        assert row is not None
        # Sealed credentials should not be plaintext
        assert row['credentials']['api_key'] == 'sealed:plaintext-key'
        assert row['credentials']['secret_key'] == 'sealed:plaintext-secret'


@pytest.mark.asyncio
async def test_save_configuration_clear_credentials(fake_db, mock_adapter, mock_user):
    """clear_credentials should remove specified fields."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        data1 = ConfigurationSave(
            credentials={'api_key': 'key1', 'secret_key': 'secret1'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        await save_configuration('payment', mock_adapter, '', data1, mock_user)
        
        data2 = ConfigurationSave(
            credentials={},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=1,
            clear_credentials=['secret_key'],
        )
        await save_configuration('payment', mock_adapter, '', data2, mock_user)
        
        row = await fake_db.provider_configs.find_one({'provider': 'stripe'})
        assert 'secret_key' not in row['credentials']
        assert 'api_key' in row['credentials']


@pytest.mark.asyncio
async def test_save_configuration_rejects_unknown_fields(fake_db, mock_adapter, mock_user):
    """Should reject unknown credential fields."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()):
        data = ConfigurationSave(
            credentials={'unknown_field': 'value'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        
        with pytest.raises(HTTPException) as exc:
            await save_configuration('payment', mock_adapter, '', data, mock_user)
        assert exc.value.status_code == 422
        assert 'Unknown credential field' in str(exc.value.detail)


@pytest.mark.asyncio
async def test_save_configuration_separate_environments(fake_db, mock_adapter, mock_user):
    """Sandbox and production should have separate configurations."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        sandbox_data = ConfigurationSave(
            credentials={'api_key': 'sandbox-key', 'secret_key': 'sandbox-secret'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        sandbox_result = await save_configuration('payment', mock_adapter, '', sandbox_data, mock_user)
        
        prod_data = ConfigurationSave(
            credentials={'api_key': 'prod-key', 'secret_key': 'prod-secret'},
            config={},
            sandbox=False,
            enabled=False,
            expected_version=0,
        )
        prod_result = await save_configuration('payment', mock_adapter, '', prod_data, mock_user)
        
        assert sandbox_result['version'] == 1
        assert prod_result['version'] == 1
        assert sandbox_result['environment'] == 'sandbox'
        assert prod_result['environment'] == 'production'


@pytest.mark.asyncio
async def test_save_configuration_enable_requires_external_actions(fake_db, mock_adapter, mock_user):
    """Enabling provider should require external actions (403)."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('core.EXTERNAL_ACTIONS', False):
        data = ConfigurationSave(
            credentials={'api_key': 'key', 'secret_key': 'secret'},
            config={},
            sandbox=True,
            enabled=True,  # Try to enable
            expected_version=0,
        )
        
        with pytest.raises(HTTPException) as exc:
            await save_configuration('payment', mock_adapter, '', data, mock_user)
        assert exc.value.status_code == 403
        assert 'External actions are unavailable' in str(exc.value.detail)


@pytest.mark.asyncio
async def test_save_configuration_no_outbound_calls(fake_db, mock_adapter, mock_user):
    """Save should not make any outbound provider calls."""
    call_count = 0
    
    original_validate = mock_adapter.validate_config
    async def track_calls(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_validate(*args, **kwargs)
    
    mock_adapter.validate_config = track_calls
    
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        data = ConfigurationSave(
            credentials={'api_key': 'key', 'secret_key': 'secret'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        await save_configuration('payment', mock_adapter, '', data, mock_user)
        
        assert call_count == 0


# Test: DELETE endpoint

@pytest.mark.asyncio
async def test_disconnect_provider_disables_non_destructively(fake_db, mock_adapter, mock_user):
    """DELETE should disable provider without destroying credentials."""
    with patch('provider_configuration.db', fake_db), \
         patch('providers_admin.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('providers_admin.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        data = ConfigurationSave(
            credentials={'api_key': 'key', 'secret_key': 'secret'},
            config={'webhook_url': 'https://example.com/webhook'},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        await save_configuration('payment', mock_adapter, '', data, mock_user)
        
        result = await disconnect_provider('payment', 'stripe', 1, '', 'sandbox', mock_user)
        
        assert result['ok'] is True
        assert 'Disabled' in result['message']
        assert 'Credentials and history retained' in result['message']
        
        row = await fake_db.provider_configs.find_one({'provider': 'stripe'})
        assert row['enabled'] is False
        assert 'api_key' in row['credentials']
        assert 'secret_key' in row['credentials']


@pytest.mark.asyncio
async def test_disconnect_provider_requires_expected_version(fake_db, mock_adapter, mock_user):
    """DELETE should require expected_version."""
    with patch('provider_configuration.db', fake_db), \
         patch('providers_admin.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('providers_admin.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        data = ConfigurationSave(
            credentials={'api_key': 'key', 'secret_key': 'secret'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        await save_configuration('payment', mock_adapter, '', data, mock_user)
        
        with pytest.raises(HTTPException) as exc:
            await disconnect_provider('payment', 'stripe', 999, '', 'sandbox', mock_user)
        assert exc.value.status_code == 409
        assert 'Configuration changed' in str(exc.value.detail)


@pytest.mark.asyncio
async def test_describe_masks_credentials(fake_db, mock_adapter, mock_user):
    """describe() should mask credentials (write-only)."""
    with patch('provider_configuration.db', fake_db), \
         patch('provider_configuration.audit', AsyncMock()), \
         patch('provider_configuration.seal', side_effect=lambda x: f'sealed:{x}'):
        data = ConfigurationSave(
            credentials={'api_key': 'secret-key-value', 'secret_key': 'secret-value'},
            config={},
            sandbox=True,
            enabled=False,
            expected_version=0,
        )
        await save_configuration('payment', mock_adapter, '', data, mock_user)
        
        row = await fake_db.provider_configs.find_one({'provider': 'stripe'})
        result = describe('payment', mock_adapter, row, 'sandbox')
        
        assert result['credentials_masked']['api_key'] == '***'
        assert result['credentials_masked']['secret_key'] == '***'
