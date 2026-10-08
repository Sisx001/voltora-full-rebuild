'''Cloudflare Turnstile CAPTCHA adapter. Site key is public (frontend widget);
the secret key stays sealed and is verified server-side.'''
import httpx
from providers.base import CaptchaProvider, register_captcha, field, setting

VERIFY = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js'


@register_captcha
class Turnstile(CaptchaProvider):
    id = 'turnstile'
    label = 'Cloudflare Turnstile'
    docs_url = 'https://developers.cloudflare.com/turnstile/'
    config_fields = [
        field('site_key', 'Site key (public)'),
        field('secret_key', 'Secret key', secret=True),
    ]
    settings_fields = [
        setting('surfaces', 'Protected surfaces (comma list)', default='admin_login,signup,password_reset'),
    ]

    def script_url(self):
        return SCRIPT

    async def verify(self, credentials, token, remote_ip):
        if not token:
            return False
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(VERIFY, data={'secret': credentials.get('secret_key', ''), 'response': token, 'remoteip': remote_ip})
            return bool(response.json().get('success'))
        except Exception:
            return False
