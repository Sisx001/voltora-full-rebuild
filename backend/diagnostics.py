"""System Diagnostics Center: one scan, every subsystem.

Each finding: {section, severity: healthy|warning|critical, title, detail, fix}.
Honest by construction - every check reads real state; nothing is fabricated.
"""
import os
import time
from datetime import timedelta
from fastapi import APIRouter, Depends, Request
from core import db, Doc, now, stamp, audit, settings
from permissions import require

router = APIRouter(prefix='/api/admin/diagnostics', tags=['Diagnostics'])


@router.get('', response_model=Doc)
async def run_diagnostics(user=Depends(require('settings.read'))):
    await audit(user, 'diagnostics.ran')
    started = time.monotonic()
    checks = []

    def add(section, severity, title, detail, fix=''):
        checks.append({'section': section, 'severity': severity, 'title': title, 'detail': detail, 'fix': fix})

    # --- Database ---
    try:
        t = time.monotonic()
        await db.command('ping')
        latency = round((time.monotonic() - t) * 1000)
        add('Database', 'healthy', f"Connected ({latency} ms)", 'MongoDB responds to ping.')
        if latency > 300:
            add('Database', 'warning', 'High database latency', f'Ping took {latency} ms.', 'Check network and indexes.')
    except Exception as error:
        add('Database', 'critical', 'Database unreachable', str(error)[:200], 'Verify MONGO_URL and that MongoDB is running.')
        return _result(checks, started)

    # --- Integrations ---
    import providers
    kinds = [('Payments', 'payment'), ('Couriers', 'courier'), ('Email', 'messaging:email'), ('SMS/OTP', 'messaging:sms'), ('Alerts (Telegram)', 'notification'), ('CAPTCHA', 'captcha'), ('Cloudflare', 'infra')]
    for label, kind in kinds:
        mk = kind.split(':')[1] if ':' in kind else None
        k = kind.split(':')[0]
        connected = await providers.any_connected(db, k, mk) if mk else await providers.any_connected(db, k)
        if connected:
            add('Integrations', 'healthy', f'{label} connected', f'A {label.lower()} provider is enabled and verified.')
        else:
            sev = 'warning' if label in ('Email', 'SMS/OTP') else 'low'
            if sev == 'low':
                sev = 'healthy' if label in ('Alerts (Telegram)', 'CAPTCHA') else 'warning'
            add('Integrations', sev, f'{label} not connected', f'No enabled {label.lower()} provider.', 'Connect one under Connections -> Providers.')

    # --- AI ---
    ai = await db.integrations.find_one({'id': 'deepseek'}, {'_id': 0, 'connected': 1, 'model': 1})
    flags = (await settings()).get('features', {})
    if flags.get('ai_customer') or flags.get('ai_admin') or flags.get('ai_chat'):
        if ai and ai.get('connected'):
            add('AI', 'healthy', f"AI connected ({ai.get('model')})", 'Assistant features are live.')
        else:
            add('AI', 'critical', 'AI features enabled but no provider connected', 'Customers/staff will see honest unavailable states.', 'Connect an AI provider in AI Studio or disable the AI flags.')
    else:
        add('AI', 'healthy', 'AI features off', 'Enable ai_customer / ai_admin after connecting a provider.')

    # --- Catalog ---
    missing_seo = await db.products.count_documents({'published': True, 'seo_description': ''})
    if missing_seo:
        add('Catalog', 'warning' if missing_seo < 20 else 'warning', f'{missing_seo} published products missing SEO description', 'Hurts search visibility.', 'Fill SEO fields or ask Mony to draft them.')
    else:
        add('Catalog', 'healthy', 'Product SEO complete', 'All published products have SEO descriptions.')
    no_images = await db.products.count_documents({'published': True, 'images.0': {'$exists': False}})
    if no_images:
        add('Catalog', 'warning', f'{no_images} published products have no images', 'Products render with broken/empty tiles.', 'Add at least one image per product.')
    inv = await db.inventory.find_one({'id': 'main'}, {'_id': 0, 'quantities': 1}) or {}
    out_of_stock = sum(1 for v in (inv.get('quantities') or {}).values() if v <= 0)
    low_stock = sum(1 for v in (inv.get('quantities') or {}).values() if 0 < v <= 10)
    if out_of_stock:
        add('Inventory', 'warning', f'{out_of_stock} variants out of stock', 'Customers cannot order these.', 'Restock or hide the variants.')
    if low_stock:
        add('Inventory', 'warning', f'{low_stock} variants low (<=10 units)', 'Restock soon.', 'See Inventory -> Low stock.')
    if not out_of_stock and not low_stock:
        add('Inventory', 'healthy', 'Stock levels healthy', 'No out-of-stock or low-stock variants.')

    # --- Coupons ---
    now_iso = stamp()
    expired_enabled = await db.coupons.count_documents({'enabled': True, 'ends_at': {'$ne': '', '$lt': now_iso}})
    if expired_enabled:
        add('Coupons', 'warning', f'{expired_enabled} enabled coupons already expired', 'They silently reject at checkout.', 'Disable or extend them.')

    # --- Offer pages ---
    broken_offers = 0
    async for offer in db.offer_pages.find({'active': True}, {'_id': 0, 'id': 1, 'code': 1, 'product_id': 1}):
        if not await db.products.find_one({'id': offer['product_id'], 'published': True}):
            broken_offers += 1
    if broken_offers:
        add('Offers', 'critical', f'{broken_offers} active offer pages point to unavailable products', 'Customers hit a 404-style state.', 'Deactivate or retarget those offers.')
    else:
        add('Offers', 'healthy', 'Active offer pages OK', 'All active offers point to published products.')

    # --- Theme ---
    theme_doc = await db.documents.find_one({'id': 'theme'}, {'_id': 0, 'draft': 1, 'published': 1})
    if theme_doc and theme_doc.get('draft', {}).get('id') != theme_doc.get('published', {}).get('id'):
        add('Theme', 'warning', 'Unpublished theme draft exists', 'The live store differs from your draft.', 'Preview and publish, or discard the draft.')
    else:
        add('Theme', 'healthy', 'Theme draft in sync', 'Draft matches the published theme.')

    # --- Store settings ---
    config = await settings()
    if config['mode'] != 'live':
        add('Store', 'critical', f"Store mode is '{config['mode']}'", 'Checkout is blocked for customers.', 'Switch to live under Store settings when ready.')
    else:
        add('Store', 'healthy', 'Store live', 'Accepting orders.')
    if config['demo_catalog']:
        add('Store', 'warning', 'Demo catalog disclosure is ON', 'Intentional for demo stores.', 'Seed real products and turn the disclosure off before going commercial.')

    # --- Email queue ---
    failed_mail = await db.email_queue.count_documents({'status': 'failed'})
    queued_mail = await db.email_queue.count_documents({'status': 'queued'})
    if failed_mail:
        add('Email', 'critical', f'{failed_mail} emails permanently failed', 'Customer notifications were lost.', 'Check SMTP settings and test the connection.')
    elif queued_mail:
        add('Email', 'warning', f'{queued_mail} emails queued', 'Waiting for the background worker.', 'Verify the email provider is connected.')
    else:
        add('Email', 'healthy', 'Email queue empty', 'No pending or failed email.')

    # --- Webhooks/alerts ---
    recent_alert_errors = await db.alert_log.count_documents({'error': {'$ne': ''}, 'created_at': {'$gte': (now() - timedelta(days=7)).isoformat()}})
    if recent_alert_errors:
        add('Alerts', 'warning', f'{recent_alert_errors} alert delivery errors in 7 days', 'Telegram may be misconfigured.', 'Test the notification provider.')

    # --- Environment ---
    for var, label in [('DEEPSEEK_BASE_URL', 'AI base URL'), ('INTEGRATION_PROXY_URL', 'Object storage'), ('APP_ORIGIN', 'Store origin')]:
        if not os.environ.get(var):
            add('Environment', 'warning', f'{label} ({var}) not set', 'Some features may be limited.', 'Add the env var and restart.')
    return _result(checks, started)


def _result(checks, started):
    counts = {'healthy': 0, 'warning': 0, 'critical': 0}
    for c in checks:
        counts[c['severity']] = counts.get(c['severity'], 0) + 1
    order = {'critical': 0, 'warning': 1, 'healthy': 2}
    checks.sort(key=lambda c: (order.get(c['severity'], 3), c['section']))
    return {'checks': checks, 'counts': counts, 'scanned_at': stamp(), 'duration_ms': round((time.monotonic() - started) * 1000),
            'note': 'Every check reads live state. Nothing here is simulated.'}


@router.get('/api-surface', response_model=Doc)
async def api_surface(user=Depends(require('security.read'))):
    from server import app
    rows = []
    for route in app.routes:
        path = getattr(route, 'path', '')
        if not path.startswith('/api') or path in ('/api/openapi.json', '/api/docs', '/api/docs/oauth2-redirect'):
            continue
        methods = sorted(m for m in getattr(route, 'methods', []) if m not in ('HEAD', 'OPTIONS'))
        if not methods:
            continue
        if path.startswith('/api/webhooks'):
            area = 'webhooks (signature-verified)'
        elif path.startswith('/api/admin'):
            area = 'admin (RBAC + MFA)'
        elif path.startswith('/api/auth'):
            area = 'auth (rate-limited)'
        elif path.startswith('/api/health') or path == '/api/captcha/config':
            area = 'public'
        else:
            area = 'storefront (public/consent-gated)'
        rows.append({'path': path, 'methods': ','.join(methods), 'area': area})
    rows.sort(key=lambda r: (r['area'], r['path']))
    return {'routes': rows, 'count': len(rows), 'note': 'Live route table from the running application.'}
