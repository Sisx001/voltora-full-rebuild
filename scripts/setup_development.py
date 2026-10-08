"""Create NEW isolated sandbox settings. Never import archives or replace .env files."""
import argparse
import configparser
import os
from pathlib import Path
import re
import secrets
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from runtime_config import read_runtime_settings  # noqa: E402


def platform_origin():
    config = configparser.ConfigParser(interpolation=None)
    config.read('/etc/supervisor/conf.d/supervisord.conf')
    entry = config.get('program:backend', 'environment', fallback='')
    match = re.search(r'APP_URL="([^"]+)"', entry)
    return os.environ.get('APP_URL') or (match.group(1) if match else '')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default=platform_origin(), help='HTTPS browser origin; defaults to platform APP_URL')
    parser.add_argument('--mongo-url', required=True, help='Local/staging MongoDB URI; never use production')
    args = parser.parse_args()
    targets = [ROOT / 'backend/.env', ROOT / 'frontend/.env']
    if any(p.exists() for p in targets + [ROOT / 'backend/.env.local']):
        parser.error('Existing private environment found; refusing to overwrite or combine configuration.')
    values = {
        'MONGO_URL': args.mongo_url,
        'DB_NAME': 'voltora_dev_' + uuid.uuid4().hex[:12],
        'REBUILD_COLLECTION_PREFIX': 'v1_',
        'APP_ORIGIN': args.origin.rstrip('/'),
        'APP_SECRET': secrets.token_urlsafe(48),
        'OWNER_SETUP_KEY': secrets.token_urlsafe(36),
        'RUNTIME_MODE': 'sandbox',
        'EXTERNAL_ACTIONS_ENABLED': 'false',
    }
    read_runtime_settings(values)
    if any('\n' in v or '\r' in v or '#' in v for v in values.values()):
        parser.error('Configuration values must be single-line and URI-encoded.')
    frontend = {'REACT_APP_BACKEND_URL': values['APP_ORIGIN'], 'REACT_APP_ADMIN_PATH': '/admin'}
    for path, content in zip(targets, (values, frontend)):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('# Private isolated development configuration. Never commit.\n')
            stream.write(''.join(f'{k}={v}\n' for k, v in content.items()))
    print('Created fresh private .env files (0600); sandbox only, external actions disabled.')
    print('No accounts created. Use the private OWNER_SETUP_KEY for first owner setup over HTTPS.')


if __name__ == '__main__':
    main()
