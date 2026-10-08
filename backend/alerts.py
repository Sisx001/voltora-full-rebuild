'''Security and operations alert dispatch. Sends approved events through the
enabled notification provider (Telegram), filters by the provider's event list
and minimum severity, and records every alert in `alert_log` (30-day retention)
whether or not a channel is connected.

Untrusted content (user names, IPs) is HTML-escaped by adapters; the dispatcher
also strips angle brackets defensively.'''
from datetime import timedelta
from fastapi import APIRouter, Depends
from pydantic import Field
from core import db, uid, stamp, now, Input, Doc, audit
from permissions import require

SEVERITY_ORDER = {'low': 0, 'medium': 1, 'high': 2}

KNOWN_EVENTS = ('admin_login', 'admin_login_failed', 'payment_failed', 'courier_failed', 'security_flag', 'order_placed', 'order_cancelled', 'return_requested')


def clean(text: str) -> str:
    return str(text).replace('<', '').replace('>', '')


async def event_settings() -> dict:
    '''Owner-customized per-event rules: {events: {event: {enabled, min_severity}}, min_severity}.'''
    doc = await db.alert_settings.find_one({'id': 'main'}, {'_id': 0})
    return doc or {}


async def send_alert(event: str, severity: str, title: str, body: str):
    '''Record the alert, then push it through the notification channel if enabled
    and the event passes the customized subscription rules (per-event toggle +
    severity floor, falling back to the provider's own event list). Never raises.'''
    import providers
    body = clean(body)
    event = event if event in KNOWN_EVENTS else 'security_flag'
    severity = severity if severity in SEVERITY_ORDER else 'low'
    row = {'id': uid(), 'event': event, 'severity': severity,
           'title': clean(title)[:200], 'body': body, 'sent': False, 'channel': '', 'error': '', 'created_at': stamp(),
           'expires_at': now() + timedelta(days=30)}
    try:
        settings_doc = await event_settings()
        per_event = (settings_doc.get('events') or {}).get(event) or {}
        global_min = (settings_doc.get('min_severity') or '').lower()
        event_enabled = per_event.get('enabled')
        event_floor = (per_event.get('min_severity') or '').lower()
        config = await providers.notification_config(db)
        if config:
            adapter = providers.get_adapter('notification', config['provider'])
            cfg = config.get('config', {})
            allowed = [e.strip() for e in (cfg.get('events') or '').split(',') if e.strip()]
            provider_min = (cfg.get('min_severity') or 'low').lower()
            # effective rules: explicit event setting wins, else provider config, else defaults
            enabled = True if event_enabled is None else bool(event_enabled)
            min_sev = event_floor or global_min or provider_min or 'low'
            if not allowed or row['event'] in allowed:
                if enabled and SEVERITY_ORDER[row['severity']] >= SEVERITY_ORDER.get(min_sev, 0):
                    credentials = config['unsealed']
                    result = await adapter.send_alert(credentials, row['title'], body, row['severity'])
                    row['sent'], row['channel'] = bool(result.get('ok')), config['provider']
    except Exception as error:
        row['error'] = str(error)[:300]
    try:
        await db.alert_log.insert_one(row.copy())
    except Exception:
        pass
    return row


router = APIRouter(prefix='/api/admin/alerts', tags=['Alerts'])


@router.get('', response_model=list)
async def recent_alerts(user=Depends(require('security.read'))):
    return await db.alert_log.find({}, {'_id': 0}).sort('created_at', -1).to_list(60)


# ---- alert event customization ----

class AlertEventRule(Input):
    event: str
    enabled: bool = True
    min_severity: str = Field(default='low', pattern=r'^(low|medium|high)$')


class AlertSettingsSave(Input):
    events: list[AlertEventRule] = Field(default_factory=list, max_length=20)
    min_severity: str = Field(default='low', pattern=r'^(low|medium|high)$')


@router.get('/settings', response_model=Doc)
async def get_alert_settings(user=Depends(require('security.read'))):
    doc = await event_settings()
    rules = {e: r for e, r in (doc.get('events') or {}).items() if e in KNOWN_EVENTS}
    return {'known_events': list(KNOWN_EVENTS), 'min_severity': doc.get('min_severity', 'low'), 'events': rules}


@router.put('/settings', response_model=Doc)
async def put_alert_settings(data: AlertSettingsSave, user=Depends(require('security.update'))):
    events = {}
    for rule in data.events:
        if rule.event in KNOWN_EVENTS:
            events[rule.event] = {'enabled': rule.enabled, 'min_severity': rule.min_severity}
    await db.alert_settings.update_one({'id': 'main'}, {'$set': {'id': 'main', 'events': events, 'min_severity': data.min_severity, 'updated_at': stamp()}}, upsert=True)
    await audit(user, 'alert_settings.saved', '', f"{len(events)} events customized")
    return {'ok': True}
