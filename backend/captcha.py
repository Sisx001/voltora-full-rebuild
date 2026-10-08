"""CAPTCHA enforcement: public widget config + server-side token verification
for protected surfaces (admin_login, signup, password_reset). Disabled and
invisible until an owner connects and enables a CAPTCHA provider."""
from fastapi import Request, HTTPException
from core import db
import providers


def _surface_enabled(config, surface):
    surfaces = [s.strip() for s in (config.get('config', {}).get('surfaces') or 'admin_login,signup,password_reset').split(',') if s.strip()]
    return surface in surfaces


async def captcha_public_config():
    config = await providers.captcha_config(db)
    if not config:
        return {'enabled': False}
    adapter = providers.get_adapter('captcha', config['provider'])
    return {'enabled': True, 'provider': config['provider'], 'site_key': adapter.site_key(config['unsealed']), 'script_url': adapter.script_url()}


async def enforce_captcha(request: Request, surface: str, token: str):
    """Raises 403 when the surface is protected and the token fails verification."""
    config = await providers.captcha_config(db)
    if not config or not _surface_enabled(config, surface):
        return
    adapter = providers.get_adapter('captcha', config['provider'])
    ok = await adapter.verify(config['unsealed'], token, request.client.host if request.client else '')
    if not ok:
        raise HTTPException(403, 'CAPTCHA verification failed. Please try again.')
