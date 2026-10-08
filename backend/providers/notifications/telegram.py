'''Telegram security/operations alert channel. Bot token + chat id configured
in the admin; the alerts dispatcher filters events by the `events` setting.
Message formatting uses HTML with strict escaping of untrusted content.'''
import httpx
from providers.base import NotificationProvider, register_notification, ProviderError, field, setting

API = 'https://api.telegram.org'


@register_notification
class Telegram(NotificationProvider):
    id = 'telegram'
    label = 'Telegram alerts'
    docs_url = 'https://core.telegram.org/bots/tutorial'
    config_fields = [
        field('bot_token', 'Bot token (from @BotFather)', secret=True),
        field('chat_id', 'Chat / channel ID', placeholder='-1001234567890'),
    ]
    settings_fields = [
        setting('events', 'Enabled events (comma list)', required=False, placeholder='admin_login, admin_login_failed, payment_failed, courier_failed, security_flag', help='Empty = all events'),
        setting('min_severity', 'Minimum severity', default='low', help='low | medium | high'),
    ]

    async def validate_config(self, credentials, sandbox):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(API + f"/bot{credentials.get('bot_token', '')}/getMe")
            body = response.json()
            if body.get('ok'):
                return True, f"Telegram bot verified: @{body['result'].get('username', '?')}"
            return False, 'Telegram rejected the bot token.'
        except Exception as error:
            return False, f'Telegram verification failed: {error}'

    async def send_alert(self, credentials, title, body, severity):
        token = credentials.get('bot_token', '')
        chat_id = credentials.get('chat_id', '')
        if not token or not chat_id:
            raise ProviderError('Telegram bot token or chat id is missing')
        text = f"<b>[{severity.upper()}] {title}</b>\n{body}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(API + f'/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': text[:3900], 'parse_mode': 'HTML', 'disable_web_page_preview': True})
        except Exception as error:
            raise ProviderError(f'Telegram send failed: {error}')
        if not response.json().get('ok'):
            raise ProviderError('Telegram did not accept the message (check chat id and bot membership)')
        return {'ok': True}
