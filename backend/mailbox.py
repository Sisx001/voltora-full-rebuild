"""Persistent mailbox workspace. External delivery is explicitly unconfigured.
No fabricated inbound mail, no simulated sends. Provider adapters are a separate gate.
"""
import re
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, EmailStr, field_validator
from core import Input, db, stamp, uid, audit, workspace, RUNTIME_MODE
from permissions import require
router=APIRouter(prefix='/api/admin/mail',tags=['Mailbox'])
READ=require('mail.read'); WRITE=require('mail.update')

class Draft(Input):
    to: str = Field(default='',max_length=254)
    cc: str = Field(default='',max_length=254)
    subject: str = Field(default='',max_length=250)
    body: str = Field(default='',max_length=50000)
    reply_to_id: str = Field(default='',max_length=64)
    @field_validator('to','cc')
    @classmethod
    def email(cls,v):
        if v and not re.fullmatch(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+',v):
            raise ValueError('Enter one valid email address')
        return v
class MailPatch(Input):
    folder: Literal['drafts','archive','trash'] | None = None
    starred: bool | None = None
    read: bool | None = None
class MailConfig(Input):
    domain: str = Field(default='',max_length=253)
    display_name: str = Field(default='VOLTORA',min_length=1,max_length=80)
    provider: Literal['resend','smtp_imap']='resend'
    @field_validator('domain')
    @classmethod
    def domain_name(cls,v):
        v=v.lower().strip().rstrip('.')
        if v and (not re.fullmatch(r'(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',v)):
            raise ValueError('Enter a domain without https://, paths or spaces')
        return v
class Alias(Input):
    local_part: str = Field(min_length=1,max_length=64,pattern=r'^[a-z0-9][a-z0-9._-]*$')
    name: str = Field(default='',max_length=80)
    forward_to: str = Field(default='',max_length=254)
    @field_validator('forward_to')
    @classmethod
    def validate_forward(cls,v):return Draft.email(v)

@router.get('/status')
async def status(user=Depends(READ)):
    config=await db.mail_settings.find_one({'id':'mail'},{'_id':0}) or {'domain':'','display_name':'VOLTORA','provider':'resend'}
    aliases=await db.mail_aliases.find({},{'_id':0}).limit(50).to_list(50)
    counts={f:await db.mail_messages.count_documents({'folder':f}) for f in ['inbox','drafts','sent','archive','trash']}
    counts['starred']=await db.mail_messages.count_documents({'starred':True,'folder':{'$ne':'trash'}})
    return {'config':config,'aliases':aliases,'counts':counts,'delivery':'not_connected','receiving':'not_connected','demo':RUNTIME_MODE=='demo','requirements':['A domain you control','Your mail provider account and credentials','Provider-issued DNS records and verification','Verified inbound webhook or IMAP access'],'note':'Drafts and address plans are saved locally. No email is sent or received until a provider and domain are verified.'}

@router.put('/config')
async def configure(data:MailConfig,user=Depends(WRITE)):
    old=await db.mail_settings.find_one({'id':'mail'})
    if old and old.get('domain')!=data.domain and await db.mail_aliases.count_documents({}):
        raise HTTPException(409,'Remove draft addresses before changing the domain so they are not silently redirected')
    await db.mail_settings.update_one({'id':'mail'},{'$set':{**data.model_dump(),'updated_at':stamp()}},upsert=True)
    await audit(user,'mail.configuration_saved','mail','Local configuration only; no external provisioning')
    return {'saved':True,'connected':False}

@router.post('/aliases')
async def add_alias(data:Alias,user=Depends(WRITE)):
    conf=await db.mail_settings.find_one({'id':'mail'})
    if not conf or not conf.get('domain'):raise HTTPException(400,'Save your domain first')
    address=data.local_part+'@'+conf['domain']
    if await db.mail_aliases.count_documents({})>=50:raise HTTPException(400,'Limit of 50 draft addresses')
    if await db.mail_aliases.find_one({'address':address}):raise HTTPException(409,'This address is already listed')
    row={'id':uid(),**data.model_dump(),'address':address,'status':'draft','created_at':stamp()}
    await db.mail_aliases.insert_one(row.copy());await audit(user,'mail.address_planned',row['id'])
    return row

@router.delete('/aliases/{id}')
async def remove_alias(id:str,user=Depends(WRITE)):
    r=await db.mail_aliases.delete_one({'id':id})
    if not r.deleted_count:raise HTTPException(404,'Address not found')
    await audit(user,'mail.address_removed',id);return {'removed':True}

@router.get('/messages')
async def messages(folder:Literal['inbox','drafts','sent','archive','trash','starred']='inbox',q:str=Query(default='',max_length=100),page:int=Query(default=1,ge=1,le=1000),user=Depends(READ)):
    filt={'folder':folder} if folder!='starred' else {'starred':True,'folder':{'$ne':'trash'}}
    if q:filt['$or']=[{f:{'$regex':re.escape(q),'$options':'i'}} for f in ['subject','to','body']]
    return {'items':await db.mail_messages.find(filt,{'_id':0}).sort('updated_at',-1).skip((page-1)*30).limit(30).to_list(30),'total':await db.mail_messages.count_documents(filt),'page':page,'page_size':30}

@router.post('/drafts')
async def new_draft(data:Draft,user=Depends(WRITE)):
    if await db.mail_messages.count_documents({})>=1000:raise HTTPException(400,'Demo mailbox limit reached')
    if data.reply_to_id and not await db.mail_messages.find_one({'id':data.reply_to_id}):raise HTTPException(404,'Original message not found')
    row={'id':uid(),**data.model_dump(),'folder':'drafts','read':True,'starred':False,'author_id':user['id'],'created_at':stamp(),'updated_at':stamp()}
    await db.mail_messages.insert_one(row.copy());await audit(user,'mail.draft_created',row['id'])
    return row

@router.put('/drafts/{id}')
async def save_draft(id:str,data:Draft,user=Depends(WRITE)):
    r=await db.mail_messages.update_one({'id':id,'folder':'drafts'},{'$set':{**data.model_dump(),'updated_at':stamp()}})
    if not r.matched_count:raise HTTPException(404,'Editable draft not found')
    return await db.mail_messages.find_one({'id':id},{'_id':0})

@router.patch('/messages/{id}')
async def patch_message(id:str,data:MailPatch,user=Depends(WRITE)):
    r=await db.mail_messages.update_one({'id':id},{'$set':{**data.model_dump(exclude_none=True),'updated_at':stamp()}})
    if not r.matched_count:raise HTTPException(404,'Message not found')
    return await db.mail_messages.find_one({'id':id},{'_id':0})

@router.post('/messages/{id}/send')
async def send(id:str,user=Depends(WRITE)):
    if not await db.mail_messages.find_one({'id':id,'folder':'drafts'}):raise HTTPException(404,'Draft not found')
    raise HTTPException(409,'Email has not been sent. Connect and verify your sending provider and domain first. External delivery is disabled in this demonstration.')
