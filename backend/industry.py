"""Applying a theme only edits the presentation draft; catalogs are never overwritten."""
import json
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from core import db, Input, Doc
from schemas import Theme, Page, Section
from permissions import require, authorize
from release_engine import state, save_builder, Bundle, SaveBundle

router=APIRouter(prefix='/api/admin/themes',tags=['Industry packs'])

class IndustryApply(Input):
    theme_id:str=Field(min_length=1,max_length=90)
    apply_content:Literal['none','content_only','content_and_products']='none'

@router.post('/apply-industry',response_model=Doc)
async def apply_industry(data:IndustryApply,user=Depends(require('theme.update'))):
    await authorize(user,'content.update')
    theme=await db.themes.find_one({'id':data.theme_id},{'_id':0})
    if not theme:raise HTTPException(404,'Theme not found')
    if data.apply_content=='content_and_products':
        raise HTTPException(409,'Catalog replacement is disabled. Apply the design or homepage without altering inventory.')
    current=await state()
    bundle=current['draft']
    bundle['theme']=Theme(**theme).model_dump()
    bundle['site']['header']['layout']=theme['header_style']
    bundle['site']['footer']['style']=theme['footer_style']
    if data.apply_content=='content_only':
        path=Path(__file__).parent/'data'/'packs'/(theme['industry']+'.json')
        if not path.exists():raise HTTPException(404,'Industry content pack not found')
        pack=json.loads(path.read_text())
        bundle['pages']['home']=Page(title='Home',slug='home',sections=[Section(**{k:v for k,v in s.items() if k in Section.model_fields}) for s in pack['sections']]).model_dump()
    result=await save_builder(SaveBundle(version=current['version'],bundle=Bundle(**bundle)),user)
    return {**result,'theme':theme['name'],'industry':theme['industry'],'content':'Draft only; catalog unchanged','products_added':0}