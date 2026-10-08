import os
import hashlib
import secrets
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict

load_dotenv(Path(__file__).parent / '.env')
load_dotenv(Path(__file__).parent / '.env.local')
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
raw_db = client[os.environ['DB_NAME']]
workspace = ContextVar('workspace', default='')
PREFIX = os.environ['REBUILD_COLLECTION_PREFIX']
RUNTIME_MODE = os.environ.get('RUNTIME_MODE', 'sandbox')
if RUNTIME_MODE not in ('sandbox', 'production'):
    raise RuntimeError('RUNTIME_MODE must explicitly select sandbox or production')
EXTERNAL_ACTIONS = os.environ.get('EXTERNAL_ACTIONS_ENABLED', 'false').lower() == 'true' and RUNTIME_MODE == 'production'

def require_external_actions():
    from fastapi import HTTPException
    if not EXTERNAL_ACTIONS:
        raise HTTPException(503, 'External actions are locked pending provider verification. No request was sent.')
class ScopedDatabase:
    def __getitem__(self, name):
        if not isinstance(name, str) or not name.replace('_', '').isalnum():
            raise ValueError('Invalid collection')
        return raw_db[PREFIX + (workspace.get() + '_' if workspace.get() else '') + name]
    def __getattr__(self, name):
        return self[name]
    async def command(self, *args, **kwargs):
        return await raw_db.command(*args, **kwargs)
db = ScopedDatabase()
def now(): return datetime.now(timezone.utc)
def stamp(): return now().isoformat()
def uid(): return secrets.token_hex(12)
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
class Doc(BaseModel):
    model_config = ConfigDict(extra='allow')
async def audit(user, action, resource='', detail=''):
    await db.audit_logs.insert_one({'id':uid(), 'actor_id':user.get('id','system'), 'actor':user.get('name','System'), 'action':action, 'resource':str(resource), 'detail':str(detail)[:1000], 'created_at':stamp(), 'expires_at':datetime.fromtimestamp(now().timestamp()+365*86400, timezone.utc)})
async def settings():
    row = await db.settings.find_one({'id':'store'}, {'_id':0})
    return row['value']
async def flag(name): return (await settings())['features'].get(name, False)
async def record_login_history(user_id, request, success, method):
    from datetime import timedelta
    await db.login_history.insert_one({'id':uid(), 'user_id':user_id, 'ip':request.client.host if request.client else '', 'device':request.headers.get('user-agent','')[:200], 'success':success, 'method':method, 'created_at':stamp(), 'expires_at':now()+timedelta(days=90)})
