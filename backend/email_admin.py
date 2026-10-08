"""Email template overrides: owner-editable subject/body per template, with
{variable} merging (notifications.render) and a test-send. Plain-text body;
falls back to the built-in defaults when no override exists. Plus the Email
Theme Builder (accent/logo/button/footer) with a live HTML preview."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import Field, field_validator
from core import db, Doc, Input, stamp, audit, settings
from schemas import safe_url
from permissions import require
from notifications import TEMPLATES

router = APIRouter(prefix='/api/admin/email-templates', tags=['Email templates'])

TEMPLATE_IDS = {tid: subject for tid, (subject, _) in TEMPLATES.items()}


@router.get('', response_model=Doc)
async def list_templates(user=Depends(require('settings.read'))):
    rows = await db.email_templates.find({}, {'_id': 0}).to_list(50)
    by_id = {r['id']: r for r in rows}
    out = []
    for tid, subject in TEMPLATE_IDS.items():
        override = by_id.get(tid, {})
        out.append({'id': tid, 'subject': override.get('subject', subject), 'body': override.get('body', TEMPLATES[tid][1]),
                    'custom': bool(by_id.get(tid)), 'variables': sorted({v for _, b in [TEMPLATES[tid]] for v in __import__('re').findall(r'{(\w+)}', b)})})
    return {'templates': out}


class TemplateSave(Input):
    id: str
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)


@router.put('', response_model=Doc)
async def save_template(data: TemplateSave, user=Depends(require('settings.update'))):
    if data.id not in TEMPLATE_IDS:
        raise HTTPException(404, 'Unknown template')
    await db.email_templates.update_one({'id': data.id}, {'$set': {'id': data.id, 'subject': data.subject, 'body': data.body, 'updated_by': user['id'], 'updated_at': stamp()}}, upsert=True)
    await audit(user, 'email_template.saved', data.id)
    return {'ok': True}


@router.delete('/{id}', response_model=Doc)
async def reset_template(id: str, user=Depends(require('settings.update'))):
    result = await db.email_templates.delete_one({'id': id})
    if not result.deleted_count:
        raise HTTPException(404, 'No override to reset')
    await audit(user, 'email_template.reset', id)
    return {'ok': True}


class TestSend(Input):
    to_email: str = Field(min_length=3, max_length=200)


@router.post('/{id}/test-send', response_model=Doc)
async def test_send(id: str, data: TestSend, user=Depends(require('settings.update'))):
    import providers
    config = await providers.messaging_config(db, 'email')
    if not config:
        raise HTTPException(503, 'Connect an email provider (Connections -> Email) before sending test email.')
    row = await db.email_templates.find_one({'id': id}, {'_id': 0})
    subject, body = (row['subject'], row['body']) if row else TEMPLATES.get(id, ('VOLTORA test', 'Test email'))
    adapter = providers.get_adapter('messaging', config['provider'])
    from notifications import render
    await adapter.send(config['unsealed'], data.to_email, render(subject, {'code': '123456', 'order_number': 'VT-TEST', 'total': '1,000', 'payment_method': 'COD', 'courier': 'TestCourier', 'tracking': 'TEST123'}),
                       render(body, {'code': '123456', 'order_number': 'VT-TEST', 'total': '1,000', 'payment_method': 'COD', 'courier': 'TestCourier', 'tracking': 'TEST123'}))
    await audit(user, 'email_template.test_sent', id, data.to_email)
    return {'ok': True, 'note': 'Test email sent (or logged by a mock provider).'}


# ---- Email Theme Builder ----

email_theme_router = APIRouter(prefix='/api/admin/email-theme', tags=['Email theme'])


class EmailThemeSave(Input):
    accent: str = Field(default='', pattern=r'^(#[0-9a-fA-F]{6})?$')
    button_color: str = Field(default='', pattern=r'^(#[0-9a-fA-F]{6})?$')
    logo: str = Field(default='', max_length=2000)
    footer_text: str = Field(default='', max_length=300)
    @field_validator('logo')
    @classmethod
    def logo_valid(cls, value):
        return safe_url(value)


@email_theme_router.get('', response_model=Doc)
async def get_theme(user=Depends(require('settings.read'))):
    doc = await db.email_theme.find_one({'id': 'main'}, {'_id': 0})
    return doc or {'accent': '', 'button_color': '', 'logo': '', 'footer_text': ''}


@email_theme_router.put('', response_model=Doc)
async def save_theme(data: EmailThemeSave, user=Depends(require('settings.update'))):
    value = {k: v for k, v in data.model_dump().items()}
    await db.email_theme.update_one({'id': 'main'}, {'$set': {'id': 'main', **value, 'updated_at': stamp()}}, upsert=True)
    await audit(user, 'email_theme.saved')
    return {'ok': True}


@email_theme_router.get('/preview', response_class=HTMLResponse)
async def preview_theme(user=Depends(require('settings.read'))):
    theme = await db.email_theme.find_one({'id': 'main'}, {'_id': 0}) or {}
    from core import settings as _settings
    store = await _settings()
    theme_doc = await db.documents.find_one({'id': 'theme'}, {'_id': 0, 'published.primary': 1})
    primary = (theme_doc or {}).get('published', {}).get('primary', '#b9f46b')
    from notifications import brand_html
    body = ('Thanks for your order!\n\nOrder: VT-PREVIEW\nTotal: 1,450 BDT\nPayment: Cash on delivery\n\n'
            'Track it any time from your account.')
    return HTMLResponse(brand_html('Your VOLTORA order VT-PREVIEW', body, store.get('brand', 'VOLTORA'), primary, store.get('footer_text', ''), theme))
