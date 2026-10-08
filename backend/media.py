"""Validated, bounded image storage in the workspace database.
No dependency on external storage or an AI key. Binary data never enters metadata JSON.
"""
import io,os,re,asyncio
from PIL import Image, UnidentifiedImageError, ImageOps
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Response
from pydantic import Field
from bson import Binary
from core import db,raw_db,PREFIX,workspace,Doc,Input,uid,stamp,audit
from permissions import require
router=APIRouter(prefix='/api',tags=['Media'])
Image.MAX_IMAGE_PIXELS=25000000

async def storage_init():
    raise HTTPException(503,'External attachment storage is not configured. Image-library uploads use the local workspace store; other attachment types require a verified storage provider.')

def process_image(data):
    try:
        image=Image.open(io.BytesIO(data))
        if image.format not in ['JPEG','PNG','WEBP']:raise ValueError()
        image.load();image=ImageOps.exif_transpose(image);image.thumbnail((2400,2400))
        output=io.BytesIO();image.convert('RGB').save(output,format='WEBP',quality=86)
        if len(output.getvalue())>5*1024*1024:raise ValueError()
        return output.getvalue(),image.width,image.height
    except (UnidentifiedImageError,ValueError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Upload a valid JPEG, PNG or WebP image, up to 25 megapixels')

async def store_image(data:bytes,filename:str,alt:str,folder:str,user):
    raw,width,height=await asyncio.to_thread(process_image,data)
    count=await db.media.count_documents({})
    if count>=100:raise HTTPException(413,'Workspace limit of 100 images reached')
    total=await db.media.aggregate([{'$group':{'_id':None,'bytes':{'$sum':'$size'}}}]).to_list(1)
    if (total[0]['bytes'] if total else 0)+len(raw)>50*1024*1024:raise HTTPException(413,'This workspace has reached its 50 MB image allowance')
    id=uid();public_id=(workspace.get()+'~' if workspace.get() else '')+id
    row={'id':id,'name':filename[:200],'alt':alt[:500],'caption':'','folder':folder[:80],'width':width,'height':height,'size':len(raw),'archived':False,'public':True,'created_at':stamp(),'url':os.environ['APP_ORIGIN']+'/api/media/'+public_id}
    await db.media_blobs.insert_one({'id':id,'data':Binary(raw),'created_at':stamp()})
    await db.media.insert_one(row.copy());await audit(user,'media.uploaded',id)
    return row

@router.get('/admin/media',response_model=list[Doc])
async def media(archived:bool=False,user=Depends(require('media.read'))):
    return await db.media.find({'archived':archived},{'_id':0,'storage_path':0}).sort('created_at',-1).limit(100).to_list(100)
@router.post('/admin/media',response_model=Doc)
async def upload(file:UploadFile=File(...),folder:str=Form('Products'),alt:str=Form(''),user=Depends(require('media.update'))):
    data=await file.read(10*1024*1024+1)
    if len(data)>10*1024*1024:raise HTTPException(413,'Images must be 10 MB or smaller')
    return await store_image(data,file.filename or 'image',alt,folder,user)
@router.get('/media/{id}')
async def image(id:str):
    if not re.fullmatch(r'(?:d[0-9a-f]{24}~)?[0-9a-f]{24}',id):raise HTTPException(404,'Image not found')
    ns,media_id=id.split('~') if '~' in id else ('',id)
    name=PREFIX+(ns+'_' if ns else '')
    row=await raw_db[name+'media'].find_one({'id':media_id,'archived':False,'public':True})
    if not row:raise HTTPException(404,'Image not found')
    blob=await raw_db[name+'media_blobs'].find_one({'id':media_id})
    if not blob:raise HTTPException(404,'Image data not found')
    return Response(bytes(blob['data']),media_type='image/webp',headers={'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff','Content-Disposition':'inline'})
class MediaUpdate(Input):
    name:str=Field(min_length=1,max_length=200)
    alt:str=Field(default='',max_length=500)
    caption:str=Field(default='',max_length=1000)
    folder:str=Field(default='Products',max_length=80)
    archived:bool=False
@router.put('/admin/media/{id}',response_model=Doc)
async def update_media(id:str,data:MediaUpdate,user=Depends(require('media.update'))):
    r=await db.media.update_one({'id':id},{'$set':data.model_dump()})
    if not r.matched_count:raise HTTPException(404,'Image not found')
    await audit(user,'media.updated',id);return {'ok':True}
