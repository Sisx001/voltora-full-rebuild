"""Regression tests for setup_development.py script."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))


def test_setup_creates_fresh_private_settings():
    """Script should create new .env files with unique DB name and secrets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        backend_dir = root / 'backend'
        frontend_dir = root / 'frontend'
        backend_dir.mkdir()
        frontend_dir.mkdir()
        
        # Mock the ROOT in setup_development
        import setup_development
        original_root = setup_development.ROOT
        setup_development.ROOT = root
        
        try:
            # Run setup
            sys.argv = [
                'setup_development.py',
                '--origin', 'https://test.example.com',
                '--mongo-url', 'mongodb://localhost:27017'
            ]
            setup_development.main()
            
            # Verify backend .env exists and has correct permissions
            backend_env = backend_dir / '.env'
            assert backend_env.exists()
            stat = backend_env.stat()
            assert oct(stat.st_mode)[-3:] == '600'
            
            # Verify frontend .env exists and has correct permissions
            frontend_env = frontend_dir / '.env'
            assert frontend_env.exists()
            stat = frontend_env.stat()
            assert oct(stat.st_mode)[-3:] == '600'
            
            # Read and verify backend .env content
            backend_content = backend_env.read_text()
            assert 'MONGO_URL=mongodb://localhost:27017' in backend_content
            assert 'DB_NAME=voltora_dev_' in backend_content
            assert 'REBUILD_COLLECTION_PREFIX=v1_' in backend_content
            assert 'APP_ORIGIN=https://test.example.com' in backend_content
            assert 'APP_SECRET=' in backend_content
            assert 'OWNER_SETUP_KEY=' in backend_content
            assert 'RUNTIME_MODE=sandbox' in backend_content
            assert 'EXTERNAL_ACTIONS_ENABLED=false' in backend_content
            
            # Verify secrets are long enough
            for line in backend_content.splitlines():
                if line.startswith('APP_SECRET='):
                    secret = line.split('=', 1)[1]
                    assert len(secret) >= 32
                if line.startswith('OWNER_SETUP_KEY='):
                    key = line.split('=', 1)[1]
                    assert len(key) >= 32
            
            # Verify DB name is unique (contains UUID)
            assert 'voltora_dev_' in backend_content
            db_line = [l for l in backend_content.splitlines() if l.startswith('DB_NAME=')][0]
            db_name = db_line.split('=', 1)[1]
            assert len(db_name) > len('voltora_dev_')
            
            # Read and verify frontend .env content
            frontend_content = frontend_env.read_text()
            assert 'REACT_APP_BACKEND_URL=https://test.example.com' in frontend_content
            assert 'REACT_APP_ADMIN_PATH=/admin' in frontend_content
            
        finally:
            setup_development.ROOT = original_root


def test_setup_refuses_to_overwrite_existing_env():
    """Script should refuse to overwrite existing .env files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        backend_dir = root / 'backend'
        frontend_dir = root / 'frontend'
        backend_dir.mkdir()
        frontend_dir.mkdir()
        
        # Create existing backend .env
        (backend_dir / '.env').write_text('EXISTING=true\n')
        
        import setup_development
        original_root = setup_development.ROOT
        setup_development.ROOT = root
        
        try:
            sys.argv = [
                'setup_development.py',
                '--origin', 'https://test.example.com',
                '--mongo-url', 'mongodb://localhost:27017'
            ]
            
            with pytest.raises(SystemExit):
                setup_development.main()
            
            # Verify original file was not modified
            assert (backend_dir / '.env').read_text() == 'EXISTING=true\n'
            
        finally:
            setup_development.ROOT = original_root


def test_setup_refuses_to_overwrite_env_local():
    """Script should refuse to run if .env.local exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        backend_dir = root / 'backend'
        frontend_dir = root / 'frontend'
        backend_dir.mkdir()
        frontend_dir.mkdir()
        
        # Create existing backend .env.local
        (backend_dir / '.env.local').write_text('EXISTING=true\n')
        
        import setup_development
        original_root = setup_development.ROOT
        setup_development.ROOT = root
        
        try:
            sys.argv = [
                'setup_development.py',
                '--origin', 'https://test.example.com',
                '--mongo-url', 'mongodb://localhost:27017'
            ]
            
            with pytest.raises(SystemExit):
                setup_development.main()
            
        finally:
            setup_development.ROOT = original_root


def test_setup_validates_configuration():
    """Script should validate configuration through read_runtime_settings."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        backend_dir = root / 'backend'
        frontend_dir = root / 'frontend'
        backend_dir.mkdir()
        frontend_dir.mkdir()
        
        import setup_development
        from runtime_config import ConfigurationError
        original_root = setup_development.ROOT
        setup_development.ROOT = root
        
        try:
            # Try with invalid origin (HTTP instead of HTTPS)
            sys.argv = [
                'setup_development.py',
                '--origin', 'http://test.example.com',  # Invalid: not HTTPS
                '--mongo-url', 'mongodb://localhost:27017'
            ]
            
            # Should raise ConfigurationError which will cause SystemExit
            with pytest.raises((SystemExit, ConfigurationError)):
                setup_development.main()
            
            # Verify no files were created
            assert not (backend_dir / '.env').exists()
            assert not (frontend_dir / '.env').exists()
            
        finally:
            setup_development.ROOT = original_root


def test_setup_no_real_config_mutation():
    """Test should not mutate real configuration files."""
    # This test verifies that the test itself uses tmp dir
    real_backend_env = Path(__file__).resolve().parents[2] / 'backend' / '.env'
    real_frontend_env = Path(__file__).resolve().parents[2] / 'frontend' / '.env'
    
    # If real files exist, read their content
    backend_before = real_backend_env.read_text() if real_backend_env.exists() else None
    frontend_before = real_frontend_env.read_text() if real_frontend_env.exists() else None
    
    # Run a test (we'll use the first test)
    test_setup_creates_fresh_private_settings()
    
    # Verify real files were not modified
    backend_after = real_backend_env.read_text() if real_backend_env.exists() else None
    frontend_after = real_frontend_env.read_text() if real_frontend_env.exists() else None
    
    assert backend_before == backend_after
    assert frontend_before == frontend_after
