import os
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import EmailStr, Field
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
import pyotp
from pymongo.errors import DuplicateKeyError
from core import db, Input, Doc, now, stamp, uid, digest, flag, audit, record_login_history
from permissions import permissions, role_permissions, BUILT_IN_ROLES
from vault import seal, unseal
from schemas import Address

router = APIRouter(prefix='/api/auth', tags=['Identity'])
hasher = PasswordHasher()

class Credentials(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    captcha_token: str = Field(default='', max_length=3000)

class Registration(Credentials):
    name: str = Field(min_length=2, max_length=80)

class Setup(Registration):
    setup_key: str

class Code(Input):
    code: str = Field(pattern=r'^\d{6}$')

def public_user(user):
    return {k:user.get(k) for k in ['id','email','name','role','addresses','created_at','mfa_enabled']} | {'permissions':permissions(user), 'mfa_verified':bool(user.get('session_mfa')), 'requires_mfa':user.get('role')!='customer' and not user.get('session_mfa')}

async def optional_user(request: Request):
    raw = request.cookies.get('voltora_session')
    if not raw:
        return None
    session = await db.sessions.find_one({'token_hash':digest(raw), 'expires_at':{'$gt':now()}}, {'_id':0})
    if not session:
        return None
    user = await db.users.find_one({'id':session['user_id'], 'disabled':{'$ne':True}}, {'_id':0})
    if not user:
        return None
    ban = user.get('ban', {})
    if ban.get('active') and (not ban.get('until') or ban['until'] > now().isoformat()):
        return None
    user['session_id'] = session['id']
    user['session_mfa'] = session.get('mfa', False)
    user['csrf'] = session['csrf']
    user['permissions'] = await role_permissions(user.get('role'))
    return user

async def current_user(request:Request):
    user = await optional_user(request)
    if not user:
        raise HTTPException(401, 'Please sign in to continue')
    if request.method not in ('GET','HEAD','OPTIONS') and not secrets.compare_digest(request.headers.get('x-csrf-token',''), user['csrf']):
        raise HTTPException(403, 'Refresh the page and try again')
    return user

async def create_session(user, request, response, mfa=False):
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(24)
    expires = now()+timedelta(hours=1 if user['role']!='customer' else 24)
    perms = user.get('permissions') if isinstance(user.get('permissions'), list) else await role_permissions(user.get('role'))
    await db.sessions.insert_one({'id':uid(),'user_id':user['id'],'token_hash':digest(token),'csrf':csrf,'mfa':mfa,'permissions':perms,'created_at':stamp(),'expires_at':expires,'device':request.headers.get('user-agent','')[:200]})
    secure_cookie=True
    response.set_cookie('voltora_session',token,httponly=True,secure=secure_cookie,samesite='lax',max_age=int((expires-now()).total_seconds()),path='/')
    user['session_mfa']=mfa
    user['permissions']=perms
    return {'user':public_user(user),'csrf':csrf}

async def throttle(request,email):
    cutoff=now()-timedelta(minutes=15)
    key=digest(email.lower())
    if await db.login_attempts.count_documents({'key':key,'created_at':{'$gt':cutoff},'success':False}) >= 8:
        raise HTTPException(429,'Too many attempts. Try again in 15 minutes.')
    return key

@router.get('/setup-status', response_model=Doc)
async def setup_status():
    return {'required':not bool(await db.users.find_one({'role':'owner'}))}

@router.post('/setup', response_model=Doc)
async def setup(data:Setup, request:Request, response:Response):
    if not os.environ.get('OWNER_SETUP_KEY') or not secrets.compare_digest(data.setup_key,os.environ['OWNER_SETUP_KEY']):
        raise HTTPException(403,'Invalid owner setup key')
    if len(data.password)<12:
        raise HTTPException(422,'Use a password of at least 12 characters')
    if await db.users.find_one({'role':'owner'}):
        raise HTTPException(409,'Owner account already exists')
    user={'id':'initial-owner','email':data.email.lower(),'name':data.name,'password_hash':hasher.hash(data.password),'role':'owner','mfa_enabled':False,'created_at':stamp(),'addresses':[]}
    try:
        await db.users.insert_one(user.copy())
    except DuplicateKeyError:
        raise HTTPException(409,'Owner setup is already complete')
    await audit(user,'owner.created')
    return await create_session(user,request,response)

@router.post('/register', response_model=Doc)
async def register(data:Registration, request:Request, response:Response):
    from captcha import enforce_captcha
    await enforce_captcha(request,'signup',data.captcha_token)
    if not await flag('registration'):
        raise HTTPException(403,'New account registration is currently closed')
    if len(data.password)<10:
        raise HTTPException(422,'Use a password of at least 10 characters')
    user={'id':uid(),'email':data.email.lower(),'name':data.name,'password_hash':hasher.hash(data.password),'role':'customer','mfa_enabled':False,'created_at':stamp(),'addresses':[]}
    try:
        await db.users.insert_one(user.copy())
    except DuplicateKeyError:
        raise HTTPException(409,'An account with this email already exists')
    return await create_session(user,request,response)

@router.post('/login', response_model=Doc)
async def login(data:Credentials, request:Request, response:Response):
    from captcha import enforce_captcha
    user_probe=await db.users.find_one({'email':data.email.lower()},{'_id':0,'role':1})
    await enforce_captcha(request,'admin_login' if user_probe and user_probe.get('role')!='customer' else 'signup',data.captcha_token)
    key=await throttle(request,data.email)
    user=await db.users.find_one({'email':data.email.lower(),'disabled':{'$ne':True}},{'_id':0})
    if user and user.get('ban',{}).get('active'):
        ban=user['ban']
        until=ban.get('until','')
        if until and until<=now().isoformat():
            await db.users.update_one({'id':user['id']},{'$set':{'ban.active':False}})
        else:
            await record_login_history(user['id'],request,False,'password')
            msg='Your account is '+('banned' if not until else 'suspended until '+until[:10])+'.'
            if ban.get('reason'):msg+=' Reason: '+ban['reason']
            raise HTTPException(403,msg)
    valid=False
    try:
        valid=bool(user and hasher.verify(user['password_hash'],data.password))
    except (VerifyMismatchError,InvalidHashError):
        pass
    await db.login_attempts.insert_one({'id':uid(),'key':key,'success':valid,'created_at':now(),'expires_at':now()+timedelta(days=90),'ip':request.client.host if request.client else ''})
    if user:await record_login_history(user['id'],request,valid,'password')
    if not valid:
        if user and user.get('role')!='customer':
            from alerts import send_alert
            await send_alert('admin_login_failed','medium','Failed admin sign-in',f"Account {user.get('email','')} had a failed sign-in attempt from {request.client.host if request.client else 'unknown'}.")
        raise HTTPException(401,'The email or password is incorrect')
    await audit(user,'auth.login')
    if user.get('role')!='customer':
        from alerts import send_alert
        await send_alert('admin_login','low','Admin signed in',f"{user.get('name','')} ({user.get('email','')}) signed in from {request.client.host if request.client else 'unknown'}.")
    return await create_session(user,request,response)

class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

@router.post('/password/change', response_model=Doc)
async def password_change(data:PasswordChange, request:Request, user=Depends(current_user)):
    from argon2.exceptions import VerifyMismatchError, InvalidHashError
    valid=False
    try:
        valid=bool(hasher.verify(user['password_hash'],data.current_password))
    except (VerifyMismatchError,InvalidHashError):
        pass
    if not valid:
        raise HTTPException(403,'Your current password is incorrect')
    if data.current_password==data.new_password:
        raise HTTPException(422,'The new password must be different')
    await db.users.update_one({'id':user['id']},{'$set':{'password_hash':hasher.hash(data.new_password)}})
    await db.sessions.delete_many({'user_id':user['id'],'id':{'$ne':user['session_id']}})
    await audit(user,'auth.password_changed')
    return {'ok':True,'note':'Password changed. Other devices were signed out.'}

@router.get('/me', response_model=Doc)
async def me(user=Depends(current_user)):
    return {'user':public_user(user),'csrf':user['csrf']}

@router.get('/session', response_model=Doc)
async def session_status(request:Request):
    user=await optional_user(request)
    return {'user':public_user(user) if user else None,'csrf':user['csrf'] if user else ''}

@router.post('/logout', response_model=Doc)
async def logout(response:Response,user=Depends(current_user)):
    await db.sessions.delete_one({'id':user['session_id']})
    response.delete_cookie('voltora_session',path='/',secure=True,samesite='lax')
    return {'ok':True}

@router.post('/mfa/enroll', response_model=Doc)
async def enroll(user=Depends(current_user)):
    if user.get('mfa_enabled'):
        raise HTTPException(409,'Two-factor authentication is already enabled')
    secret=pyotp.random_base32()
    await db.users.update_one({'id':user['id']},{'$set':{'mfa_pending':seal(secret)}})
    return {'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(user['email'],issuer_name='VOLTORA')}

@router.post('/mfa/verify', response_model=Doc)
async def verify(data:Code, request:Request, response:Response,user=Depends(current_user)):
    await throttle(request,'mfa:'+user['id'])
    encrypted=user.get('mfa_secret') if user.get('mfa_enabled') else user.get('mfa_pending')
    secret=unseal(encrypted) if encrypted else None
    valid=bool(secret and pyotp.TOTP(secret).verify(data.code,valid_window=1))
    await db.login_attempts.insert_one({'key':digest('mfa:'+user['id']),'success':valid,'created_at':now(),'expires_at':now()+timedelta(days=90)})
    if not valid:
        raise HTTPException(400,'Invalid authentication code')
    totp=pyotp.TOTP(secret)
    instant=now()
    timecode=next(totp.timecode(instant)+offset for offset in (-1,0,1) if secrets.compare_digest(totp.at(instant.timestamp()+offset*totp.interval),data.code))
    result=await db.users.update_one({'id':user['id'],'$or':[{'mfa_last_step':{'$exists':False}},{'mfa_last_step':{'$lt':timecode}}]},{'$set':{'mfa_secret':seal(secret),'mfa_enabled':True,'mfa_last_step':timecode},'$unset':{'mfa_pending':''}})
    if not result.modified_count:
        raise HTTPException(409,'This code has already been used. Wait for a new code.')
    await db.sessions.delete_one({'id':user['session_id']})
    user['mfa_enabled']=True
    await audit(user,'auth.mfa_verified')
    return await create_session(user,request,response,True)

@router.get('/sessions', response_model=list[Doc])
async def sessions(user=Depends(current_user)):
    rows=await db.sessions.find({'user_id':user['id'],'expires_at':{'$gt':now()}},{'_id':0,'token_hash':0,'csrf':0}).to_list(100)
    for row in rows:
        row['current']=row['id']==user['session_id']
    return rows

@router.delete('/sessions/{session_id}', response_model=Doc)
async def revoke(session_id:str,user=Depends(current_user)):
    await db.sessions.delete_one({'id':session_id,'user_id':user['id']})
    return {'ok':True}

class Profile(Input):
    name: str = Field(min_length=2,max_length=80)
    addresses: list[Address] = Field(default=[],max_length=10)

@router.put('/profile', response_model=Doc)
async def profile(data:Profile,user=Depends(current_user)):
    await db.users.update_one({'id':user['id']},{'$set':data.model_dump()})
    return {'ok':True}