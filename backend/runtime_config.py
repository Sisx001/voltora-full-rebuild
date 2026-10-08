"""Validate startup configuration without connecting or revealing secret values."""
from dataclasses import dataclass
import re
from typing import Mapping
from urllib.parse import urlsplit


class ConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeSettings:
    mongo_url: str
    db_name: str
    collection_prefix: str
    app_origin: str
    runtime_mode: str
    external_actions: bool


def read_runtime_settings(env: Mapping[str, str]) -> RuntimeSettings:
    required = ('MONGO_URL', 'DB_NAME', 'REBUILD_COLLECTION_PREFIX', 'APP_ORIGIN', 'APP_SECRET')
    problems = [f'{key} is required' for key in required if not env.get(key, '').strip()]
    mongo = env.get('MONGO_URL', '').strip()
    name = env.get('DB_NAME', '').strip()
    prefix = env.get('REBUILD_COLLECTION_PREFIX', '').strip()
    origin = env.get('APP_ORIGIN', '').strip().rstrip('/')
    mode = env.get('RUNTIME_MODE', 'sandbox').strip()
    actions = env.get('EXTERNAL_ACTIONS_ENABLED', 'false').strip().lower()
    if mongo:
        try:
            uri = urlsplit(mongo)
            valid_mongo = uri.scheme in ('mongodb', 'mongodb+srv') and bool(uri.netloc)
        except ValueError:
            valid_mongo = False
        if not valid_mongo:
            problems.append('MONGO_URL must be a MongoDB connection URI')
    if name and not re.fullmatch(r'[A-Za-z0-9_-]{1,63}', name):
        problems.append('DB_NAME must contain 1–63 letters, digits, underscores or hyphens')
    if prefix and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', prefix):
        problems.append('REBUILD_COLLECTION_PREFIX must start with a letter and contain only letters, digits or underscores')
    for key, values in [('APP_ORIGIN', [origin]), ('ADDITIONAL_TRUSTED_ORIGINS', env.get('ADDITIONAL_TRUSTED_ORIGINS', '').split(','))]:
        for value in filter(None, (v.strip().rstrip('/') for v in values)):
            try:
                uri = urlsplit(value)
                valid = uri.scheme == 'https' and bool(uri.hostname) and not (uri.username or uri.password or uri.path or uri.query or uri.fragment)
                _ = uri.port
            except ValueError:
                valid = False
            if not valid:
                problems.append(f'{key} must contain HTTPS origins only (no paths, credentials or wildcards)')
    if mode not in ('sandbox', 'production'):
        problems.append('RUNTIME_MODE must select sandbox or production')
    if actions not in ('true', 'false'):
        problems.append('EXTERNAL_ACTIONS_ENABLED must be true or false')
    if actions == 'true' and mode != 'production':
        problems.append('EXTERNAL_ACTIONS_ENABLED must remain false in sandbox')
    for key in ('APP_SECRET', 'OWNER_SETUP_KEY'):
        value = env.get(key, '')
        if value and (len(value) < 32 or value.lower().startswith(('replace', 'change', 'example'))):
            problems.append(f'{key} must be a fresh private secret of at least 32 characters')
    if problems:
        raise ConfigurationError('VOLTORA startup configuration is invalid: ' + '; '.join(problems) + '. See docs/STARTUP.md. No configuration values have been logged.')
    return RuntimeSettings(mongo, name, prefix, origin, mode, actions == 'true' and mode == 'production')
