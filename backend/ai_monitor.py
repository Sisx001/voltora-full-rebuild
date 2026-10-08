'''AI activity monitoring: every AI operation becomes a tracked task.

ai_tasks rows record what the AI did, is doing, and what failed - kind,
user, model, tools invoked, duration, token usage, and the linked ai_usage
row. The monitor endpoint aggregates running work, recent history, pending
human approvals, and today's usage against the daily limit.
'''
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from core import db, Doc, now, stamp, uid
from permissions import require

router = APIRouter(prefix='/api/admin/ai', tags=['AI monitoring'])


async def task_begin(kind: str, user, task: str, model: str = '') -> str:
    task_id = uid()
    await db.ai_tasks.insert_one({'id': task_id, 'kind': kind, 'status': 'running',
                                  'user_id': (user or {}).get('id', ''), 'user': (user or {}).get('name', ''),
                                  'task': task[:80], 'model': model[:80], 'tools': [],
                                  'started_at': stamp(), 'finished_at': '', 'duration_ms': None,
                                  'usage': {}, 'usage_id': '', 'error': '', 'created_at': stamp()})
    return task_id


async def task_tools(task_id: str, tools: list):
    if tools:
        await db.ai_tasks.update_one({'id': task_id}, {'$set': {'tools': [str(t)[:60] for t in tools][:20]}})


async def task_finish(task_id: str, status: str = 'completed', usage=None, error='', usage_id=''):
    row = await db.ai_tasks.find_one({'id': task_id}, {'_id': 0, 'started_at': 1})
    duration = None
    if row:
        try:
            duration = int((now() - datetime.fromisoformat(row['started_at'])).total_seconds() * 1000)
        except Exception:
            pass
    await db.ai_tasks.update_one({'id': task_id}, {'$set': {'status': status, 'finished_at': stamp(),
                                                           'duration_ms': duration, 'usage': usage or {},
                                                           'usage_id': usage_id, 'error': str(error)[:400]}})


@router.get('/monitor', response_model=Doc)
async def monitor(user=Depends(require('ai.read'))):
    running = await db.ai_tasks.find({'status': 'running'}, {'_id': 0}).sort('started_at', -1).to_list(20)
    recent = await db.ai_tasks.find({'status': {'$ne': 'running'}}, {'_id': 0}).sort('created_at', -1).to_list(50)
    pending_approvals = await db.ai_action_requests.count_documents({'status': 'pending'})
    approvals = await db.ai_action_requests.find({'status': 'pending'}, {'_id': 0}).sort('created_at', -1).to_list(20)
    today = now().date().isoformat()
    by_task = await db.ai_tasks.aggregate([
        {'$match': {'created_at': {'$regex': '^' + today}}},
        {'$group': {'_id': {'task': '$task', 'status': '$status'}, 'count': {'$sum': 1}}},
    ]).to_list(30)
    per_user = await db.ai_tasks.aggregate([
        {'$match': {'created_at': {'$regex': '^' + today}}},
        {'$group': {'_id': '$user', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}, {'$limit': 10},
    ]).to_list(10)
    limit_row = await db.ai_limits.find_one({'id': 'deepseek:' + today}, {'_id': 0}) or {}
    config = await db.integrations.find_one({'id': 'deepseek'}, {'_id': 0, 'daily_requests': 1, 'model': 1, 'connected': 1}) or {}
    return {'running': running, 'recent': recent,
            'pending_approvals': pending_approvals, 'approvals': approvals,
            'today': {'count': sum(x['count'] for x in by_task), 'by_task': [{'task': x['_id']['task'], 'status': x['_id']['status'], 'count': x['count']} for x in by_task],
                      'limit_used': limit_row.get('count', 0), 'daily_limit': config.get('daily_requests', 100)},
            'connected': config.get('connected', False), 'model': config.get('model', ''),
            'per_user': [{'user': p['_id'] or 'guest/unknown', 'count': p['count']} for p in per_user]}
