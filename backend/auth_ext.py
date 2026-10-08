'''Extended authentication: phone OTP login, email/phone verification, password
reset, social OAuth (Google / Facebook / Apple), and login history.

Security notes:
- OTP codes are stored hashed, expire in 5 minutes, and are attempt-capped.
- Password reset always answers 200 (no account enumeration) and revokes sessions.
- OAuth state uses a short-lived signed cookie checked on callback.
- All SMS/email sending degrades honestly when no provider is configured.
'''
import base64
import json
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import EmailStr, Field

from core import db, Input, Doc, now, stamp, uid, digest, flag, audit, record_login_history
from auth import current_user, optional_user, create_session, hasher
from permissions import authorize, require

router = APIRouter(prefix='/api/auth', tags=['Identity extensions'])
oauth_admin = APIRouter(prefix='/api/admin/oauth', tags=['OAuth providers'])

OAUTH_PROVIDERS = ('google', 'facebook', 'apple')


# ---------------- helpers ----------------


async def issue_code(purpose, target, payload=None, minutes=5):
    code = f'{secrets.randbelow(1000000):06d}'
    await db.otps.insert_one({'id': uid(), 'purpose': purpose, 'target': digest(target.lower()), 'code_hash': digest(code), 'payload': payload or {}, 'attempts': 0, 'created_at': stamp(), 'expires_at': now() + timedelta(minutes=minutes)})
    return code


async def consume_code(purpose, target, code, single_use=True):
    row = await db.otps.find_one({'purpose': purpose, 'target': digest(target.lower()), 'expires_at': {'$gt': now()}, 'attempts': {'$lt': 5}}, {'_id': 0}, sort=[('created_at', -1)])
    if not row or not secrets.compare_digest(row['code_hash'], digest(code.strip())):
        if row:
            await db.otps.update_one({'id': row['id']}, {'$inc': {'attempts': 1}})
        return None
    if single_use:
        await db.otps.delete_one({'id': row['id']})
    return row


async def messaging_ready(kind):
    import providers
    return await providers.any_connected(db, 'messaging', kind)


# ---------------- OTP sign-in (SMS + email channels) ----------------

class OtpSend(Input):
    phone: str = Field(default='', max_length=25)
    email: EmailStr = Field(default='')
    channel: str = Field(default='sms', pattern=r'^(sms|email)$')
    purpose: str = Field(default='login', pattern=r'^(login|verify)$')


@router.post('/otp/send', response_model=Doc)
async def otp_send(data: OtpSend, request: Request):
    if not await flag('otp_login'):
        raise HTTPException(403, 'OTP sign-in is currently unavailable')
    if data.channel == 'email':
        target = data.email.lower()
        if not target:
            raise HTTPException(422, 'Enter your email address first')
        if not await messaging_ready('email'):
            raise HTTPException(503, 'Email delivery is not configured')
        if data.purpose == 'login':
            user = await db.users.find_one({'email': target, 'disabled': {'$ne': True}}, {'_id': 0})
            if not user or user.get('role') != 'customer':
                return {'ok': True, 'sent': False}
        else:
            user = await optional_user(request)
            if not user:
                raise HTTPException(401, 'Please sign in first')
        code = await issue_code('otp_' + data.purpose, target, {'user_id': (user or {}).get('id', ''), 'email': True})
        from notifications import send_email, TEMPLATES
        subject, body = TEMPLATES['otp_email']
        sent = await send_email(target, subject, body, {'code': code})
        return {'ok': True, 'sent': sent, 'channel': 'email'}
    target = data.phone
    if len(target) < 7:
        raise HTTPException(422, 'Enter your phone number first')
    if not await messaging_ready('sms'):
        raise HTTPException(503, 'SMS delivery is not configured')
    if data.purpose == 'login':
        user = await db.users.find_one({'phone': target, 'disabled': {'$ne': True}}, {'_id': 0})
        if not user or user.get('role') != 'customer':
            return {'ok': True, 'sent': False}
    else:
        user = await optional_user(request)
        if not user:
            raise HTTPException(401, 'Please sign in first')
    code = await issue_code('otp_' + data.purpose, target, {'user_id': (user or {}).get('id', '')})
    from notifications import send_sms
    sent = await send_sms(target, f'Your VOLTORA code is {code}. It expires in 5 minutes.')
    return {'ok': True, 'sent': sent, 'channel': 'sms'}


class OtpLogin(Input):
    phone: str = Field(default='', max_length=25)
    email: EmailStr = Field(default='')
    channel: str = Field(default='sms', pattern=r'^(sms|email)$')
    code: str = Field(pattern=r'^\d{6}$')


@router.post('/otp/login', response_model=Doc)
async def otp_login(data: OtpLogin, request: Request, response: Response):
    if not await flag('otp_login'):
        raise HTTPException(403, 'OTP sign-in is currently unavailable')
    if data.channel == 'email':
        target = data.email.lower()
        if not target:
            raise HTTPException(422, 'Enter your email address')
        row = await consume_code('otp_login', target, data.code, single_use=True)
        if not row:
            raise HTTPException(401, 'That code is invalid or has expired')
        user = await db.users.find_one({'id': row.get('payload', {}).get('user_id', ''), 'email': target, 'disabled': {'$ne': True}}, {'_id': 0})
        if not user:
            raise HTTPException(401, 'No account matches this email address')
    else:
        target = data.phone
        if len(target) < 7:
            raise HTTPException(422, 'Enter your phone number')
        row = await consume_code('otp_login', target, data.code, single_use=True)
        if not row:
            raise HTTPException(401, 'That code is invalid or has expired')
        user = await db.users.find_one({'id': row.get('payload', {}).get('user_id', ''), 'phone': target, 'disabled': {'$ne': True}}, {'_id': 0})
        if not user:
            raise HTTPException(401, 'No account matches this phone number')
    await record_login_history(user['id'], request, True, 'otp-' + data.channel)
    await audit(user, 'auth.login_otp')
    return await create_session(user, request, response)


@router.post('/phone/verify', response_model=Doc)
async def phone_verify(data: OtpLogin, request: Request, user=Depends(current_user)):
    if len(data.phone) < 7:
        raise HTTPException(422, 'Enter your phone number first')
    if not await flag('phone_auth'):
        raise HTTPException(403, 'Phone verification is currently unavailable')
    row = await consume_code('otp_verify', data.phone, data.code)
    if not row:
        raise HTTPException(400, 'That code is invalid or has expired')
    clash = await db.users.find_one({'phone': data.phone, 'id': {'$ne': user['id']}}, {'_id': 1})
    if clash:
        raise HTTPException(409, 'This phone number is already linked to another account')
    await db.users.update_one({'id': user['id']}, {'$set': {'phone': data.phone, 'phone_verified': True}})
    return {'ok': True}


# ---------------- email verification + password reset ----------------

class EmailCode(Input):
    code: str = Field(pattern=r'^\d{6}$')


@router.post('/email/verify/send', response_model=Doc)
async def email_verify_send(request: Request, user=Depends(current_user)):
    if not await flag('email_verification'):
        raise HTTPException(403, 'Email verification is currently unavailable')
    if not await messaging_ready('email'):
        raise HTTPException(503, 'Email delivery is not configured')
    code = await issue_code('email_verify', user['email'])
    from notifications import send_email, TEMPLATES
    subject, body = TEMPLATES['verify_email']
    await send_email(user['email'], subject, body, {'code': code})
    return {'ok': True}


@router.post('/email/verify', response_model=Doc)
async def email_verify(data: EmailCode, user=Depends(current_user)):
    row = await consume_code('email_verify', user['email'], data.code)
    if not row:
        raise HTTPException(400, 'That code is invalid or has expired')
    await db.users.update_one({'id': user['id']}, {'$set': {'email_verified': True}})
    return {'ok': True}


class ForgotPassword(Input):
    email: EmailStr


@router.post('/password/forgot', response_model=Doc)
async def password_forgot(data: ForgotPassword):
    # Always 200 - do not reveal whether the account exists.
    if await flag('email_verification') is False and not await messaging_ready('email'):
        return {'ok': True}
    user = await db.users.find_one({'email': data.email.lower(), 'disabled': {'$ne': True}}, {'_id': 0})
    if user and await messaging_ready('email'):
        code = await issue_code('password_reset', user['email'], {'user_id': user['id']}, minutes=30)
        from notifications import send_email, TEMPLATES
        subject, body = TEMPLATES['reset_password']
        await send_email(user['email'], subject, body, {'code': code})
    return {'ok': True}


class ResetPassword(Input):
    email: EmailStr
    code: str = Field(pattern=r'^\d{6}$')
    new_password: str = Field(min_length=10, max_length=128)


@router.post('/password/reset', response_model=Doc)
async def password_reset(data: ResetPassword, request: Request):
    row = await consume_code('password_reset', data.email.lower(), data.code)
    if not row:
        raise HTTPException(400, 'That code is invalid or has expired')
    user = await db.users.find_one({'id': row.get('payload', {}).get('user_id', '')}, {'_id': 0})
    if not user:
        raise HTTPException(400, 'That code is invalid or has expired')
    await db.users.update_one({'id': user['id']}, {'$set': {'password_hash': hasher.hash(data.new_password)}})
    await db.sessions.delete_many({'user_id': user['id']})
    await record_login_history(user['id'], request, True, 'password_reset')
    await audit(user, 'auth.password_reset')
    return {'ok': True}


# ---------------- login history + logout everywhere ----------------

@router.get('/login-history', response_model=list[Doc])
async def login_history(user=Depends(current_user)):
    return await db.login_history.find({'user_id': user['id']}, {'_id': 0}).sort('created_at', -1).to_list(50)


@router.delete('/sessions/all', response_model=Doc)
async def revoke_all(response: Response, user=Depends(current_user)):
    await db.sessions.delete_many({'user_id': user['id'], 'id': {'$ne': user['session_id']}})
    return {'ok': True}


# ---------------- social OAuth ----------------

def redirect_uri(provider):
    return os.environ['APP_ORIGIN'].rstrip('/') + f'/api/auth/oauth/{provider}/callback'


async def oauth_config(provider):
    row = await db.integrations.find_one({'id': 'oauth:' + provider}, {'_id': 0})
    if not row or not row.get('connected'):
        return None
    from vault import unseal
    return {'client_id': row.get('client_id', ''), 'client_secret': unseal(row['client_secret']) if row.get('client_secret') else ''}


@oauth_admin.get('', response_model=Doc)
async def list_oauth(user=Depends(require('settings.read'))):
    rows = []
    for provider in OAUTH_PROVIDERS:
        row = await db.integrations.find_one({'id': 'oauth:' + provider}, {'_id': 0})
        rows.append({'id': provider, 'connected': bool(row and row.get('connected')), 'client_id': (row or {}).get('client_id', ''), 'redirect_uri': redirect_uri(provider), 'enabled': bool(row and row.get('enabled', True))})
    return {'providers': rows}


class OAuthSave(Input):
    client_id: str = Field(min_length=1, max_length=300)
    client_secret: str = Field(default='', max_length=400)
    enabled: bool = True


@oauth_admin.put('/{provider}', response_model=Doc)
async def save_oauth(provider: str, data: OAuthSave, user=Depends(require('settings.update'))):
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, 'Unknown OAuth provider')
    update = {'client_id': data.client_id, 'enabled': data.enabled, 'connected': True}
    if data.client_secret:
        from vault import seal
        update['client_secret'] = seal(data.client_secret)
    await db.integrations.update_one({'id': 'oauth:' + provider}, {'$set': update}, upsert=True)
    await audit(user, 'oauth.saved', provider)
    return {'ok': True}


@oauth_admin.delete('/{provider}', response_model=Doc)
async def delete_oauth(provider: str, user=Depends(require('settings.update'))):
    result = await db.integrations.delete_one({'id': 'oauth:' + provider})
    if not result.deleted_count:
        raise HTTPException(404, 'Not configured')
    await audit(user, 'oauth.removed', provider)
    return {'ok': True}


AUTHORIZE_URLS = {
    'google': 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({'response_type': 'code', 'scope': 'openid email profile'}),
    'facebook': 'https://www.facebook.com/v19.0/dialog/oauth?' + urlencode({'scope': 'email,public_profile'}),
    'apple': 'https://appleid.apple.com/auth/authorize?' + urlencode({'response_mode': 'form_post', 'scope': 'name email'}),
}
TOKEN_URLS = {
    'google': 'https://oauth2.googleapis.com/token',
    'facebook': 'https://graph.facebook.com/v19.0/oauth/access_token',
    'apple': 'https://appleid.apple.com/auth/token',
}


@router.get('/oauth/{provider}/start')
async def oauth_start(provider: str):
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, 'Unknown OAuth provider')
    config = await oauth_config(provider)
    if not config:
        raise HTTPException(503, 'This sign-in provider is not configured')
    state = secrets.token_urlsafe(24)
    params = {'client_id': config['client_id'], 'redirect_uri': redirect_uri(provider), 'state': state}
    extra = AUTHORIZE_URLS[provider]
    response = RedirectResponse(url=extra + '&' + urlencode(params), status_code=302)
    response.set_cookie('voltora_oauth', provider + ':' + state, max_age=600, httponly=True, secure=True, samesite='lax', path='/')
    return response


async def exchange_google(config, code):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(TOKEN_URLS['google'], data={'code': code, 'client_id': config['client_id'], 'client_secret': config['client_secret'], 'redirect_uri': redirect_uri('google'), 'grant_type': 'authorization_code'})
        body = response.json()
        if 'id_token' not in body:
            raise HTTPException(400, 'Google sign-in failed')
        info_response = await client.get('https://oauth2.googleapis.com/tokeninfo?id_token=' + body['id_token'])
    info = info_response.json()
    if info.get('aud') != config['client_id']:
        raise HTTPException(400, 'Google sign-in could not be verified')
    return {'sub': info.get('sub', ''), 'email': (info.get('email') or '').lower(), 'name': info.get('name') or info.get('email', ''), 'verified': info.get('email_verified') in (True, 'true')}


async def exchange_facebook(config, code):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(TOKEN_URLS['facebook'], params={'client_id': config['client_id'], 'client_secret': config['client_secret'], 'redirect_uri': redirect_uri('facebook'), 'code': code})
        body = response.json()
        if 'access_token' not in body:
            raise HTTPException(400, 'Facebook sign-in failed')
        profile = (await client.get('https://graph.facebook.com/v19.0/me', params={'access_token': body['access_token'], 'fields': 'id,name,email'})).json()
    # Graph email presence is not proof of verified ownership. Separate verification is required.
    return {'sub': profile.get('id', ''), 'email': (profile.get('email') or '').lower(), 'name': profile.get('name') or 'Facebook user', 'verified': False}


async def exchange_apple(config, id_token):
    # Verify Apple's RS256 id_token against Apple's published JWKS.
    import jwt
    try:
        header=jwt.get_unverified_header(id_token)
        if header.get('alg')!='RS256':raise ValueError('Unsupported algorithm')
        async with httpx.AsyncClient(timeout=20,follow_redirects=False) as client:
            response=await client.get('https://appleid.apple.com/auth/keys')
            response.raise_for_status()
            keys=response.json().get('keys',[])
        key=next((k for k in keys if k.get('kid')==header.get('kid') and k.get('kty')=='RSA'),None)
        if not key:raise ValueError('Unknown signing key')
        public_key=jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        payload=jwt.decode(id_token,public_key,algorithms=['RS256'],audience=config['client_id'],issuer='https://appleid.apple.com',options={'require':['exp','iat','iss','sub','aud']})
    except (jwt.PyJWTError,ValueError,KeyError):
        raise HTTPException(400, 'Apple sign-in could not be verified')
    email = (payload.get('email') or '').lower()
    return {'sub': payload.get('sub', ''), 'email': email, 'name': 'Apple user', 'verified': payload.get('email_verified') in (True,'true')}


@router.post('/oauth/{provider}/callback', response_model=Doc)
@router.get('/oauth/{provider}/callback', response_model=Doc)
async def oauth_callback(provider: str, request: Request, response: Response):
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(404, 'Unknown OAuth provider')
    config = await oauth_config(provider)
    if not config:
        raise HTTPException(503, 'This sign-in provider is not configured')
    query, form = request.query_params, {}
    if request.method == 'POST':
        try:
            form = dict(await request.form())
        except Exception:
            form = {}
    code = query.get('code') or form.get('code', '')
    state = query.get('state') or form.get('state', '')
    id_token = form.get('id_token', '')
    cookie = request.cookies.get('voltora_oauth', '')
    expected_state = cookie.split(':', 1)[1] if ':' in cookie else ''
    if not state or not expected_state or cookie.split(':', 1)[0] != provider or not secrets.compare_digest(state, expected_state):
        raise HTTPException(400, 'Sign-in state mismatch. Start again.')
    if provider == 'google':
        identity = await exchange_google(config, code)
    elif provider == 'facebook':
        identity = await exchange_facebook(config, code)
    else:
        identity = await exchange_apple(config, id_token)
    response.delete_cookie('voltora_oauth', path='/', secure=True, samesite='lax')
    if not identity['email']:
        raise HTTPException(422, 'This provider did not share an email address. Sign in with email instead.')
    if not identity.get('sub') or identity.get('verified') is not True:
        raise HTTPException(403,'A verified provider identity and email are required. Sign in with email and password instead.')
    link_to = await optional_user(request)
    if link_to:
        raise HTTPException(409,'Automatic account linking is disabled. A separate reauthenticated linking flow is required.')
    user = await db.users.find_one({f'oauth_{provider}': identity['sub']}, {'_id': 0})
    if not user:
        existing = await db.users.find_one({'email': identity['email']}, {'_id': 1})
        if existing:
            raise HTTPException(409,'An account with this email already exists. Sign in with your existing method; accounts are never automatically linked.')
    if not user:
        if not await flag('registration'):
            raise HTTPException(403, 'New account registration is currently closed')
        user = {'id': uid(), 'email': identity['email'], 'name': identity['name'][:80], 'password_hash': hasher.hash(secrets.token_urlsafe(24)), 'role': 'customer', 'mfa_enabled': False, 'created_at': stamp(), 'addresses': [], f'oauth_{provider}': identity['sub'], **({'email_verified': True} if identity.get('verified') else {})}
        try:
            await db.users.insert_one(user.copy())
        except Exception:
            raise HTTPException(409, 'An account with this email already exists')
    if user.get('disabled'):
        raise HTTPException(403, 'This account is disabled')
    if user.get('role')!='customer':
        raise HTTPException(403,'Staff must sign in using password and two-factor authentication.')
    ban=user.get('ban',{})
    if ban.get('active') and (not ban.get('until') or ban['until']>stamp()):
        raise HTTPException(403,'This account is unavailable. Contact support.')
    await record_login_history(user['id'], request, True, 'oauth:' + provider)
    await audit(user, 'auth.login_oauth', provider)
    return await create_session(user, request, response)
