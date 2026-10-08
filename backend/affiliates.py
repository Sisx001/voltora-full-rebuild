'''Affiliate system: owner-managed affiliate profiles with referral codes,
click tracking, and a commission ledger settled when orders are paid.

Commissions accrue when an order attributed to an affiliate's code becomes
PAID (never on mere placement). Payouts are recorded staff actions.'''
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, EmailStr
from pymongo.errors import DuplicateKeyError
from core import db, Input, Doc, uid, stamp, now, audit, settings
from permissions import require

router = APIRouter(prefix='/api/admin/affiliates', tags=['Affiliates'])
public_router = APIRouter(prefix='/api/affiliate', tags=['Affiliates'])


async def record_conversion(affiliate_code: str, order: dict):
    '''Credit a commission when an attributed order is placed; idempotent per order.'''
    affiliate = await db.affiliates.find_one({'code': affiliate_code.upper(), 'status': 'active'}, {'_id': 0})
    if not affiliate:
        return
    if await db.affiliate_ledger.find_one({'order_id': order['id']}):
        return
    pct = affiliate.get('commission_pct')
    if pct is None:
        config = await settings()
        pct = config.get('affiliate_commission_pct', 5)
    commission = int(order['total'] * pct / 100)
    await db.affiliate_ledger.insert_one({'id': uid(), 'affiliate_id': affiliate['id'], 'order_id': order['id'],
                                          'order_number': order['number'], 'order_total': order['total'],
                                          'commission': commission, 'status': 'pending', 'paid_at': '', 'note': '',
                                          'created_at': stamp()})
    await db.affiliates.update_one({'id': affiliate['id']}, {'$inc': {'conversions': 1, 'revenue': order['total'], 'commission_earned': commission}})


@public_router.post('/{code}/click', response_model=Doc)
async def record_click(code: str):
    result = await db.affiliates.update_one({'code': code.upper(), 'status': 'active'}, {'$inc': {'clicks': 1}})
    return {'ok': True, 'recorded': bool(result.modified_count)}


# ---------------- admin ----------------

@router.get('', response_model=list[Doc])
async def list_affiliates(user=Depends(require('marketing.read'))):
    return await db.affiliates.find({}, {'_id': 0}).sort('created_at', -1).to_list(200)


class AffiliateSave(Input):
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    commission_pct: float = Field(default=5, ge=0, le=50)
    status: Literal['pending', 'active', 'suspended'] = 'active'
    notes: str = Field(default='', max_length=500)


@router.post('', response_model=Doc)
async def create_affiliate(data: AffiliateSave, user=Depends(require('marketing.update'))):
    code = (data.name.lower().replace(' ', '').replace('&', 'and')[:8] + uid()[:4])
    code = ''.join(c for c in code if c.isalnum())[:12]
    row = {'id': uid(), 'code': code.upper(), **data.model_dump(), 'clicks': 0, 'conversions': 0,
           'revenue': 0, 'commission_earned': 0, 'commission_paid': 0, 'created_at': stamp()}
    try:
        await db.affiliates.insert_one(row.copy())
    except DuplicateKeyError:
        raise HTTPException(409, 'Affiliate code collision; retry')
    await audit(user, 'affiliate.created', row['id'], f"{data.name} ({code.upper()})")
    return row


@router.put('/{id}', response_model=Doc)
async def update_affiliate(id: str, data: AffiliateSave, user=Depends(require('marketing.update'))):
    result = await db.affiliates.update_one({'id': id}, {'$set': {**data.model_dump(), 'updated_at': stamp()}})
    if not result.modified_count and not await db.affiliates.find_one({'id': id}):
        raise HTTPException(404, 'Affiliate not found')
    await audit(user, 'affiliate.updated', id, data.status)
    return {'ok': True}


@router.get('/{id}/ledger', response_model=list[Doc])
async def ledger(id: str, user=Depends(require('marketing.read'))):
    return await db.affiliate_ledger.find({'affiliate_id': id}, {'_id': 0}).sort('created_at', -1).to_list(200)


class Payout(Input):
    note: str = Field(default='', max_length=300)


@router.post('/{id}/payout', response_model=Doc)
async def payout(id: str, data: Payout, user=Depends(require('marketing.update'))):
    affiliate = await db.affiliates.find_one({'id': id}, {'_id': 0})
    if not affiliate:
        raise HTTPException(404, 'Affiliate not found')
    rows = await db.affiliate_ledger.find({'affiliate_id': id, 'status': 'pending'}, {'_id': 0}).to_list(500)
    if not rows:
        raise HTTPException(409, 'No pending commissions to pay out')
    total = sum(r['commission'] for r in rows)
    await db.affiliate_ledger.update_many({'affiliate_id': id, 'status': 'pending'}, {'$set': {'status': 'paid', 'paid_at': stamp(), 'note': data.note[:300]}})
    await db.affiliates.update_one({'id': id}, {'$inc': {'commission_paid': total}})
    await audit(user, 'affiliate.payout', id, f"{total} poisha across {len(rows)} orders: {data.note}"[:300])
    return {'ok': True, 'orders': len(rows), 'total': total}
