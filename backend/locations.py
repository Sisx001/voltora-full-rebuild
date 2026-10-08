'''Bangladesh location system: division -> district -> upazila/thana -> area (post office) -> postcode.

Public endpoints power checkout address selection and search; the admin endpoints
manage the hierarchy (edit, activate/deactivate, import). POST /api/locations/resolve
is an AI-assisted address lookup - a search tool, not a chat surface.
'''
import json
import re
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import Field
from core import db, Input, Doc, uid, stamp, audit, flag, settings
from auth import current_user
from permissions import require

router = APIRouter(prefix='/api/locations', tags=['Locations'])
admin_router = APIRouter(prefix='/api/admin/locations', tags=['Locations'])

DATA_FILE = Path(__file__).parent / 'data' / 'bd_locations.json'
PUBLIC_PROJECTION = {'_id': 0, 'id': 1, 'kind': 1, 'parent_id': 1, 'district_id': 1, 'upazila_id': 1, 'name': 1, 'name_bn': 1, 'postcode': 1, 'thana': 1}


async def load_seed_data():
    if not DATA_FILE.exists():
        return {'divisions': [], 'districts': [], 'upazilas': [], 'areas': []}
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))


async def seed_locations():
    '''One-time bulk insert of the bundled Bangladesh dataset (admin edits are never overwritten).'''
    if await db.locations.count_documents({}) >= 100:
        return
    data = await load_seed_data()
    docs = []
    for d in data['divisions']:
        docs.append({'id': d['id'], 'kind': 'division', 'parent_id': '', 'name': d['name'], 'name_bn': d.get('name_bn', ''), 'postcode': '', 'thana': '', 'active': True, 'source': 'bd'})
    for d in data['districts']:
        docs.append({'id': d['id'], 'kind': 'district', 'parent_id': d['division_id'], 'name': d['name'], 'name_bn': d.get('name_bn', ''), 'postcode': '', 'thana': '', 'active': True, 'source': 'bd'})
    for d in data['upazilas']:
        docs.append({'id': d['id'], 'kind': 'upazila', 'parent_id': d['district_id'], 'name': d['name'], 'name_bn': d.get('name_bn', ''), 'postcode': '', 'thana': '', 'active': True, 'source': 'bd'})
    for d in data['areas']:
        docs.append({'id': d['id'], 'kind': 'area', 'parent_id': d['upazila_id'] or d['district_id'], 'district_id': d['district_id'], 'upazila_id': d.get('upazila_id', ''), 'name': d['name'], 'name_bn': d.get('name_bn', ''), 'postcode': d.get('postcode', ''), 'thana': d.get('thana', ''), 'active': True, 'source': 'bd'})
    if docs:
        await db.locations.insert_many([x.copy() for x in docs])


# ---------- public ----------

@router.get('/tree', response_model=Doc)
async def tree():
    '''Compact active hierarchy for address pickers: divisions with nested district ids.'''
    divisions = await db.locations.find({'kind': 'division', 'active': True}, {'_id': 0, 'id': 1, 'name': 1, 'name_bn': 1}).sort('name', 1).to_list(10)
    districts = await db.locations.find({'kind': 'district', 'active': True}, {'_id': 0, 'id': 1, 'parent_id': 1, 'name': 1, 'name_bn': 1}).sort('name', 1).to_list(80)
    for div in divisions:
        div['districts'] = [d for d in districts if d['parent_id'] == div['id']]
    return {'divisions': divisions}


@router.get('/districts/{district_id}/children', response_model=Doc)
async def district_children(district_id: str):
    district = await db.locations.find_one({'id': district_id, 'kind': 'district', 'active': True}, {'_id': 0, 'id': 1, 'name': 1, 'name_bn': 1})
    if not district:
        raise HTTPException(404, 'District not found')
    district_slug = district_id.removeprefix('dis:')
    upazilas = await db.locations.find({'kind': 'upazila', 'active': True, 'id': {'$regex': '^upa:' + re.escape(district_slug) + '-'}}, {'_id': 0, 'id': 1, 'name': 1, 'name_bn': 1, 'postcode': 1}).sort('name', 1).to_list(80)
    areas = await db.locations.find({'kind': 'area', 'active': True, 'district_id': district_id}, {'_id': 0, 'id': 1, 'parent_id': 1, 'upazila_id': 1, 'name': 1, 'name_bn': 1, 'postcode': 1, 'thana': 1}).sort('name', 1).to_list(200)
    return {'district': district, 'upazilas': upazilas, 'areas': areas}


@router.get('/upazilas/{upazila_id}/areas', response_model=list[Doc])
async def upazila_areas(upazila_id: str):
    return await db.locations.find({'kind': 'area', 'active': True, 'upazila_id': upazila_id}, PUBLIC_PROJECTION).sort('name', 1).to_list(100)


@router.get('/search', response_model=list[Doc])
async def search(q: str = Query(..., min_length=2, max_length=120)):
    '''Ranked location search across area/upazila/district names (en/bn), post office
    thana names, and postcodes: exact > prefix > contains.'''
    term = q.strip()
    if term.isdigit():
        rows = await db.locations.find({'kind': 'area', 'active': True, 'postcode': term}, PUBLIC_PROJECTION).sort('name', 1).to_list(30)
        if rows:
            return rows
    pattern = re.escape(term)
    bn_pattern = re.escape(term)
    def where(modifier):
        fields = [{'name': {'$regex': modifier(pattern), '$options': 'i'}}, {'name_bn': {'$regex': modifier(bn_pattern)}}, {'thana': {'$regex': modifier(pattern), '$options': 'i'}}, {'thana_bn': {'$regex': modifier(bn_pattern)}}]
        return {'active': True, 'kind': {'$ne': 'division'}, '$or': fields}
    exact = await db.locations.find(where(lambda p: '^' + p + '$'), PUBLIC_PROJECTION).sort('kind', 1).to_list(10)
    prefix = await db.locations.find(where(lambda p: '^' + p), PUBLIC_PROJECTION).sort('kind', 1).to_list(max(0, 25 - len(exact)))
    contains = await db.locations.find(where(lambda p: p), PUBLIC_PROJECTION).sort('kind', 1).to_list(40)
    seen, result = set(), []
    for row in exact + prefix + contains:
        if row['id'] not in seen:
            seen.add(row['id'])
            result.append(row)
    return result[:40]


class ResolveQuery(Input):
    query: str = Field(min_length=3, max_length=300)


@router.post('/resolve', response_model=Doc)
async def resolve(data: ResolveQuery):
    '''AI-assisted address resolution (search only - no chat): deterministic scoring
    first, then an optional AI normalization step constrained to real database rows.'''
    candidates = await search_public(data.query)
    result = {'query': data.query, 'candidates': candidates, 'mode': 'fuzzy'}
    if not candidates or await flag('ai_location'):
        ai_candidates = await ai_resolve(data.query, candidates)
        if ai_candidates:
            result['candidates'] = ai_candidates
            result['mode'] = 'ai'
    if not result['candidates']:
        raise HTTPException(404, 'No matching location found. Try a district, upazila, or postcode.')
    return result


async def search_public(query):
    rows = await search(query if len(query) >= 2 else query.strip()[:2])
    return [r for r in rows if r['kind'] in ('district', 'upazila', 'area')][:12]


async def ai_resolve(query, candidates):
    from ai_monitor import task_begin, task_finish
    config = await db.integrations.find_one({'id': 'deepseek', 'connected': True}, {'_id': 0})
    if not config:
        return []
    monitor_id = await task_begin('location', {'id': 'system', 'name': 'Location search'}, 'address_resolve', config['model'])
    try:
        from ai import DeepSeekAdapter
        known = '\n'.join(f"- kind={r['kind']} id={r['id']} name={r['name']} bn={r.get('name_bn','')} postcode={r.get('postcode','')}" for r in candidates[:30]) or '(no fuzzy matches)'
        system = ('You resolve messy Bangladeshi delivery addresses to database location rows. '
                  'Choose only from the supplied candidate ids - never invent ids or postcodes. '
                  'Reply with strict JSON: {"matches":[{"id":"...","confidence":0.0}]}, best first, at most 5. No commentary.')
        messages = [{'role': 'system', 'content': system},
                    {'role': 'user', 'content': f'Address: {query!r}\nCandidate rows:\n{known}'}]
        text = ''
        async for event in DeepSeekAdapter().stream(config, messages):
            if 'text' in event:
                text += event['text']
            if 'error' in event:
                return []
        match = re.search(r'\{.*\}', text, re.S)
        if not match:
            return []
        parsed = json.loads(match.group(0))
        out = []
        for item in parsed.get('matches', [])[:5]:
            row = await db.locations.find_one({'id': str(item.get('id', '')), 'active': True}, PUBLIC_PROJECTION)
            if row and float(item.get('confidence', 0)) >= 0.3:
                row['confidence'] = round(float(item.get('confidence', 0)), 2)
                out.append(row)
        await task_finish(monitor_id, 'completed' if out else 'failed', error='' if out else 'no confident match')
        return out
    except Exception as error:
        await task_finish(monitor_id, 'failed', error=error)
        return []


# ---------- admin ----------

class LocationSave(Input):
    kind: Literal['division', 'district', 'upazila', 'area']
    parent_id: str = Field(default='', max_length=120)
    name: str = Field(min_length=1, max_length=120)
    name_bn: str = Field(default='', max_length=120)
    postcode: str = Field(default='', max_length=10)
    active: bool = True


@admin_router.get('', response_model=Doc)
async def admin_list(kind: str = '', parent_id: str = '', q: str = '', active: str = '', page: int = 1, user=Depends(require('locations.read'))):
    query = {}
    if kind:
        query['kind'] = kind
    if parent_id:
        query['$or'] = [{'parent_id': parent_id}, {'district_id': parent_id}]
    if active in ('true', 'false'):
        query['active'] = active == 'true'
    if q:
        pattern = re.escape(q)
        query['$or'] = [{'name': {'$regex': pattern, '$options': 'i'}}, {'name_bn': {'$regex': re.escape(q)}}, {'postcode': q}]
    total = await db.locations.count_documents(query)
    rows = await db.locations.find(query, {'_id': 0}).sort([('kind', 1), ('name', 1)]).skip((max(1, page) - 1) * 100).to_list(100)
    return {'total': total, 'items': rows}


@admin_router.post('', response_model=Doc)
async def admin_create(data: LocationSave, user=Depends(require('locations.update'))):
    if data.kind != 'division' and not data.parent_id:
        raise HTTPException(422, 'A parent location is required')
    if data.parent_id and not await db.locations.find_one({'id': data.parent_id}):
        raise HTTPException(422, 'Parent location does not exist')
    slug = re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-') or uid()[:8]
    row = {'id': f"{data.kind}:{slug}-{uid()[:6]}", 'kind': data.kind, 'parent_id': data.parent_id,
           'district_id': data.parent_id if data.kind == 'area' else '', 'upazila_id': data.parent_id if data.kind == 'area' else '',
           'name': data.name, 'name_bn': data.name_bn, 'postcode': data.postcode, 'thana': '', 'active': data.active,
           'source': 'custom', 'created_at': stamp()}
    if data.kind == 'area':
        parent = await db.locations.find_one({'id': data.parent_id}, {'_id': 0, 'kind': 1})
        if parent and parent['kind'] == 'upazila':
            upa = await db.locations.find_one({'id': data.parent_id}, {'_id': 0})
            district = next((d for d in [upa.get('parent_id')] if d), '')
            row['upazila_id'] = data.parent_id
            row['district_id'] = district
    await db.locations.insert_one(row.copy())
    await audit(user, 'location.created', row['id'], data.name)
    return row


@admin_router.put('/{id}', response_model=Doc)
async def admin_update(id: str, data: LocationSave, user=Depends(require('locations.update'))):
    row = await db.locations.find_one({'id': id}, {'_id': 0})
    if not row:
        raise HTTPException(404, 'Location not found')
    updates = {'name': data.name, 'name_bn': data.name_bn, 'postcode': data.postcode, 'active': data.active, 'updated_at': stamp()}
    if data.parent_id and data.parent_id != row.get('parent_id') and row['kind'] != 'division':
        if not await db.locations.find_one({'id': data.parent_id}):
            raise HTTPException(422, 'Parent location does not exist')
        updates['parent_id'] = data.parent_id
    await db.locations.update_one({'id': id}, {'$set': updates})
    await audit(user, 'location.updated', id, data.name)
    return {'ok': True}


@admin_router.post('/{id}/toggle', response_model=Doc)
async def admin_toggle(id: str, user=Depends(require('locations.update'))):
    row = await db.locations.find_one({'id': id}, {'_id': 0, 'active': 1})
    if not row:
        raise HTTPException(404, 'Location not found')
    await db.locations.update_one({'id': id}, {'$set': {'active': not row.get('active', True)}})
    await audit(user, 'location.toggled', id, str(not row.get('active', True)))
    return {'ok': True, 'active': not row.get('active', True)}


@admin_router.delete('/{id}', response_model=Doc)
async def admin_delete(id: str, user=Depends(require('locations.update'))):
    row = await db.locations.find_one({'id': id}, {'_id': 0})
    if not row:
        raise HTTPException(404, 'Location not found')
    children = await db.locations.count_documents({'$or': [{'parent_id': id}, {'district_id': id}, {'upazila_id': id}]})
    if children:
        raise HTTPException(409, f'This location has {children} children. Remove or move them first.')
    await db.locations.delete_one({'id': id})
    await audit(user, 'location.deleted', id, row.get('name', ''))
    return {'ok': True}


class LocationImport(Input):
    items: list[dict] = Field(min_length=1, max_length=5000)


@admin_router.post('/import', response_model=Doc)
async def admin_import(data: LocationImport, user=Depends(require('locations.update'))):
    '''Bulk import: {items:[{kind,parent_id,name,name_bn?,postcode?,active?,id?}]}.
    Existing ids are left untouched; new rows are inserted.'''
    docs, skipped = [], 0
    for item in data.items:
        kind = item.get('kind')
        if kind not in ('division', 'district', 'upazila', 'area') or not item.get('name'):
            skipped += 1
            continue
        if kind != 'division' and not item.get('parent_id'):
            skipped += 1
            continue
        doc = {'id': item.get('id') or f"{kind}:{re.sub(r'[^a-z0-9]+','-',str(item['name']).lower()).strip('-')}-{uid()[:6]}",
               'kind': kind, 'parent_id': item.get('parent_id', ''), 'district_id': item.get('district_id', ''), 'upazila_id': item.get('upazila_id', ''),
               'name': str(item['name'])[:120], 'name_bn': str(item.get('name_bn', ''))[:120],
               'postcode': str(item.get('postcode', ''))[:10], 'thana': str(item.get('thana', ''))[:120],
               'active': bool(item.get('active', True)), 'source': 'import', 'created_at': stamp()}
        docs.append(doc)
    if docs:
        result = await db.locations.insert_many([d.copy() for d in docs], ordered=False)
        await audit(user, 'location.imported', detail=f'{len(result.inserted_ids)} imported, {skipped} skipped')
        return {'imported': len(result.inserted_ids), 'skipped': skipped}
    raise HTTPException(422, 'No valid rows found in the import payload')
