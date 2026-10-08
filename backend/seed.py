from core import db, stamp, uid
from themes import theme_presets
from schemas import Settings, Features, Section, Page, Product, SiteConfig, MiraConfig
from permissions import BUILT_IN_ROLES
from locations import seed_locations

HERO='https://static.prod-images.emergentagent.com/jobs/ee3ab9c1-ccfe-475f-9503-dd779366e596/images/a9b1a3191a7860145be233a5eecd9ad9276ba777ee047d49796860c619db8bdc.jpeg'
EARBUDS='https://static.prod-images.emergentagent.com/jobs/ee3ab9c1-ccfe-475f-9503-dd779366e596/images/6c7bbda47ecd387a610e99d9e51a7f4b30bdc83e55e8bb3cdbf2198ae63bd66e.jpeg'
DESK='https://static.prod-images.emergentagent.com/jobs/ee3ab9c1-ccfe-475f-9503-dd779366e596/images/388cb4261a27822517da3bd664a8bbd1b975243b774a43dff8d300351fba6ce4.jpeg'
def photo(id): return f'https://images.unsplash.com/{id}?auto=format&fit=crop&w=800&q=85'
CATEGORIES=[('audio','Audio & sound','Headphones',photo('photo-1546435770-a3e426bf472b')),('laptops','Laptops & computing','Laptop',photo('photo-1496181133206-80ce9b88a853')),('phones','Smartphones','Smartphone',photo('photo-1511707171634-5f897ff02aa9')),('wearables','Smart wearables','Watch',photo('photo-1523275335684-37898b6baf30')),('gaming','Gaming','Gamepad2',photo('photo-1612287230202-1ff1d85d1bdf')),('accessories','Accessories','Cable',photo('photo-1587829741301-dc798b83add3')),('cameras','Cameras & creators','Camera',photo('photo-1516035069371-29a1b244cc32')),('smart-home','Smart home','House',photo('photo-1543512214-318c7553f230'))]


async def seed_demo_workspace():
    """Copy only public demo content, not real users/orders/provider credentials.

    Index creation is bounded: no repeated full application/location initialization.
    """
    from core import raw_db, PREFIX
    for name in ['settings','documents','themes','categories','brands','collections','products','product_drafts','inventory','coupons']:
        rows=await raw_db[PREFIX+name].find({}, {'_id':0}).to_list(200)
        if rows:
            from pymongo import ReplaceOne
            await db[name].bulk_write([ReplaceOne({'id':row['id']}, row, upsert=True) for row in rows])
    for name,field in [('users','email'),('sessions','token_hash'),('orders','idempotency_key'),('products','id'),('products','slug')]:
        await db[name].create_index(field,unique=True)
    # The small country tree can be copied in a single insert; no per-record API calls.
    rows=await raw_db[PREFIX+'locations'].find({}, {'_id':0}).to_list(10000)
    if rows:
        from pymongo import ReplaceOne
        await db.locations.bulk_write([ReplaceOne({'id':row['id']},row,upsert=True) for row in rows])

async def seed():
    await seed_locations()
    from core import raw_db, PREFIX
    if await raw_db[PREFIX+'migrations'].find_one({'id':'initial_indexes_v1'}):
        return
    for coll,field in [('users','id'),('users','email'),('products','id'),('products','slug'),('products','sku'),('documents','id'),('themes','id'),('categories','id'),('orders','id'),('sessions','token_hash'),('media','id'),('conversations','id')]:
        await db[coll].create_index(field,unique=True)
    await db.orders.create_index('idempotency_key',unique=True)
    await db.login_attempts.create_index([('key',1),('created_at',1)])
    for coll in ['sessions','login_attempts','previews','audit_logs','events']:
        await db[coll].create_index('expires_at',expireAfterSeconds=0)
    await db.orders.create_index([('user_id',1),('created_at',-1)])
    await db.products.create_index([('published',1),('category',1)])
    await db.conversations.create_index('user_id')
    await db.messages.create_index([('conversation_id',1),('created_at',1)])
    await db.reviews.create_index([('user_id',1),('product_id',1)],unique=True)
    await db.products.create_index('variants.id',unique=True)
    await db.products.create_index('variants.sku',unique=True)
    await db.coupons.create_index('code',unique=True)
    await db.ai_limits.create_index('id',unique=True)
    await db.rate_limits.create_index('expires_at',expireAfterSeconds=0)
    await db.roles.create_index('id',unique=True)
    await db.users.create_index('phone',unique=True,sparse=True)
    await db.offer_pages.create_index('code',unique=True)
    await db.offer_events.create_index('offer_id')
    await db.offer_events.create_index('expires_at',expireAfterSeconds=0)
    await db.affiliates.create_index('code',unique=True)
    await db.affiliate_ledger.create_index('order_id',unique=True)
    await db.affiliate_ledger.create_index('affiliate_id')
    await db.alert_log.create_index('expires_at',expireAfterSeconds=0)
    await db.ai_memories.create_index('id',unique=True)
    await db.ai_tasks.create_index([('created_at',-1)])
    await db.ai_tasks.create_index('status')
    await db.ai_tasks.create_index('user_id')
    await db.provider_configs.create_index('id',unique=True)
    await db.provider_configs.create_index([('kind',1),('enabled',1),('status',1)])
    await db.webhook_events.create_index([('provider',1),('event_id',1)],unique=True)
    await db.payment_transactions.create_index('id',unique=True)
    await db.payment_transactions.create_index('order_id')
    await db.payment_transactions.create_index([('created_at',-1)])
    await db.shipments.create_index('id',unique=True)
    await db.shipments.create_index('order_id')
    await db.locations.create_index('id',unique=True)
    await db.locations.create_index('parent_id')
    await db.locations.create_index([('kind',1),('active',1)])
    await db.locations.create_index('name')
    await db.locations.create_index('postcode')
    await db.otps.create_index('expires_at',expireAfterSeconds=0)
    await db.email_queue.create_index('expires_at',expireAfterSeconds=0)
    await db.notifications.create_index('expires_at',expireAfterSeconds=0)
    await db.notifications.create_index([('user_id',1),('created_at',-1)])
    await db.login_history.create_index('expires_at',expireAfterSeconds=0)
    await db.login_history.create_index([('user_id',1),('created_at',-1)])
    await db.attachments.create_index('id',unique=True)
    await db.attachments.create_index('conversation_id')
    await db.return_requests.create_index('id',unique=True)
    await db.return_requests.create_index('order_id')
    await db.loyalty_ledger.create_index('user_id')
    await db.visitor_sessions.create_index('expires_at',expireAfterSeconds=0)
    await db.visitor_sessions.create_index([('created_at',-1)])
    for rid in ['super_admin','admin','moderator','product_manager','seller','order_manager','finance_manager','content_editor','support_agent','marketing_manager','inventory_manager','seo_manager','analyst']:
        await db.roles.update_one({'id':rid},{'$setOnInsert':{'id':rid,'name':rid.replace('_',' ').title(),'description':'Built-in role','permissions':BUILT_IN_ROLES[rid],'built_in':True,'created_at':stamp()}},upsert=True)
    presets=theme_presets()
    for theme in presets:
        await db.themes.update_one({'id':theme['id']},{'$setOnInsert':theme},upsert=True)
        # canonical refresh: built-in presets always carry the latest industry tag + variant fields
        await db.themes.update_one({'id':theme['id'],'built_in':{'$ne':False}},{'$set':theme})
    initial={
      'brand':'VOLTORA','tagline':'Technology for your everyday.','announcement':'Better tech. Better everyday. Free delivery on orders ৳5,000+','announcement_bn':'সেরা প্রযুক্তি, সুন্দর প্রতিদিন। ৳৫,০০০-এর বেশি অর্ডারে ফ্রি ডেলিভারি',
      'email':'','phone':'','address':'Bangladesh','footer_text':'Thoughtfully selected tech. Endless possibilities.',
      'features':Features().model_dump(),
      'currencies':[{'code':'BDT','symbol':'৳','rate':1,'decimals':0,'enabled':True},{'code':'USD','symbol':'$','rate':0.0082,'decimals':2,'enabled':True},{'code':'EUR','symbol':'€','rate':0.0076,'decimals':2,'enabled':True}],
      'shipping':[{'id':'dhaka','name':'Inside Dhaka','fee':8000,'free_above':500000,'estimate':'2–3 business days','enabled':True},{'id':'outside','name':'Outside Dhaka','fee':15000,'free_above':500000,'estimate':'3–5 business days','enabled':True},{'id':'pickup','name':'Store pickup','fee':0,'free_above':0,'estimate':'After confirmation','enabled':True}],
      'payments':[{'id':'cod','label':'Cash on delivery','enabled':True},{'id':'bank_transfer','label':'Bank transfer','enabled':False,'instructions':''},{'id':'bkash','label':'bKash','enabled':False},{'id':'nagad','label':'Nagad','enabled':False},{'id':'rocket','label':'Rocket','enabled':False},{'id':'upay','label':'Upay','enabled':False},{'id':'sslcommerz','label':'SSLCommerz','enabled':False},{'id':'stripe','label':'Stripe','enabled':False},{'id':'paypal','label':'PayPal','enabled':False}],
      'navigation':[{'label':'All products','url':'/shop'},{'label':'Audio & sound','url':'/shop?category=audio'},{'label':'Laptops','url':'/shop?category=laptops'},{'label':'Smartphones','url':'/shop?category=phones'},{'label':'Gaming','url':'/shop?category=gaming'},{'label':'Accessories','url':'/shop?category=accessories'}],
      'footer_links':[{'label':x.title(),'url':f'/pages/{x}'} for x in ['about','contact','faq','shipping','returns','warranty','privacy','terms']],
      'translations':{'en':{'shop':'Shop all','search':'Search for your next upgrade...','cart':'My bag','wishlist':'Wishlist','compare':'Compare','account':'Account','add':'Add to bag','checkout':'Checkout','explore':'Explore the collection'},'bn':{'shop':'সব পণ্য','search':'আপনার পছন্দের পণ্য খুঁজুন...','cart':'আমার ব্যাগ','wishlist':'পছন্দের তালিকা','compare':'তুলনা','account':'অ্যাকাউন্ট','add':'ব্যাগে যোগ করুন','checkout':'চেকআউট','explore':'সংগ্রহ দেখুন'}}
    }
    await db.settings.update_one({'id':'store'},{'$setOnInsert':{'id':'store','version':1,'value':Settings(**initial).model_dump()}},upsert=True)
    await db.settings.update_one({'id':'store','value.mira_config':{'$exists':False}},{'$set':{'value.mira_config':MiraConfig().model_dump()}})
    stored=await db.settings.find_one({'id':'store'},{'_id':0})
    known=[p['id'] for p in stored['value'].get('payments',[])]
    additions=[p for p in initial['payments'] if p['id'] not in known]
    if additions:
        merged=stored['value']['payments']+additions
        await db.settings.update_one({'id':'store'},{'$set':{'value.payments':merged[:10]},'$inc':{'version':1}})
    await db.documents.update_one({'id':'theme'},{'$setOnInsert':{'id':'theme','kind':'theme','draft':presets[0],'published':presets[0],'version':1,'updated_at':stamp()}},upsert=True)
    # website-builder site document (header/footer/auth/checkout blocks) mirrors the live layout at first boot
    site_value=SiteConfig(header={
        'layout':'classic','sticky':True,
        'top':[{'id':'announcement','type':'announcement'},{'id':'utility_message','type':'utility_message','label':'Thoughtfully selected. Exceptionally yours.'},{'id':'track_order','type':'track_order','label':'Track your order'},{'id':'support_link','type':'support_link','label':'Need a hand?'},{'id':'language','type':'language'},{'id':'currency','type':'currency'}],
        'main':[{'id':'menu','type':'menu'},{'id':'logo','type':'logo'},{'id':'search','type':'search'}],
        'actions':[{'id':'notifications','type':'notifications'},{'id':'dark_mode','type':'dark_mode'},{'id':'account','type':'account'},{'id':'wishlist','type':'wishlist'},{'id':'compare','type':'compare'},{'id':'cart','type':'cart'}],
        'show_nav':True,'show_browse':True,'nav_deal_label':'New arrivals'},
        footer={'style':'dark','columns':[
            {'id':'brand','type':'brand','enabled':True},
            {'id':'explore','type':'links','title':'Explore','enabled':True,'links':[{'label':'All products','url':'/shop'},{'label':'New arrivals','url':'/shop?sort=newest'}]},
            {'id':'help','type':'links','title':'We’re here to help','enabled':True},
            {'id':'newsletter','type':'newsletter','title':'Stay a little ahead.','text':'New finds, thoughtful edits, and store updates.','enabled':True}],
            'show_social':True,'show_payments':True},
        auth={'layout':'split','side_heading':'Made for the way you live.','side_bullets':['Fast, secure checkout','Order tracking and easy returns','Members-only offers and early access']},
        checkout={'layout':'two_column','fields':[{'key':k,'enabled':True,'required':True} for k in ['name','email','phone','address','city','postal_code','notes']],'show_coupon':True}).model_dump()
    await db.documents.update_one({'id':'site'},{'$setOnInsert':{'id':'site','kind':'site','draft':site_value,'published':None,'version':1,'updated_at':stamp()}},upsert=True)
    sections=[
      {'id':'hero','type':'hero','eyebrow':'THE EVERYDAY, UPGRADED.','title':'Less noise.\nMore possibility.','title_bn':'কম শব্দ।\nআরও সম্ভাবনা।','subtitle':'Meet Auralis Studio H1. Immersive sound, effortless comfort.\nMade for the way you move.','subtitle_bn':'Auralis Studio H1। গভীর সাউন্ড, অনায়াস আরাম।','image':HERO,'button':'Discover the H1','link':'/product/auralis-studio-h1'},
      {'id':'features','type':'features','items':[{'title':'Delivered to your door','text':'Across Bangladesh','icon':'Truck'},{'title':'Quality, without question','text':'Warranty on every product','icon':'ShieldCheck'},{'title':'Here when you need us','text':'Real people. Real support.','icon':'Headset'}]},
      {'id':'categories','type':'categories','title':'Find your next upgrade','title_bn':'আপনার পরবর্তী আপগ্রেড খুঁজুন','eyebrow':'MADE FOR YOUR EVERYDAY'},
      {'id':'featured','type':'products','title':'Good tech. Great picks.','title_bn':'ভালো প্রযুক্তি। দারুণ পছন্দ।','subtitle':'The things we think you’ll love.','button':'View all products','link':'/shop','limit':4},
      {'id':'desk','type':'image_text','title':'Make space\nfor your best work.','subtitle':'A little less clutter. A lot more focus. Discover essentials that work as hard as you do.','eyebrow':'THE DESK EDIT','image':DESK,'button':'Upgrade your setup','link':'/shop?category=accessories'},
      {'id':'new','type':'products','title':'New to the collection','subtitle':'Fresh finds for what’s next.','limit':4,'button':'Explore new arrivals','link':'/shop?sort=newest'},
      {'id':'brands','type':'brands','title':'Considered brands. Exceptional ideas.'},
      {'id':'cta','type':'cta','eyebrow':'LET’S FIND YOUR NEXT FAVORITE','title':'A little help goes a long way.','subtitle':'Tell us what you’re looking for. We’ll help you find your fit.','button':'Talk to our team','link':'/support'}
    ]
    home=Page(title='Home',slug='home',sections=[Section(**s) for s in sections]).model_dump()
    await db.documents.update_one({'id':'page:home'},{'$setOnInsert':{'id':'page:home','kind':'page','draft':home,'published':home,'version':1,'updated_at':stamp()}},upsert=True)
    policies={
      'about':('Thoughtfully selected. Made for everyday.','VOLTORA is a working electronics storefront with a fictional demonstration catalog. Product names, prices and inventory are sample data for exploring the shopping experience. Store owners should replace this catalog and review all policies before accepting real orders.'),
      'contact':('Let’s talk tech.','Have a product question or need help with an order? Open a support conversation with our team. We keep your conversation together so nothing gets lost.'),
      'faq':('A few useful answers.','Orders currently ship within Bangladesh. Display currencies are estimates; checkout is charged in BDT. Cash on delivery is paid when you receive your order. Contact support for product and order questions.'),
      'shipping':('From our door to yours.','Available delivery zones, fees and estimated delivery times appear at checkout. Delivery estimates are not guarantees. Shipment references are entered by staff; no live carrier connection is currently available.'),
      'returns':('Let’s make it right.','Contact support with your order reference to request a return. Requests are reviewed by the store team. Eligibility, inspection requirements and refund timing require confirmation from the owner before this store accepts real orders.'),
      'warranty':('Confidence comes included.','Warranty information is shown on each product. Keep your order reference and contact support for a warranty request. The team will confirm the applicable terms and next steps.'),
      'privacy':('Your data, treated with care.','We use order and account information to fulfill purchases and provide support. Optional analytics is off until you consent. You may submit an export or deletion request from your account. Required transaction records may be retained. Security events are retained for 90 days; audit history for 365 days. This starter policy requires owner legal review.'),
      'terms':('The important details.','This store currently contains fictional demonstration products. Do not treat catalog specifications as manufacturer claims. Prices and stock are revalidated when placing an order. Policies require owner review before commercial use.')
    }
    for slug,(title,text) in policies.items():
        page=Page(title=slug.title(),slug=slug,sections=[Section(id=uid(),type='text',title=title,subtitle=text),Section(id=uid(),type='cta',title='Need a hand?',button='Contact support',link='/support')]).model_dump()
        await db.documents.update_one({'id':f'page:{slug}'},{'$setOnInsert':{'id':f'page:{slug}','kind':'page','draft':page,'published':page,'version':1,'updated_at':stamp()}},upsert=True)
    for i,(id,name,icon,image) in enumerate(CATEGORIES):
        await db.categories.update_one({'id':id},{'$setOnInsert':{'id':id,'name':name,'slug':id,'icon':icon,'image':image,'position':i,'enabled':True,'parent_id':'','seo_title':'','description':''}},upsert=True)
    brands=['Auralis','Nova','Orbit','Keyform','Lumixis','Nexora','Flux','Forma']
    for name in brands:
        await db.brands.update_one({'id':name.lower()},{'$setOnInsert':{'id':name.lower(),'name':name,'slug':name.lower(),'description':'Fictional demonstration brand'}},upsert=True)
    for name in ['Everyday essentials','The desk edit','On the move']:
        await db.collections.update_one({'name':name},{'$setOnInsert':{'id':uid(),'name':name,'slug':name.lower().replace(' ','-'),'description':''}},upsert=True)
    await raw_db[PREFIX+'migrations'].update_one({'id':'initial_indexes_v1'}, {'$set':{'complete':True,'at':stamp()}}, upsert=True)
    if await db.products.count_documents({}):
        return
    base=[
      ('Auralis Studio H1','audio','Auralis',18900,22900,photo('photo-1546435770-a3e426bf472b'),'Wireless noise-cancelling headphones','OUR PICK',{'Battery':'Up to 40 hours','Connectivity':'Bluetooth 5.3','Driver':'40 mm','Weight':'250 g'}),
      ('NovaBook Air 14','laptops','Nova',89900,0,photo('photo-1496181133206-80ce9b88a853'),'Big ideas. In a lighter package.','NEW',{'Display':'14-inch IPS','Memory':'16 GB','Storage':'512 GB SSD','Weight':'1.25 kg'}),
      ('Orbit Watch S2','wearables','Orbit',12900,14900,photo('photo-1523275335684-37898b6baf30'),'A smarter rhythm for your everyday','',{'Display':'1.4-inch AMOLED','Battery':'Up to 10 days','Resistance':'5 ATM','Connectivity':'Bluetooth 5.2'}),
      ('Auralis Pods Mini','audio','Auralis',6900,8900,EARBUDS,'Small size. Seriously good sound.','POPULAR',{'Battery':'24 hours with case','Connectivity':'Bluetooth 5.3','Weight':'4.8 g per earbud','Charging':'USB-C'}),
      ('Keyform K75 Mechanical','accessories','Keyform',8900,0,photo('photo-1587829741301-dc798b83add3'),'Your ideas deserve a better keyboard','NEW',{'Layout':'75% compact','Switches':'Tactile mechanical','Connectivity':'USB-C','Backlight':'White LED'}),
      ('Nova Phone X1','phones','Nova',42900,0,photo('photo-1511707171634-5f897ff02aa9'),'Everything you need. Nothing you don’t.','',{'Display':'6.4-inch OLED','Storage':'128 GB','Camera':'50 MP','Battery':'4,800 mAh'}),
      ('Flux Pro Controller','gaming','Flux',5900,6900,photo('photo-1612287230202-1ff1d85d1bdf'),'Play your way','',{'Connectivity':'Bluetooth / USB-C','Battery':'20 hours','Compatibility':'PC / mobile','Weight':'245 g'}),
      ('Lumixis Mirror C1','cameras','Lumixis',76900,0,photo('photo-1516035069371-29a1b244cc32'),'Capture a different perspective','NEW',{'Sensor':'24 MP APS-C','Video':'4K 30fps','Mount':'Interchangeable','Weight':'380 g'})
    ]
    quantities={}
    for i in range(56):
        name,category,brand,price,compare,image,subtitle,badge,specs=base[i%8]
        if i>=8:
            name += ' ' + ['Essential','Plus','Pro','Lite','Max','Edition'][i//8-1]
            price+=i*125
            compare=0
            badge=''
        slug=name.lower().replace(' ','-')
        id=f'product-{i+1:03}'
        variants=[]
        for j,option in enumerate(['Graphite','Silver'] if category not in ['laptops','phones'] else ['128 GB','256 GB']):
            vid=f'{id}-v{j+1}'
            variants.append({'id':vid,'sku':f'VT-{i+1:04}-{j+1}','options':{'Finish' if category not in ['laptops','phones'] else 'Storage':option},'price':(price+j*1000)*100})
            quantities[vid]=8+(i*7+j)%35
        product=Product(name=name,slug=slug,sku=f'VT-{i+1:04}',brand=brand,category=category,description=f'{subtitle}. Thoughtfully designed for your daily routine, {name} brings together considered details and practical performance. This is a fictional demonstration product; specifications and imagery are illustrative.',subtitle=subtitle,price=price*100,compare_price=compare*100,images=[image],specs=specs,variants=variants,badge=badge,featured=i<4,collection='Everyday essentials').model_dump()
        row=product|{'id':id,'published':True,'version':1,'created_at':stamp(),'updated_at':stamp(),'demo':True}
        await db.products.insert_one(row.copy())
        await db.product_drafts.insert_one({'id':id,'value':product,'version':1})
    await db.inventory.update_one({'id':'main'},{'$setOnInsert':{'id':'main','quantities':quantities,'reservations':{}}},upsert=True)
    await db.coupons.update_one({'code':'HELLO10'},{'$setOnInsert':{'id':uid(),'code':'HELLO10','type':'percentage','value':10,'min_spend':100000,'max_uses':100,'used':0,'enabled':True,'starts_at':'','ends_at':'','product_ids':[],'category_ids':[]}},upsert=True)