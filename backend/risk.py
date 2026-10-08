"""Suspicious-activity risk signals: computed from real telemetry, presented
as review flags - never automatic accusations or auto-punishment."""
from datetime import timedelta
from fastapi import APIRouter, Depends
from core import db, Doc, now, audit
from permissions import require

router = APIRouter(prefix='/api/admin/security', tags=['Risk signals'])

SEVERITY_RANK = {'low': 0, 'medium': 1, 'high': 2}


async def compute_risk_signals():
    signals = []
    cutoff24 = now() - timedelta(hours=24)  # datetime: login_attempts stores datetime objects
    bursts = await db.login_attempts.aggregate([
        {'$match': {'success': False, 'created_at': {'$gte': cutoff24}}},
        {'$group': {'_id': '$key', 'count': {'$sum': 1}}},
        {'$match': {'count': {'$gte': 5}}},
        {'$sort': {'count': -1}}, {'$limit': 5},
    ]).to_list(5)
    for b in bursts:
        signals.append({'kind': 'failed_login_burst', 'severity': 'high' if b['count'] >= 15 else 'medium',
                        'detail': str(b['count']) + ' failed sign-ins against one account key (hashed) in 24h',
                        'affected': b['_id'][:12] + '...'})
    failed_tx = await db.payment_transactions.count_documents({'status': 'failed', 'created_at': {'$gte': cutoff24}})
    if failed_tx >= 5:
        signals.append({'kind': 'payment_failures', 'severity': 'medium' if failed_tx < 15 else 'high',
                        'detail': str(failed_tx) + ' failed payment transactions in 24h', 'affected': 'checkout'})
    failed_ship = await db.shipments.count_documents({'status': 'failed', 'created_at': {'$gte': cutoff24}})
    if failed_ship >= 3:
        signals.append({'kind': 'courier_failures', 'severity': 'medium',
                        'detail': str(failed_ship) + ' courier bookings failed in 24h', 'affected': 'fulfillment'})
    ai_failed = await db.ai_tasks.count_documents({'status': 'failed', 'created_at': {'$gte': cutoff24}})
    if ai_failed >= 10:
        signals.append({'kind': 'ai_failures', 'severity': 'low',
                        'detail': str(ai_failed) + ' AI tasks failed in 24h', 'affected': 'AI features'})
    failed_orders = await db.orders.count_documents({'status': 'failed', 'created_at': {'$gte': cutoff24}})
    if failed_orders >= 8:
        signals.append({'kind': 'failed_checkouts', 'severity': 'medium',
                        'detail': str(failed_orders) + ' checkout attempts failed in 24h (possible bot pressure)', 'affected': 'checkout'})
    signals.sort(key=lambda s: -SEVERITY_RANK.get(s['severity'], 0))
    return signals


@router.get('/risk', response_model=Doc)
async def risk_signals(user=Depends(require('security.read'))):
    await audit(user, 'security.risk_viewed')
    return {'signals': await compute_risk_signals(), 'note': 'Risk signals are review flags, not automatic accusations. Review before acting.'}
