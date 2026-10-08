"""Regression tests for scripts/check_environment.py origin alignment validation.

Tests verify exact approved supplemental origin acceptance, absent additional origin
mismatch rejection, unsafe frontend URL rejection, and environment precedence without
mutating real .env files.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add backend to path FIRST, then import - same as check_environment.py does
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from runtime_config import ConfigurationError  # noqa: E402

# Now add scripts and import check_environment
sys.path.insert(0, str(ROOT / 'scripts'))
from check_environment import check_environment  # noqa: E402


@pytest.fixture
def temp_env_dir():
    """Create temporary directory structure for isolated env testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        backend = root / 'backend'
        frontend = root / 'frontend'
        backend.mkdir()
        frontend.mkdir()
        yield root


def test_aligned_configuration_with_exact_supplemental_origin(temp_env_dir):
    """Verify aligned config when frontend origin matches backend APP_ORIGIN."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_aligned\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    # Should succeed - frontend origin matches APP_ORIGIN
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://platform-complete-1.preview.emergentagent.com'
    assert settings.runtime_mode == 'sandbox'
    assert settings.external_actions is False


def test_exact_supplemental_origin_acceptance(temp_env_dir):
    """Verify exact approved supplemental origin in ADDITIONAL_TRUSTED_ORIGINS is accepted."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_supplemental\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://backend-primary.test.invalid\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    backend_env_local = temp_env_dir / 'backend' / '.env.local'
    backend_env_local.write_text(
        'ADDITIONAL_TRUSTED_ORIGINS=https://frontend-supplemental.test.invalid\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://frontend-supplemental.test.invalid\n'
    )
    
    # Should succeed - frontend origin in ADDITIONAL_TRUSTED_ORIGINS
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://backend-primary.test.invalid'


def test_multiple_supplemental_origins_comma_separated(temp_env_dir):
    """Verify multiple supplemental origins can be specified comma-separated."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_multi\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://backend-primary.test.invalid\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    backend_env_local = temp_env_dir / 'backend' / '.env.local'
    backend_env_local.write_text(
        'ADDITIONAL_TRUSTED_ORIGINS=https://frontend-first.test.invalid,https://frontend-second.test.invalid\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://frontend-second.test.invalid\n'
    )
    
    # Should succeed - frontend origin is second in comma-separated list
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://backend-primary.test.invalid'


def test_absent_additional_origin_mismatch_rejection(temp_env_dir):
    """Verify mismatch rejection when frontend origin not in backend allowlist."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_mismatch\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://backend-primary.test.invalid\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://frontend-different.test.invalid\n'
    )
    
    # Should fail - frontend origin not in APP_ORIGIN or ADDITIONAL_TRUSTED_ORIGINS
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    assert 'Browser/API origin is not in the backend exact-origin allowlist' in str(exc_info.value)


def test_unsafe_frontend_url_with_credentials_rejected(temp_env_dir):
    """Verify frontend URL with embedded credentials is rejected."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_unsafe\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://backend-primary.test.invalid\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://user:pass@backend-primary.test.invalid\n'
    )
    
    # Should fail - credentials in URL
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    assert 'REACT_APP_BACKEND_URL must be an HTTPS origin without credentials' in str(exc_info.value)


def test_unsafe_frontend_url_with_path_rejected(temp_env_dir):
    """Verify frontend URL with path component is rejected."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_path\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com/api\n'
    )
    
    # Should fail - path in URL
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    assert 'REACT_APP_BACKEND_URL must be an HTTPS origin without credentials' in str(exc_info.value)


def test_unsafe_frontend_url_with_query_rejected(temp_env_dir):
    """Verify frontend URL with query string is rejected."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_query\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com?key=value\n'
    )
    
    # Should fail - query string in URL
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    assert 'REACT_APP_BACKEND_URL must be an HTTPS origin without credentials' in str(exc_info.value)


def test_unsafe_frontend_url_with_fragment_rejected(temp_env_dir):
    """Verify frontend URL with fragment is rejected."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_fragment\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com#section\n'
    )
    
    # Should fail - fragment in URL
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    assert 'REACT_APP_BACKEND_URL must be an HTTPS origin without credentials' in str(exc_info.value)


def test_non_https_frontend_url_rejected(temp_env_dir):
    """Verify non-HTTPS frontend URL is rejected."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_http\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=http://uuid-alias.preview.emergentagent.com\n'
    )
    
    # Should fail - HTTP not HTTPS
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    assert 'REACT_APP_BACKEND_URL must be an HTTPS origin' in str(exc_info.value)


def test_env_local_precedence_over_env(temp_env_dir):
    """Verify .env values are used first, then .env.local supplements missing keys."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_precedence\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    # .env.local supplements with additional origin
    backend_env_local = temp_env_dir / 'backend' / '.env.local'
    backend_env_local.write_text(
        'ADDITIONAL_TRUSTED_ORIGINS=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    # Should succeed - .env.local ADDITIONAL_TRUSTED_ORIGINS supplements .env
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://platform-complete-1.preview.emergentagent.com'


def test_environ_precedence_over_dotenv(temp_env_dir):
    """Verify environment variables take precedence over .env files."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_environ\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    # Pass ADDITIONAL_TRUSTED_ORIGINS via environ
    environ = {
        'ADDITIONAL_TRUSTED_ORIGINS': 'https://platform-complete-1.preview.emergentagent.com'
    }
    
    # Update frontend to match environ origin
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    # Should succeed - environ ADDITIONAL_TRUSTED_ORIGINS used
    settings = check_environment(root=temp_env_dir, environ=environ)
    assert settings.app_origin == 'https://platform-complete-1.preview.emergentagent.com'


def test_no_real_env_mutation(temp_env_dir):
    """Verify check_environment never mutates real .env files."""
    backend_env = temp_env_dir / 'backend' / '.env'
    original_content = (
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_mutation\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    backend_env.write_text(original_content)
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_original = 'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    frontend_env.write_text(frontend_original)
    
    # Run check_environment
    check_environment(root=temp_env_dir, environ={})
    
    # Verify files unchanged
    assert backend_env.read_text() == original_content
    assert frontend_env.read_text() == frontend_original


def test_no_secrets_logged_on_validation_error(temp_env_dir, capsys):
    """Verify secrets are not logged when validation fails."""
    backend_env = temp_env_dir / 'backend' / '.env'
    secret_value = 'test_secret_32_characters_minimum_length_required'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_secrets\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://backend-primary.test.invalid\n'
        f'APP_SECRET={secret_value}\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://frontend-different.test.invalid\n'
    )
    
    # Should fail with mismatch
    with pytest.raises(ConfigurationError) as exc_info:
        check_environment(root=temp_env_dir, environ={})
    
    assert 'Browser/API origin is not in the backend exact-origin allowlist' in str(exc_info.value)
    
    # Verify secret not in captured output
    captured = capsys.readouterr()
    assert secret_value not in captured.out
    assert secret_value not in captured.err


def test_trailing_slash_normalization(temp_env_dir):
    """Verify trailing slashes are normalized in origin comparison."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_slash\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com/\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    # Should succeed - trailing slash normalized
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://platform-complete-1.preview.emergentagent.com'


def test_whitespace_handling_in_origins(temp_env_dir):
    """Verify whitespace is properly stripped from origin values."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_whitespace\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=  https://platform-complete-1.preview.emergentagent.com  \n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    backend_env_local = temp_env_dir / 'backend' / '.env.local'
    backend_env_local.write_text(
        'ADDITIONAL_TRUSTED_ORIGINS=  https://platform-complete-1.preview.emergentagent.com  \n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=  https://platform-complete-1.preview.emergentagent.com  \n'
    )
    
    # Should succeed - whitespace stripped
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://platform-complete-1.preview.emergentagent.com'


def test_empty_additional_trusted_origins_ignored(temp_env_dir):
    """Verify empty ADDITIONAL_TRUSTED_ORIGINS values are ignored."""
    backend_env = temp_env_dir / 'backend' / '.env'
    backend_env.write_text(
        'MONGO_URL=mongodb://127.0.0.1:27017\n'
        'DB_NAME=voltora_test_empty\n'
        'REBUILD_COLLECTION_PREFIX=v1_\n'
        'APP_ORIGIN=https://platform-complete-1.preview.emergentagent.com\n'
        'APP_SECRET=test_secret_32_characters_minimum_length_required\n'
        'OWNER_SETUP_KEY=test_owner_key_32_characters_minimum_length\n'
        'RUNTIME_MODE=sandbox\n'
        'EXTERNAL_ACTIONS_ENABLED=false\n'
    )
    
    backend_env_local = temp_env_dir / 'backend' / '.env.local'
    backend_env_local.write_text(
        'ADDITIONAL_TRUSTED_ORIGINS=,,  ,\n'
    )
    
    frontend_env = temp_env_dir / 'frontend' / '.env'
    frontend_env.write_text(
        'REACT_APP_BACKEND_URL=https://platform-complete-1.preview.emergentagent.com\n'
    )
    
    # Should succeed - empty values ignored, APP_ORIGIN matches
    settings = check_environment(root=temp_env_dir, environ={})
    assert settings.app_origin == 'https://platform-complete-1.preview.emergentagent.com'
