'''Custom role management: staff roles beyond the built-ins, edited from the
admin Team page. Editing or deleting a role revokes that role's sessions so
permission changes take effect immediately.
'''
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from core import db, Doc, Input, stamp, audit
from permissions import require, BUILT_IN_ROLES, DOMAINS, VERBS, ALL, ROLE_IDS

router = APIRouter(prefix='/api/admin/roles', tags=['Roles'])


class RoleSave(Input):
    id: str = Field(pattern=r'^[a-z0-9-]{2,40}$')
    name: str = Field(min_length=2, max_length=60)
    description: str = Field(default='', max_length=300)
    permissions: list[str] = Field(default_factory=list, max_length=500)


def validate_permissions(items):
    bad = [p for p in items if p not in ALL]
    if bad:
        raise HTTPException(422, 'Unknown permission: ' + bad[0])
    return sorted(set(items))


@router.get('', response_model=Doc)
async def list_roles(user=Depends(require('roles.read'))):
    custom = await db.roles.find({}, {'_id': 0}).sort('name', 1).to_list(100)
    built = [{'id': rid, 'name': rid.replace('_', ' ').title(), 'description': 'Built-in role', 'permissions': perms, 'built_in': True} for rid, perms in BUILT_IN_ROLES.items() if rid not in ('owner', 'customer')]
    return {'domains': DOMAINS, 'verbs': VERBS, 'roles': built + [{**r, 'built_in': r.get('built_in', False)} for r in custom]}


@router.post('', response_model=Doc)
async def create_role(data: RoleSave, user=Depends(require('roles.update'))):
    if data.id in BUILT_IN_ROLES or await db.roles.find_one({'id': data.id}):
        raise HTTPException(409, 'A role with this id already exists')
    perms = validate_permissions(data.permissions)
    row = {'id': data.id, 'name': data.name, 'description': data.description, 'permissions': perms, 'built_in': False, 'created_at': stamp()}
    await db.roles.insert_one(row.copy())
    await audit(user, 'role.created', data.id, data.name)
    return row


@router.put('/{id}', response_model=Doc)
async def update_role(id: str, data: RoleSave, user=Depends(require('roles.update'))):
    if id in BUILT_IN_ROLES:
        raise HTTPException(403, 'Built-in roles cannot be edited. Create a custom role instead.')
    if not await db.roles.find_one({'id': id}):
        raise HTTPException(404, 'Role not found')
    perms = validate_permissions(data.permissions)
    await db.roles.update_one({'id': id}, {'$set': {'name': data.name, 'description': data.description, 'permissions': perms, 'updated_at': stamp()}})
    await db.sessions.delete_many({'user_id': {'$in': [u['id'] for u in await db.users.find({'role': id}, {'_id': 0, 'id': 1}).to_list(500)]}})
    await audit(user, 'role.updated', id, data.name)
    return {'ok': True}


@router.delete('/{id}', response_model=Doc)
async def delete_role(id: str, user=Depends(require('roles.update'))):
    if id in BUILT_IN_ROLES:
        raise HTTPException(403, 'Built-in roles cannot be deleted.')
    holders = await db.users.count_documents({'role': id})
    if holders:
        raise HTTPException(422, f'{holders} team member(s) still use this role. Reassign them first.')
    result = await db.roles.delete_one({'id': id, 'built_in': {'$ne': True}})
    if not result.deleted_count:
        raise HTTPException(404, 'Role not found')
    await audit(user, 'role.deleted', id)
    return {'ok': True}
