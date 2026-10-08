'''Store analytics for the admin dashboard: funnel, search terms, traffic
sources, and device mix. All consent-gated data with 30-day retention.
'''
from datetime import timedelta
from fastapi import APIRouter, Depends
from core import db, Doc, now, audit
from permissions import require

router = APIRouter(prefix='/api/admin/analytics', tags=['Analytics'])


@router.get('', response_model=Doc)
async def analytics(days: int = 30, user=Depends(require('analytics.read'))):
    await audit(user, 'analytics.viewed')
    cutoff = (now() - timedelta(days=min(90, max(7, days)))).isoformat()
    match = {'created_at': {'$gte': cutoff}}
    funnel_events = ['page_view', 'product_view', 'add_to_cart', 'begin_checkout', 'purchase']
    funnel_counts = await db.events.aggregate([
        {'$match': {**match, 'event': {'$in': funnel_events}}},
        {'$group': {'_id': '$event', 'count': {'$sum': 1}}},
    ]).to_list(20)
    funnel = {row['_id']: row['count'] for row in funnel_counts}
    search_terms = await db.events.aggregate([
        {'$match': {**match, 'event': 'search', 'term': {'$ne': ''}}},
        {'$group': {'_id': '$term', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}, {'$limit': 10},
    ]).to_list(10)
    top_pages = await db.events.aggregate([
        {'$match': {**match, 'event': 'page_view'}},
        {'$group': {'_id': '$path', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}, {'$limit': 10},
    ]).to_list(10)
    top_products = await db.events.aggregate([
        {'$match': {**match, 'event': 'product_view'}},
        {'$group': {'_id': '$path', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}, {'$limit': 10},
    ]).to_list(10)
    devices = await db.visitor_sessions.aggregate([
        {'$match': {'first_seen': {'$gte': cutoff}}},
        {'$group': {'_id': '$device_type', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
    ]).to_list(10)
    sources = await db.visitor_sessions.aggregate([
        {'$match': {'first_seen': {'$gte': cutoff}}},
        {'$group': {'_id': {'source': {'$ifNull': ['$utm.utm_source', 'direct']}}, 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}, {'$limit': 10},
    ]).to_list(10)
    daily = await db.events.aggregate([
        {'$match': match},
        {'$group': {'_id': {'day': {'$substr': ['$created_at', 0, 10]}}, 'events': {'$sum': 1}, 'visitors': {'$addToSet': '$visitor_id'}}},
        {'$project': {'date': '$_id.day', 'events': 1, 'visitors': {'$size': '$visitors'}}},
        {'$sort': {'date': 1}},
    ]).to_list(100)
    visitors = await db.visitor_sessions.count_documents({'first_seen': {'$gte': cutoff}})
    return {'funnel': [{'event': e, 'count': funnel.get(e, 0)} for e in funnel_events],
            'search_terms': [{'term': s['_id'], 'count': s['count']} for s in search_terms],
            'top_pages': [{'path': p['_id'], 'count': p['count']} for p in top_pages],
            'top_products': [{'path': p['_id'], 'count': p['count']} for p in top_products],
            'devices': [{'device': d['_id'] or 'unknown', 'count': d['count']} for d in devices],
            'sources': [{'source': s['_id']['source'] or 'direct', 'count': s['count']} for s in sources],
            'daily': daily, 'visitors': visitors,
            'note': 'Consent-gated data only. Visitor analytics are retained for 30 days.'}
