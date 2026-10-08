'''Owner profile + brand logo endpoints.

- PUT /api/auth/profile-extended: name, email, phone, avatar URL
- POST /api/admin/brand/logo: upload a store logo (media doc, public URL)
'''
import os
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, EmailStr
from core import db, Input, Doc, uid, stamp, audit
from auth import current_user
from permissions import require

router = APIRouter(prefix='/api/auth', tags=['Owner profile'])
admin_router = APIRouter(prefix='/api/admin/brand', tags=['Brand'])


class ProfileExtended(Input):
    current_password: str = Field(default='', max_length=128)
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str = Field(default='', max_length=25)
    avatar: str = Field(default='', max_length=2000)


@router.put('/profile-extended', response_model=Doc)
async def update_profile_extended(data: ProfileExtended, user=Depends(current_user)):
    email = data.email.lower()
    if email != user['email']:
        from auth import hasher
        try:
            valid = hasher.verify(user['password_hash'], data.current_password)
        except Exception:
            valid = False
        if not valid:
            raise HTTPException(403, 'Confirm your current password before changing your email')
        await db.sessions.delete_many({'user_id': user['id'], 'id': {'$ne': user['session_id']}})
    clash = await db.users.find_one({'email': email, 'id': {'$ne': user['id']}}, {'_id': 1})
    if clash:
        raise HTTPException(409, 'That email is already used by another account')
    update = {'name': data.name, 'email': email, 'phone': data.phone}
    if data.avatar:
        update['avatar'] = data.avatar
    await db.users.update_one({'id': user['id']}, {'$set': update})
    await db.sessions.update_many({'user_id': user['id']}, {'$set': {'profile_version': stamp()}})
    await audit(user, 'profile.updated', user['id'])
    return {'ok': True}


class BrandLogo(Input):
    logo_url: str = Field(min_length=1, max_length=2000)
    logo_height: int = Field(default=36, ge=18, le=120)


@admin_router.put('/logo', response_model=Doc)
async def set_brand_logo(data: BrandLogo, user=Depends(require('settings.update'))):
    url = data.logo_url
    if not (url.startswith('https://') or (url.startswith('/') and not url.startswith('//'))):
        raise HTTPException(422, 'Use a secure URL or a store media path')
    doc = await db.settings.find_one({'id': 'store'}, {'_id': 0})
    await db.settings.update_one({'id': 'store', 'version': doc['version']},
                                 {'$set': {'value.brand_logo': url, 'value.brand_logo_height': data.logo_height}, '$inc': {'version': 1}})
    await audit(user, 'brand.logo_set', url[:200])
    return {'ok': True, 'logo_url': url}


@admin_router.delete('/logo', response_model=Doc)
async def clear_brand_logo(user=Depends(require('settings.update'))):
    doc = await db.settings.find_one({'id': 'store'}, {'_id': 0})
    await db.settings.update_one({'id': 'store', 'version': doc['version']},
                                 {'$unset': {'value.brand_logo': '', 'value.brand_logo_height': ''}, '$inc': {'version': 1}})
    await audit(user, 'brand.logo_cleared')
    return {'ok': True}
