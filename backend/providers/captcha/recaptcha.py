'''Google reCAPTCHA (v2 checkbox) adapter.'''
import httpx
from providers.base import CaptchaProvider, register_captcha, field, setting

VERIFY = 'https://www.google.com/recaptcha/api/siteverify'
SCRIPT = 'https://www.google.com/recaptcha/api.js'


@register_captcha
class Recaptcha(CaptchaProvider):
    id = 'recaptcha'
    label = 'Google reCAPTCHA v2'
    docs_url = 'https://developers.google.com/recaptcha/docs/display'
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
