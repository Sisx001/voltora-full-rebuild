"""Market defaults with a deliberately guarded settlement-currency change."""
import pycountry
from zoneinfo import available_timezones
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from core import Input,db,settings,audit
from permissions import require
router=APIRouter(prefix='/api/admin/market',tags=['Market configuration'])
# Existing commerce stores hundredths. Unsupported exponents are never silently mispriced.
NON_TWO={'BIF','CLP','DJF','GNF','ISK','JPY','KMF','KRW','PYG','RWF','UGX','UYI','VND','VUV','XAF','XOF','XPF','BHD','IQD','JOD','KWD','LYD','OMR','TND','CLF','UYW','XAU','XAG','XPD','XPT','XXX','XTS'}
CURRENCIES=[{'code':c.alpha_3,'name':c.name} for c in pycountry.currencies if c.alpha_3 not in NON_TWO]
ALLOWED={c['code'] for c in CURRENCIES}
class Market(Input):
    country:str=Field(pattern=r'^[A-Z]{2}$')
    timezone:str=Field(max_length=80)
    base_currency:str=Field(pattern=r'^[A-Z]{3}$')
@router.get('')
async def read(user=Depends(require('settings.read'))):
    s=await settings()
    return {'value':{'country':s.get('country','BD'),'timezone':s.get('timezone','Asia/Dhaka'),'base_currency':s.get('base_currency','BDT')},'countries':sorted([{'code':c.alpha_2,'name':c.name} for c in pycountry.countries],key=lambda c:c['name']),'currencies':sorted(CURRENCIES,key=lambda c:c['code']),'timezones':sorted(available_timezones()),'currency_locked':bool(await db.orders.count_documents({}))}
@router.put('')
async def save(data:Market,user=Depends(require('settings.update'))):
    if not pycountry.countries.get(alpha_2=data.country):raise HTTPException(422,'Unknown country')
    if data.timezone not in available_timezones():raise HTTPException(422,'Unknown timezone')
    if data.base_currency not in ALLOWED:raise HTTPException(422,'This currency needs a minor-unit migration before it can be used')
    s=await settings(); old=s.get('base_currency','BDT')
    if data.base_currency!=old and await db.orders.count_documents({}):raise HTTPException(409,'The selling currency cannot change after orders exist. Use a reviewed migration.')
    patch={'value.country':data.country,'value.timezone':data.timezone,'value.base_currency':data.base_currency}
    if data.base_currency!=old:
        symbol={'BDT':'৳','USD':'$','EUR':'€','GBP':'£','INR':'₹'}.get(data.base_currency,data.base_currency+' ')
        patch['value.currencies']=[{'code':data.base_currency,'symbol':symbol,'rate':1,'decimals':2,'enabled':True}]+[{**c,'enabled':False} for c in s['currencies'] if c['code']!=data.base_currency]
    if data.country!='BD':patch['value.features.location_picker']=False
    await db.settings.update_one({'id':'store'},{'$set':patch,'$inc':{'version':1}})
    await audit(user,'market.updated',data.country,'Currency '+data.base_currency+'; rates not auto-converted')
    return {'saved':True,'base_currency':data.base_currency}
