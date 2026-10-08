'''Notification dispatch: email + SMS through the messaging provider adapters,
with a durable queue (retry + TTL) so a broken mail relay never loses mail or
blocks a request. Template rendering is deliberately simple string formatting.
'''
import asyncio
from datetime import datetime, timezone
from core import db, uid, stamp, now

_queue_worker_started = False


def render(template: str, vars: dict) -> str:
    out = template
    for key, value in (vars or {}).items():
        out = out.replace('{' + key + '}', str(value))
    return out


async def enqueue(kind: str, to: str, subject: str, body: str, vars: dict | None = None):
    '''Queue an email. Delivery is attempted by the background worker with retries.'''
    from core import EXTERNAL_ACTIONS
    if not EXTERNAL_ACTIONS:
        await db.email_queue.insert_one({'id':uid(),'kind':kind,'to':to,'subject':subject,'body':render(body,vars or {}),'attempts':0,'status':'suppressed_demo','error':'External delivery disabled in demonstration','created_at':stamp()})
        return
    await db.email_queue.insert_one({'id': uid(), 'kind': kind, 'to': to, 'subject': subject, 'body': render(body, vars or {}), 'attempts': 0, 'status': 'queued', 'error': '', 'created_at': stamp(), 'expires_at': datetime.fromtimestamp(now().timestamp() + 7 * 86400, timezone.utc)})


def brand_html(subject: str, body: str, brand: str, primary: str, footer_text: str, theme: dict | None = None) -> str:
    '''Wrap a plain-text body in the store's brand: logo/colored header, themed
    button, footer. Body text is HTML-escaped so store/user content can't inject markup.'''
    from html import escape
    theme = theme or {}
    primary = theme.get('accent') or (primary if primary.startswith('#') else '#b9f46b')
    button = theme.get('button_color') or primary
    dark = '#1c2918'
    lines = ''.join('<p style=\"margin:0 0 12px\">' + escape(l) + '</p>' for l in body.split('\n') if l.strip())
    logo = (theme.get('logo') or '').strip()
    head = ('<img src=\"' + escape(logo) + '\" alt=\"' + escape(brand) + '\" style=\"max-height:44px;display:block\"/>'
            if logo else escape(brand))
    head_style = 'padding:18px 26px;font-size:18px;font-weight:800;background:' + escape(primary) + ';color:' + dark
    if logo:
        head_style = 'padding:16px 26px;background:' + escape(primary) + ';color:' + dark
    return ('<div style=\"font-family:Segoe UI,Arial,sans-serif;background:#f4f5f3;padding:28px\">'
            '<div style=\"max-width:560px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e6e9e3\">'
            '<div style=\"' + head_style + '\">' + head + '</div>'
            '<div style=\"padding:26px;color:#202420;font-size:14px;line-height:1.7\">'
            '<h2 style=\"margin:0 0 14px;font-size:17px\">' + escape(subject) + '</h2>' + lines +
            '<p style=\"margin:22px 0 0\"><a href=\"\" style=\"background:' + escape(button) + ';color:' + dark + ';padding:11px 22px;border-radius:8px;text-decoration:none;font-weight:700\">Visit the store</a></p>'
            '</div>'
            '<div style=\"padding:16px 26px;background:#f9faf7;color:#737a73;font-size:11px\">' + escape(theme.get('footer_text') or footer_text or ('© ' + brand)) + '</div>'
            '</div></div>')


async def email_theme() -> dict:
    '''The Email Theme Builder document (accent, logo, button color, footer).'''
    doc = await db.email_theme.find_one({'id': 'main'}, {'_id': 0})
    return doc or {}


async def send_email(to: str, subject: str, body: str, vars: dict | None = None):
    '''Best-effort immediate email; falls back to the queue on failure.'''
    import providers
    override = await db.email_templates.find_one({'subject': subject}, {'_id': 0, 'body': 1})
    if override and override.get('body'):
        body = override['body']
    config = await providers.messaging_config(db, 'email')
    if not config:
        await enqueue('email', to, subject, body, vars)
        return False
    try:
        from core import settings as _settings
        store = await _settings()
        theme_doc = await db.documents.find_one({'id': 'theme'}, {'_id': 0, 'published.primary': 1})
        primary = (theme_doc or {}).get('published', {}).get('primary', '#b9f46b')
        theme = await email_theme()
        html = brand_html(render(subject, vars or {}), render(body, vars or {}), store.get('brand', 'VOLTORA'), primary, store.get('footer_text', ''), theme)
        adapter = providers.get_adapter('messaging', config['provider'])
        sent_html = False
        if hasattr(adapter, 'send_html'):
            try:
                await adapter.send_html(config['unsealed'], to, render(subject, vars or {}), html)
                sent_html = True
            except Exception:
                sent_html = False
        if not sent_html:
            await adapter.send(config['unsealed'], to, render(subject, vars or {}), render(body, vars or {}))
        return True
    except Exception:
        await enqueue('email', to, subject, body, vars)
        return False


async def send_sms(to: str, text: str):
    '''Immediate SMS (OTP codes are short-lived, so no queue). Returns True if sent.'''
    import providers
    config = await providers.messaging_config(db, 'sms')
    if not config:
        return False
    try:
        adapter = providers.get_adapter('messaging', config['provider'])
        await adapter.send(config['unsealed'], to, '', text)
        return True
    except Exception:
        return False


async def _deliver_queued():
    import providers
    config = await providers.messaging_config(db, 'email')
    if not config:
        return
    adapter = providers.get_adapter('messaging', config['provider'])
    rows = await db.email_queue.find({'status': 'queued', 'attempts': {'$lt': 5}}, {'_id': 0}).sort('created_at', 1).to_list(25)
    for row in rows:
        try:
            await adapter.send(config['unsealed'], row['to'], row['subject'], row['body'])
            await db.email_queue.update_one({'id': row['id']}, {'$set': {'status': 'sent', 'attempts': row['attempts'] + 1}})
        except Exception as error:
            await db.email_queue.update_one({'id': row['id']}, {'$set': {'attempts': row['attempts'] + 1, 'error': str(error)[:300], 'status': 'failed' if row['attempts'] >= 4 else 'queued'}})


async def start_queue_worker():
    '''Run the retry loop alongside the FastAPI lifespan. Cheap: wakes once a minute.'''
    global _queue_worker_started
    if _queue_worker_started:
        return
    _queue_worker_started = True

    async def loop():
        while True:
            try:
                await _deliver_queued()
            except Exception:
                pass
            await asyncio.sleep(60)
    asyncio.create_task(loop())


async def notify(user_id: str, type_: str, title: str, body: str, link: str = ''):
    '''In-app notification center entry (90-day retention). Guests are skipped.'''
    if not user_id:
        return
    from datetime import datetime, timezone
    await db.notifications.insert_one({'id': uid(), 'user_id': user_id, 'type': type_, 'title': title[:200], 'body': body[:600], 'link': link[:300], 'read': False, 'created_at': stamp(), 'expires_at': datetime.fromtimestamp(now().timestamp() + 90 * 86400, timezone.utc)})


async def user_notifications(user_id: str):
    return await db.notifications.find({'user_id': user_id}, {'_id': 0}).sort('created_at', -1).to_list(40)


# ---- templates (owner-editable overrides via /admin/email-templates; safe defaults) ----

TEMPLATES = {
    'verify_email': ('Verify your VOLTORA email', 'Welcome to VOLTORA!\n\nConfirm your email address with this code: {code}\n\nIf you did not create this account you can ignore this message.'),
    'otp_email': ('Your VOLTORA sign-in code', 'Your one-time sign-in code is:\n\n{code}\n\nIt expires in 10 minutes and works only once. If this was not you, ignore this message.'),
    'reset_password': ('Reset your VOLTORA password', 'A password reset was requested for your account.\n\nReset code: {code}\n\nThis code expires in 30 minutes. If this was not you, ignore this message.'),
    'welcome': ('Welcome to VOLTORA', 'Your account is ready.\n\nBrowse the store, save your favorites, and check out in seconds.\n\nNeed a hand? Our support team is one message away.'),
    'order_confirmation': ('Your VOLTORA order {order_number}', 'Thanks for your order!\n\nOrder: {order_number}\nTotal: {total} BDT\nPayment: {payment_method}\n\nTrack it any time from your account.'),
    'payment_failed': ('Payment issue with order {order_number}', 'The payment for order {order_number} did not go through.\n\nYour order is saved — you can retry the payment or switch to another method from your account.\n\nIf you paid by cash on delivery, no action is needed.'),
    'shipment_update': ('Your order {order_number} is on the way', 'Good news — your order {order_number} is with {courier}.\n\nTracking reference: {tracking}'),
    'delivered': ('Your order {order_number} was delivered', 'Your order {order_number} has been delivered.\n\nSomething not right? You can start a return from your account within 7 days.'),
    'order_cancelled': ('Your order {order_number} was cancelled', 'Order {order_number} has been cancelled.\n\nIf this was a mistake or you have questions, reply to this email or open a support conversation.'),
    'refunded': ('Refund issued for order {order_number}', 'A refund of {amount} BDT has been issued for order {order_number}.\n\nDepending on your payment method it can take 3–7 working days to appear.'),
    'return_status': ('Update on your return ({order_number})', 'Your return for order {order_number} is now: {status}\n\n{note}'),
    'back_in_stock': ('Back in stock: {product_name}', 'Good news — {product_name} is back in stock.\n\nIt sold out fast last time, so don’t wait too long.'),
    'newsletter_welcome': ('You’re on the list!', 'Thanks for subscribing to store updates.\n\nNew finds and thoughtful edits — straight to your inbox, no noise.'),
}
