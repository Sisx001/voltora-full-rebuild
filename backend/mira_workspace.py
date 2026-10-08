"""Visual Mira configuration. Saving settings never invokes a model or enables tools."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from core import Input, Doc, db, stamp
from permissions import require
router=APIRouter(prefix='/api/admin/mira',tags=['Mira workspace'])

class MiraSettings(Input):
    title:str=Field(default='Mira',min_length=1,max_length=40)
    greeting:str=Field(default='Hi there. Let’s find your next good thing.',min_length=1,max_length=300)
    accent:str=Field(default='#b9df8e',pattern=r'^#[0-9a-fA-F]{6}$')
    position:Literal['bottom_right','bottom_left']='bottom_right'
    personality:Literal['warm','concise','professional']='warm'
    language:Literal['en','bn','es','fr','hi']='en'
    pages:list[Literal['home','shop','product','cart','checkout','account','support','assistant','page']]=Field(default=['home','shop','product'],max_length=9)
    knowledge:str=Field(default='',max_length=6000)
    provider:Literal['deepseek','openai-compatible','anthropic','google']='deepseek'
    model:str=Field(default='',max_length=100)
    product_search:bool=True
    policy_lookup:bool=True
    order_status:bool=False
    require_approval:Literal[True]=True

class MiraSave(Input):
    version:int=Field(ge=0)
    settings:MiraSettings

async def mira_configuration():
    row=await db.mira_workspace.find_one({'id':'main'},{'_id':0})
    return row or {'id':'main','version':0,'settings':MiraSettings().model_dump()}

@router.get('',response_model=Doc)
async def read(user=Depends(require('ai.read'))):
    return {**await mira_configuration(),'provider_status':'unverified','generation_enabled':False}

@router.put('',response_model=Doc)
async def save(data:MiraSave,user=Depends(require('ai.update'))):
    await db.mira_workspace.update_one({'id':'main'},{'$setOnInsert':{'id':'main','version':0}},upsert=True)
    value=data.settings.model_dump()
    result=await db.mira_workspace.update_one({'id':'main','version':data.version},
        {'$set':{'settings':value,'updated_at':stamp()},'$inc':{'version':1}})
    if not result.modified_count:raise HTTPException(409,'Mira settings changed in another session. Reload before saving.')
    return {'version':data.version+1,'settings':value}

async def allow_tool(name):
    row=await mira_configuration()
    mapping={'search_products':'product_search','get_product':'product_search','shipping_info':'policy_lookup','policy_info':'policy_lookup','order_status':'order_status'}
    return row['settings'].get(mapping.get(name,''),False)