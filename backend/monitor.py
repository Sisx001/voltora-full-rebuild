'''Real-time store monitor: one endpoint that snapshots the whole platform —
orders, visitors, integrations, AI tasks, queues and risk signals — for the
/monitor wall. Cheap aggregation queries only, safe to poll every few seconds.'''
from datetime import timedelta
from fastapi import APIRouter, Depends
from core import db, Doc, now, stamp
from permissions import require
import providers

router = APIRouter(prefix='/api/admin/monitor', tags=['Monitor'])


@router.get('', response_model=Doc)
async def monitor(user=Depends(require('analytics.read'))):
    today_start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff24 = now() - timedelta(hours=24)
    today_iso = today_start.isoformat()

    orders_today = await db.orders.count_documents({'created_at': {'$gte': today_iso}})
    revenue_row = await db.orders.aggregate([
        {'$match': {'created_at': {'$gte': today_iso}, 'payment_status': 'paid'}},
        {'$group': {'_id': None, 'revenue': {'$sum': '$total'}}},
    ]).to_list(1)
    revenue_today = (revenue_row[0]['revenue'] if revenue_row else 0) / 100
    pending_orders = await db.orders.count_documents({'status': {'$in': ['pending', 'initiating', 'awaiting_payment', 'processing']}})
    visitors_24h = await db.visitor_sessions.count_documents({'last_seen': {'$gte': cutoff24.isoformat()}}) if await db.visitor_sessions.count_documents({}) else 0
    visitors_row = await db.visitor_sessions.count_documents({'first_seen': {'$gte': today_iso}})
    inventory = await db.inventory.find_one({'id': 'main'}, {'_id': 0, 'quantities': 1}) or {}
    quantities = inventory.get('quantities', {})
    low_variants = [k for k, v in quantities.items() if 0 < v <= 5]
    out_variants = [k for k, v in quantities.items() if v <= 0]

    # integrations: active provider configs per kind (status from last verify)
    integrations = {}
    async for row in db.provider_configs.find({'enabled': True}, {'_id': 0, 'kind': 1, 'provider': 1, 'status': 1}):
        integrations.setdefault(row['kind'], []).append({'provider': row['provider'], 'status': row.get('status', 'unknown')})

    ai_running = await db.ai_tasks.count_documents({'status': 'running'})
    ai_failed_24h = await db.ai_tasks.count_documents({'status': 'failed', 'created_at': {'$gte': cutoff24.isoformat()}})
    ai_today = await db.ai_tasks.count_documents({'created_at': {'$gte': today_iso}})
    approvals_pending = await db.ai_action_requests.count_documents({'status': 'pending'})
    email_queued = await db.email_queue.count_documents({'status': 'queued'})
    email_failed = await db.email_queue.count_documents({'status': 'failed'})
    risk_24h = await db.login_attempts.count_documents({'success': False, 'created_at': {'$gte': cutoff24}})
    failed_payments_24h = await db.payment_transactions.count_documents({'status': 'failed', 'created_at': {'$gte': stamp()[:10]}}) if await db.payment_transactions.count_documents({}) else 0

    series = []
    for r in await db.orders.aggregate([
        {'$match': {'created_at': {'$gte': (now() - timedelta(days=13)).isoformat()}}},
        {'$group': {'_id': {'$substr': ['$created_at', 0, 10]}, 'orders': {'$sum': 1},
                    'revenue': {'$sum': {'$cond': [{'$eq': ['$payment_status', 'paid']}, '$total', 0]}}}},
        {'$sort': {'_id': 1}},
    ]).to_list(14):
        series.append({'day': r['_id'], 'orders': r['orders'], 'revenue': round(r['revenue'] / 100, 2)})

    return {'generated_at': stamp(),
            'orders_today': orders_today, 'revenue_today': revenue_today, 'pending_orders': pending_orders,
            'visitors_today': visitors_row, 'visitors_24h': max(visitors_24h, visitors_row),
            'low_stock': len(low_variants), 'out_of_stock': len(out_variants),
            'integrations': integrations,
            'ai': {'running': ai_running, 'failed_24h': ai_failed_24h, 'today': ai_today, 'approvals_pending': approvals_pending},
            'queues': {'email_queued': email_queued, 'email_failed': email_failed},
            'signals': {'failed_logins_24h': risk_24h, 'failed_payments_today': failed_payments_24h},
            'series': series}
