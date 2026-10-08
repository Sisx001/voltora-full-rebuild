"""Check backend settings and browser/API-origin alignment without exposing secrets.

This checks configured values only, not provider or service readiness. It never
approves an origin or modifies configuration automatically.
"""
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from runtime_config import ConfigurationError, read_runtime_settings  # noqa: E402


def check_environment(root=ROOT, environ=None):
    env = dict(os.environ if environ is None else environ)
    for filename in ('.env', '.env.local'):
        for key, value in dotenv_values(root / 'backend' / filename).items():
            if value is not None:
                env.setdefault(key, value)
    settings = read_runtime_settings(env)
    frontend = dotenv_values(root / 'frontend/.env')
    value = env.get('REACT_APP_BACKEND_URL') or frontend.get('REACT_APP_BACKEND_URL') or ''
    try:
        uri = urlsplit(value.strip())
        valid = uri.scheme == 'https' and bool(uri.hostname) and not (uri.username or uri.password or uri.query or uri.fragment) and uri.path in ('', '/')
        _ = uri.port
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError('REACT_APP_BACKEND_URL must be an HTTPS origin without credentials, paths or query strings.')
    origin = value.strip().rstrip('/')
    trusted = {settings.app_origin, *(v.strip().rstrip('/') for v in env.get('ADDITIONAL_TRUSTED_ORIGINS', '').split(',') if v.strip())}
    if origin not in trusted:
        raise ConfigurationError('Browser/API origin is not in the backend exact-origin allowlist. Confirm the current platform preview alias; explicitly approve it with ADDITIONAL_TRUSTED_ORIGINS in fresh private backend/.env.local if absent. Do not overwrite protected URLs or relax CORS. See docs/STARTUP.md.')
    return settings


def main():
    try:
        settings = check_environment()
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f'Configuration aligned. Runtime: {settings.runtime_mode}. External actions: {"enabled" if settings.external_actions else "disabled"}.')
    print('This does not verify running services or external providers. Use the configured HTTPS origin for browser testing.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
