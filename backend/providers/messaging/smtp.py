'''Generic SMTP email adapter - works with any provider (Gmail workspace,
transactional relays, self-hosted mail). Credentials are stored sealed.
'''
import asyncio
import email.utils
import smtplib
import ssl
from email.message import EmailMessage

from providers.base import MessagingAdapter, register_messaging, field


def _connect(credentials, login=True):
    host = credentials['host']
    port = int(credentials.get('port') or 587)
    use_tls = str(credentials.get('use_tls', 'true')).strip().lower() in ('1', 'true', 'yes', 'on')
    if use_tls:
        client = smtplib.SMTP(host, port, timeout=15)
        client.starttls(context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(host, port, timeout=15)
    try:
        if login and credentials.get('username'):
            client.login(credentials['username'], credentials.get('password') or '')
        return client
    except Exception:
        client.quit()
        raise


@register_messaging
class SmtpEmail(MessagingAdapter):
    id = 'smtp'
    kind = 'email'
    label = 'SMTP email'
    docs_url = 'https://en.wikipedia.org/wiki/Simple_Mail_Transfer_Protocol'
    config_fields = [
        field('host', 'SMTP host', placeholder='smtp.example.com'),
        field('port', 'Port', required=False, placeholder='587'),
        field('username', 'Username', required=False),
        field('password', 'Password', secret=True),
        field('from_email', 'From address', placeholder='store@example.com'),
        field('from_name', 'From name', required=False, placeholder='VOLTORA'),
        field('use_tls', 'Use STARTTLS', required=False, placeholder='true', help='Set to false for plain/SSL-only relays'),
    ]
    settings_fields = []

    async def validate_config(self, credentials, sandbox):
        try:
            def probe():
                client = _connect(credentials)
                try:
                    client.noop()
                finally:
                    client.quit()
            await asyncio.to_thread(probe)
            return True, 'Connected to the SMTP server.'
        except Exception as error:
            return False, f'SMTP connection failed: {error}'

    async def send_html(self, credentials, to, subject, html):
        message = EmailMessage()
        message['Subject'] = subject
        message['From'] = email.utils.formataddr((credentials.get('from_name') or 'VOLTORA', credentials.get('from_email') or credentials.get('username') or ''))
        message['To'] = to
        message.set_content('Please view this email in an HTML-capable client.')
        message.add_alternative(html, subtype='html')

        def deliver():
            client = _connect(credentials)
            try:
                client.send_message(message)
            finally:
                client.quit()
        await asyncio.to_thread(deliver)
        return {'ok': True}

    async def send(self, credentials, to, subject, body):
        message = EmailMessage()
        message['Subject'] = subject
        message['From'] = email.utils.formataddr((credentials.get('from_name') or 'VOLTORA', credentials.get('from_email') or credentials.get('username') or ''))
        message['To'] = to
        message.set_content(body)

        def deliver():
            client = _connect(credentials)
            try:
                client.send_message(message)
            finally:
                client.quit()
        await asyncio.to_thread(deliver)
        return {'ok': True}
