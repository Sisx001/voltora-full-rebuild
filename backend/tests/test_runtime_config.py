"""Regression tests for runtime configuration validation."""
import pytest
from runtime_config import read_runtime_settings, ConfigurationError


def test_read_runtime_settings_aggregates_required_names():
    """Valid configuration should return RuntimeSettings with all required fields."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        'OWNER_SETUP_KEY': 'b' * 32,
        'RUNTIME_MODE': 'sandbox',
        'EXTERNAL_ACTIONS_ENABLED': 'false',
    }
    settings = read_runtime_settings(env)
    assert settings.mongo_url == 'mongodb://localhost:27017'
    assert settings.db_name == 'voltora_test'
    assert settings.collection_prefix == 'v1_'
    assert settings.app_origin == 'https://example.com'
    assert settings.runtime_mode == 'sandbox'
    assert settings.external_actions is False


def test_read_runtime_settings_no_secret_leakage_in_error():
    """Configuration errors must not leak secret values in exception messages."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'short',  # Invalid: too short
        'OWNER_SETUP_KEY': 'b' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    error_msg = str(exc.value)
    assert 'short' not in error_msg
    assert 'APP_SECRET' in error_msg
    assert 'at least 32 characters' in error_msg
    assert 'No configuration values have been logged' in error_msg


def test_malformed_mongo_url():
    """Invalid MongoDB URL should raise ConfigurationError."""
    env = {
        'MONGO_URL': 'not-a-valid-url',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'MONGO_URL must be a MongoDB connection URI' in str(exc.value)


def test_invalid_db_name():
    """DB_NAME with invalid characters should raise ConfigurationError."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'invalid name!',  # Spaces and special chars not allowed
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'DB_NAME must contain 1–63 letters, digits, underscores or hyphens' in str(exc.value)


def test_invalid_collection_prefix():
    """Collection prefix must start with letter and contain only valid chars."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': '1_invalid',  # Cannot start with digit
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'REBUILD_COLLECTION_PREFIX must start with a letter' in str(exc.value)


def test_app_origin_must_be_https():
    """APP_ORIGIN must use HTTPS scheme."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'http://example.com',  # HTTP not allowed
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'APP_ORIGIN must contain HTTPS origins only' in str(exc.value)


def test_app_origin_no_credentials():
    """APP_ORIGIN must not contain username or password."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://user:pass@example.com',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'no paths, credentials or wildcards' in str(exc.value)


def test_app_origin_no_path():
    """APP_ORIGIN must not contain path components."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com/path',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'no paths, credentials or wildcards' in str(exc.value)


def test_app_origin_with_query_string():
    """APP_ORIGIN must not contain query strings."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com?param=value',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'no paths, credentials or wildcards' in str(exc.value)


def test_additional_trusted_origins_validation():
    """ADDITIONAL_TRUSTED_ORIGINS must also be HTTPS without paths."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        'ADDITIONAL_TRUSTED_ORIGINS': 'http://bad.com,https://good.com',
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'ADDITIONAL_TRUSTED_ORIGINS must contain HTTPS origins only' in str(exc.value)


def test_runtime_mode_validation():
    """RUNTIME_MODE must be either sandbox or production."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        'RUNTIME_MODE': 'invalid',
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'RUNTIME_MODE must select sandbox or production' in str(exc.value)


def test_external_actions_flag_validation():
    """EXTERNAL_ACTIONS_ENABLED must be true or false."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        'EXTERNAL_ACTIONS_ENABLED': 'yes',  # Must be 'true' or 'false'
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'EXTERNAL_ACTIONS_ENABLED must be true or false' in str(exc.value)


def test_sandbox_external_actions_refusal():
    """External actions must remain false in sandbox mode."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        'RUNTIME_MODE': 'sandbox',
        'EXTERNAL_ACTIONS_ENABLED': 'true',  # Not allowed in sandbox
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'EXTERNAL_ACTIONS_ENABLED must remain false in sandbox' in str(exc.value)


def test_secret_minimum_length():
    """APP_SECRET and OWNER_SETUP_KEY must be at least 32 characters."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'tooshort',
        'OWNER_SETUP_KEY': 'b' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'APP_SECRET must be a fresh private secret of at least 32 characters' in str(exc.value)


def test_secret_placeholder_rejection():
    """Secrets starting with placeholder text should be rejected."""
    for placeholder in ['replace_me_' + 'x' * 20, 'change_this_' + 'x' * 20, 'example_secret_' + 'x' * 20]:
        env = {
            'MONGO_URL': 'mongodb://localhost:27017',
            'DB_NAME': 'voltora_test',
            'REBUILD_COLLECTION_PREFIX': 'v1_',
            'APP_ORIGIN': 'https://example.com',
            'APP_SECRET': placeholder,
            'OWNER_SETUP_KEY': 'b' * 32,
        }
        with pytest.raises(ConfigurationError) as exc:
            read_runtime_settings(env)
        assert 'fresh private secret' in str(exc.value)


def test_valid_production_config_parsing():
    """Valid production configuration should parse successfully."""
    env = {
        'MONGO_URL': 'mongodb+srv://user:pass@cluster.mongodb.net',
        'DB_NAME': 'voltora_prod',
        'REBUILD_COLLECTION_PREFIX': 'v2_',
        'APP_ORIGIN': 'https://shop.example.com',
        'APP_SECRET': 'a' * 48,
        'OWNER_SETUP_KEY': 'b' * 48,
        'RUNTIME_MODE': 'production',
        'EXTERNAL_ACTIONS_ENABLED': 'true',
        'ADDITIONAL_TRUSTED_ORIGINS': 'https://admin.example.com,https://api.example.com',
    }
    settings = read_runtime_settings(env)
    assert settings.runtime_mode == 'production'
    assert settings.external_actions is True
    assert settings.app_origin == 'https://shop.example.com'


def test_missing_required_fields():
    """Missing required fields should raise ConfigurationError."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        # Missing DB_NAME
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'DB_NAME is required' in str(exc.value)


def test_empty_required_fields():
    """Empty required fields should raise ConfigurationError."""
    env = {
        'MONGO_URL': '   ',  # Whitespace only
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
    }
    with pytest.raises(ConfigurationError) as exc:
        read_runtime_settings(env)
    assert 'MONGO_URL is required' in str(exc.value)


def test_trailing_slash_removal():
    """APP_ORIGIN trailing slashes should be stripped."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com/',
        'APP_SECRET': 'a' * 32,
        'RUNTIME_MODE': 'sandbox',
        'EXTERNAL_ACTIONS_ENABLED': 'false',
    }
    settings = read_runtime_settings(env)
    assert settings.app_origin == 'https://example.com'


def test_mongodb_srv_scheme():
    """MongoDB SRV connection strings should be accepted."""
    env = {
        'MONGO_URL': 'mongodb+srv://cluster.mongodb.net',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
    }
    settings = read_runtime_settings(env)
    assert settings.mongo_url == 'mongodb+srv://cluster.mongodb.net'


def test_default_runtime_mode():
    """RUNTIME_MODE should default to sandbox if not specified."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        # RUNTIME_MODE not specified
    }
    settings = read_runtime_settings(env)
    assert settings.runtime_mode == 'sandbox'


def test_default_external_actions():
    """EXTERNAL_ACTIONS_ENABLED should default to false."""
    env = {
        'MONGO_URL': 'mongodb://localhost:27017',
        'DB_NAME': 'voltora_test',
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': 'https://example.com',
        'APP_SECRET': 'a' * 32,
        # EXTERNAL_ACTIONS_ENABLED not specified
    }
    settings = read_runtime_settings(env)
    assert settings.external_actions is False
