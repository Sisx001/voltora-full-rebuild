"""Version-bound, authorization-rechecked scheduled publishing.
Platform cron is the scheduler. Work is claimed atomically and execution is bounded.
"""
import os,secrets
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Depends,HTTPException,Request,BackgroundTasks
from pydantic import Field
from pymongo import ReturnDocument
from core import Input,raw_db,db,PREFIX,workspace,stamp,uid,audit,now
from permissions import require
from auth import role_permissions
router=APIRouter(prefix='/api',tags=['Publishing schedules'])
class Schedule(Input):
    version:int=Field(ge=1)
    at:datetime
@router.post('/admin/documents/{id}/schedule')
async def schedule(id:str,data:Schedule,user=Depends(require('content.publish'))):
    raise HTTPException(409,'Per-page scheduling is retired. Use Website builder to review and explicitly publish an atomic release.')
    if data.at.tzinfo is None:raise HTTPException(422,'A timezone is required')
    if not now()+timedelta(seconds=30)<data.at<now()+timedelta(days=366):raise HTTPException(422,'Choose a future time within the next year')
    doc=await db.documents.find_one({'id':id})
    if not doc:raise HTTPException(404,'Page not found')
    if doc['kind'] in ['theme','site']:raise HTTPException(422,'Schedule a content page; publish themes and site layouts explicitly')
    if doc['version']!=data.version:raise HTTPException(409,'Save the latest draft before scheduling')
    at=data.at.astimezone(timezone.utc).isoformat();job_id=uid()
    await raw_db[PREFIX+'publish_jobs'].update_many({'workspace':workspace.get(),'document_id':id,'status':'scheduled'},{'$set':{'status':'superseded'}})
    row={'id':job_id,'workspace':workspace.get(),'document_id':id,'version':data.version,'actor_id':user['id'],'at':at,'status':'scheduled','created_at':stamp()}
    await raw_db[PREFIX+'publish_jobs'].insert_one(row)
    await db.documents.update_one({'id':id},{'$set':{'publish_schedule':{'id':job_id,'at':at,'status':'scheduled','version':data.version}}})
    await audit(user,'content.scheduled',id,at)
    return {'scheduled':True,'at':at,'cadence':'Runs on the next 15-minute publishing tick after the chosen time'}
@router.delete('/admin/documents/{id}/schedule')
async def cancel(id:str,user=Depends(require('content.publish'))):
    result=await db.documents.update_one({'id':id},{'$unset':{'publish_schedule':''}})
    if not result.matched_count:raise HTTPException(404,'Page not found')
    await raw_db[PREFIX+'publish_jobs'].update_many({'workspace':workspace.get(),'document_id':id,'status':'scheduled'},{'$set':{'status':'cancelled'}})
    await audit(user,'content.schedule_cancelled',id);return {'cancelled':True}
async def run_due(run_id):
    jobs=raw_db[PREFIX+'publish_jobs'];result={'published':0,'blocked':0}
    try:
        # Reclaim work interrupted before completion; publication CAS prevents a second write.
        await jobs.update_many({'status':'processing','claimed_at':{'$lt':(now()-timedelta(minutes=20)).isoformat()}},{'$set':{'status':'scheduled'}})
        for _ in range(20):
            job=await jobs.find_one_and_update({'status':'scheduled','at':{'$lte':stamp()}},{'$set':{'status':'processing','claimed_at':stamp()}},return_document=ReturnDocument.AFTER)
            if not job:break
            token=workspace.set(job['workspace'])
            try:
                user=await db.users.find_one({'id':job['actor_id']})
                perms=await role_permissions(user.get('role')) if user else []
                ban=(user or {}).get('ban',{})
                if not user or user.get('disabled') or user.get('role')=='investor' or 'content.publish' not in perms or (ban.get('active') and (not ban.get('until') or ban['until']>stamp())):
                    raise ValueError('Publisher no longer has permission')
                doc=await db.documents.find_one({'id':job['document_id']})
                if not doc or doc['version']!=job['version']:raise ValueError('Draft changed after scheduling; review and reschedule')
                from schemas import Page
                value=Page(**doc['draft']).model_dump()
                published=await db.documents.update_one({'id':doc['id'],'version':job['version'],'publish_schedule.id':job['id']},{'$set':{'published':value,'published_at':stamp(),'publish_schedule.status':'published'},'$inc':{'version':1}})
                if not published.modified_count:raise ValueError('Schedule was cancelled or page changed')
                await db.revisions.insert_one({'id':uid(),'document_id':doc['id'],'value':value,'previous':doc.get('published'),'created_at':stamp(),'author':user['name'],'summary':'Scheduled publication','version':job['version']+1})
                await audit(user,'content.scheduled_published',doc['id'])
                await jobs.update_one({'id':job['id']},{'$set':{'status':'published','completed_at':stamp()}});result['published']+=1
            except Exception as exc:
                await jobs.update_one({'id':job['id']},{'$set':{'status':'blocked','reason':str(exc)[:200]}})
                await db.documents.update_one({'id':job['document_id'],'publish_schedule.id':job['id']},{'$set':{'publish_schedule.status':'blocked','publish_schedule.reason':str(exc)[:200]}});result['blocked']+=1
            finally:workspace.reset(token)
        await raw_db[PREFIX+'cron_runs'].update_one({'_id':run_id},{'$set':{'status':'complete','result':result,'completed_at':stamp()}})
    except Exception:
        await raw_db[PREFIX+'cron_runs'].update_one({'_id':run_id},{'$set':{'status':'failed','completed_at':stamp()}})
@router.post('/cron/publish')
async def publish_tick(request:Request,background:BackgroundTasks):
    # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
    secret=os.environ.get('WEBHOOK_CRON_SECRET','')
    auth=request.headers.get('authorization','')
    if not secret or not auth.startswith('Bearer ') or not secrets.compare_digest(auth[7:],secret):raise HTTPException(401,'Invalid scheduler authentication')
    try:body=await request.json()
    except Exception:raise HTTPException(400,'Invalid JSON envelope')
    if not isinstance(body,dict) or body.get('event')!='schedule.triggered':raise HTTPException(400,'Invalid scheduler envelope')
    run_id=request.headers.get('x-webhook-id') or body.get('run_id')
    if not isinstance(run_id,str) or not 1<=len(run_id)<=200:raise HTTPException(400,'Run ID is required')
    receipt=await raw_db[PREFIX+'cron_runs'].update_one({'_id':run_id},{'$setOnInsert':{'status':'accepted','created_at':stamp()}},upsert=True)
    if receipt.upserted_id:background.add_task(run_due,run_id)
    return {'accepted':True,'duplicate':not bool(receipt.upserted_id)}
