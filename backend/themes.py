from schemas import Theme

PRESETS = [
 ('premium-electronics','Premium Electronics','Product-led. Carefully considered.','#b9f46b','#ffffff','#f4f5f3','#202420','Manrope',6,64,24,4,'clean','square','classic','editorial','dark','solid'),
 ('minimal-tech','Minimal Tech','Quiet design. All about the essentials.','#d6ea77','#ffffff','#f7f7f5','#292b26','DM Sans',2,80,32,3,'clean','portrait','centered','panoramic','minimal','outline'),
 ('cyber-dark','Cyber Dark','High contrast. Uncompromising focus.','#63e6da','#111616','#1d2727','#edf4f2','Space Grotesk',0,40,12,5,'technical','square','compact','compact','dark','outline'),
 ('future-lab','Future Lab','A new perspective on technology.','#c8f266','#f0f4f1','#e4ece7','#18362c','Space Grotesk',0,72,32,3,'bordered','landscape','bordered','editorial','light','solid'),
 ('precision-minimal','Precision Minimal','Less noise. More possibility.','#dedfe1','#fafafa','#eeeeef','#202125','Manrope',8,96,36,3,'clean','portrait','centered','centered','minimal','pill'),
 ('gaming-arena','Gaming Arena','Built for your next level.','#f4a53f','#151516','#232324','#f5f5f0','Outfit',4,40,16,5,'bordered','square','compact','compact','dark','solid'),
 ('neon-gadget','Neon Gadget','Big ideas. Bright details.','#ddfa47','#181b17','#252b21','#f0f6e9','Space Grotesk',0,48,20,4,'technical','landscape','bordered','panoramic','dark','outline'),
 ('luxury-black','Luxury Black','Understated by design.','#ddd1b8','#121212','#1f1f1f','#f3f0e9','Playfair Display',0,96,36,3,'clean','portrait','centered','centered','minimal','outline'),
 ('clean-commerce','Clean Commerce','Great technology, made simple.','#75ddb4','#ffffff','#f2f6f5','#21302a','DM Sans',6,56,20,4,'bordered','square','classic','compact','light','solid'),
 ('material-tech','Material Tech','Clarity at every level.','#87cbb9','#f1f5f3','#ffffff','#1c3027','Outfit',8,56,24,4,'elevated','square','classic','editorial','light','pill'),
 ('glass-studio','Glass Studio','A lighter point of view.','#b5ddf6','#edf5f7','#ffffff','#23434d','Manrope',8,72,28,3,'elevated','landscape','centered','panoramic','light','pill'),
 ('editorial-tech','Editorial Tech','Good design has a story.','#e6a993','#fafaf7','#eeeee8','#302e27','Playfair Display',0,88,32,3,'clean','portrait','bordered','editorial','minimal','outline'),
 ('bold-marketplace','Bold Marketplace','Discover more, every day.','#ffe47d','#ffffff','#f5f5ed','#242822','Outfit',4,32,12,5,'bordered','square','compact','compact','dark','solid'),
 ('soft-modern','Soft Modern','Technology with a softer side.','#b3d5bb','#fbfcf9','#eff4e9','#354337','DM Sans',16,80,28,3,'elevated','square','centered','centered','light','pill'),
 ('industrial-digital','Industrial Digital','Purpose-built. Precisely detailed.','#e5e36b','#eceeeb','#e0e4df','#242d26','IBM Plex Mono',0,40,12,4,'technical','landscape','bordered','panoramic','dark','outline'),
 ('modern-shopping','Modern Shopping','Everything you need, beautifully arranged.','#0d9488','#ffffff','#f1f5f4','#1e292b','Outfit',10,60,20,4,'elevated','landscape','classic','centered','light','solid'),
 ('luxury-fashion','Luxury Fashion','Fashion, framed like art.','#c9a227','#141414','#1f1d1a','#f5f1e8','Playfair Display',0,96,32,3,'fashion','portrait','centered','panoramic','minimal','outline'),
 ('clothing-boutique','Clothing Boutique','Soft, considered, wearable.','#b76e79','#fdf8f6','#f7efec','#3d2b2e','Playfair Display',12,80,24,4,'fashion','portrait','centered','editorial','light','outline'),
 ('food-market','Food Market','Fresh finds for every table.','#ea580c','#fffbeb','#fef3c7','#431407','Outfit',14,56,18,4,'food','landscape','classic','compact','light','solid'),
 ('sweet-shop','Sweet Shop','A little sugar in every click.','#ec4899','#fff5f8','#fce7f0','#4a1930','DM Sans',18,64,18,4,'food','square','centered','centered','light','pill'),
 ('grocery-store','Grocery Store','Daily essentials, one tap away.','#16a34a','#ffffff','#f0fdf4','#14532d','DM Sans',8,48,12,5,'grocery','square','compact','compact','light','solid'),
 ('beauty-store','Beauty Store','Rituals for your best skin.','#9d5c8c','#fdfbfc','#f5eef2','#33202e','Playfair Display',20,88,26,3,'elevated','portrait','centered','editorial','light','pill'),
 ('accessories-store','Accessories Store','The details that finish the look.','#475569','#f8fafc','#eef2f6','#0f172a','Outfit',6,56,18,4,'bordered','square','classic','compact','dark','solid'),
 ('multi-marketplace','Multi-Purpose Marketplace','One store. Endless aisles.','#2563eb','#ffffff','#f1f5f9','#0f172a','Outfit',6,44,12,5,'bordered','landscape','compact','compact','light','solid'),
 ('dark-premium','Dark Premium','After-dark commerce.','#7ef0b2','#0b0f0e','#141b18','#eef4f0','Space Grotesk',4,56,20,4,'elevated','landscape','bordered','panoramic','dark','solid'),
 ('home-living','Home & Living','A calmer kind of home.','#c96f4a','#faf7f2','#f1eae2','#33302b','Playfair Display',10,88,26,3,'elevated','landscape','centered','editorial','light','pill')
]

INDUSTRY_TAGS = {
    'premium-electronics':'electronics','minimal-tech':'electronics','cyber-dark':'electronics',
    'future-lab':'electronics','precision-minimal':'general','gaming-arena':'gaming',
    'neon-gadget':'electronics','luxury-black':'fashion','clean-commerce':'general',
    'material-tech':'electronics','glass-studio':'beauty','editorial-tech':'general',
    'bold-marketplace':'marketplace','soft-modern':'general','industrial-digital':'electronics',
    'modern-shopping':'general','luxury-fashion':'fashion','clothing-boutique':'fashion',
    'food-market':'food','sweet-shop':'sweets','grocery-store':'grocery','beauty-store':'beauty',
    'accessories-store':'accessories','multi-marketplace':'marketplace','dark-premium':'marketplace','home-living':'home',
}

EXTRA_VARIANTS = {
    'cyber-dark': {'shadow_style':'strong','input_style':'square','heading_weight':700,'letter_spacing':1},
    'soft-modern': {'shadow_style':'medium','input_style':'pill','heading_weight':700,'product_badge_style':'soft'},
    'material-tech': {'shadow_style':'medium','micro_interactions':True,'heading_weight':700},
    'minimal-tech': {'shadow_style':'none','heading_weight':700,'letter_spacing':1,'line_height':165},
    'luxury-black': {'shadow_style':'none','heading_weight':400,'body_weight':300,'letter_spacing':2},
    'industrial-digital': {'shadow_style':'none','input_style':'square','heading_weight':600},
    'bold-marketplace': {'shadow_style':'strong','heading_weight':900,'micro_interactions':True},
    'glass-studio': {'shadow_style':'medium','heading_weight':700},
    'editorial-tech': {'heading_weight':500,'letter_spacing':1,'line_height':170},
    'gaming-arena': {'shadow_style':'strong','heading_weight':900,'letter_spacing':1},
    # ---- VOLTORA 3.0 industry presets: full variant combinations ----
    'modern-shopping': {'industry':'general','secondary':'#f59e0b','accent':'#0f766e','success':'#16a34a','card_background':'#ffffff',
                        'category_style':'rail','product_layout':'split','icon_style':'regular','animation_level':'subtle',
                        'shadow_style':'medium','heading_weight':800},
    'luxury-fashion': {'industry':'fashion','secondary':'#8a6d1d','accent':'#f5e6c8','success':'#6b7f3f','card_background':'#1a1815',
                       'category_style':'rail','product_layout':'split','icon_style':'thin','animation_level':'rich',
                       'shadow_style':'none','input_style':'square','heading_weight':500,'body_weight':300,'letter_spacing':2,'line_height':170},
    'clothing-boutique': {'industry':'fashion','secondary':'#d8a48f','accent':'#7c5c52','success':'#7a9d6f','card_background':'#ffffff',
                          'category_style':'rail','product_layout':'split','icon_style':'thin','animation_level':'rich',
                          'shadow_style':'soft','product_badge_style':'outline','heading_weight':600,'letter_spacing':1},
    'food-market': {'industry':'food','secondary':'#dc2626','accent':'#facc15','success':'#22c55e','card_background':'#ffffff',
                    'category_style':'mosaic','product_layout':'stacked','icon_style':'bold','animation_level':'subtle',
                    'shadow_style':'medium','product_badge_style':'soft','heading_weight':800,'radius':14},
    'sweet-shop': {'industry':'sweets','secondary':'#a855f7','accent':'#fbbf24','success':'#34d399','card_background':'#ffffff',
                   'category_style':'grid','product_layout':'stacked','icon_style':'regular','animation_level':'rich',
                   'shadow_style':'medium','input_style':'pill','product_badge_style':'soft','heading_weight':700,'radius':18},
    'grocery-store': {'industry':'grocery','secondary':'#0d9488','accent':'#f59e0b','success':'#16a34a','card_background':'#ffffff',
                      'category_style':'mosaic','product_layout':'classic','icon_style':'bold','animation_level':'none',
                      'shadow_style':'soft','heading_weight':700,'radius':8,'spacing':48,'gap':12,'columns':5},
    'beauty-store': {'industry':'beauty','secondary':'#c08497','accent':'#d4b483','success':'#84a98c','card_background':'#ffffff',
                     'category_style':'rail','product_layout':'split','icon_style':'thin','animation_level':'rich',
                     'shadow_style':'medium','input_style':'pill','product_badge_style':'soft','heading_weight':500,'letter_spacing':1,'line_height':170},
    'accessories-store': {'industry':'accessories','secondary':'#0ea5e9','accent':'#f97316','success':'#22c55e','card_background':'#ffffff',
                          'category_style':'grid','product_layout':'split','icon_style':'regular','animation_level':'subtle',
                          'shadow_style':'soft','heading_weight':700,'radius':6},
    'multi-marketplace': {'industry':'marketplace','secondary':'#7c3aed','accent':'#f59e0b','success':'#16a34a','card_background':'#ffffff',
                          'category_style':'mosaic','product_layout':'classic','icon_style':'regular','animation_level':'subtle',
                          'shadow_style':'soft','heading_weight':800,'radius':6,'spacing':44,'gap':12,'columns':5},
    'home-living': {'industry':'home','secondary':'#8a9b6e','accent':'#c96f4a','success':'#6b8f71','card_background':'#ffffff','category_style':'rail','product_layout':'split','icon_style':'thin','animation_level':'subtle','shadow_style':'medium','product_badge_style':'soft','heading_weight':500,'letter_spacing':1,'line_height':170,'loading_style':'branded'},
    'dark-premium': {'industry':'marketplace','secondary':'#38bdf8','accent':'#7ef0b2','success':'#34d399','card_background':'#141b18',
                     'category_style':'rail','product_layout':'split','icon_style':'regular','animation_level':'rich',
                     'shadow_style':'strong','heading_weight':800,'letter_spacing':1},
}

DARK_BACKGROUNDS = ['#111616','#151516','#181b17','#121212','#141414','#0b0f0e']

def theme_presets():
    result=[]
    for row in PRESETS:
        keys=['id','name','description','primary','background','surface','text','heading_font','radius','spacing','gap','columns','card_style','image_ratio','header_style','hero_style','footer_style','button_style']
        d=dict(zip(keys,row))
        dark=d['background'] in DARK_BACKGROUNDS
        d.update(muted='#a5afa7' if dark else '#737a73',border='#394238' if dark else '#e2e7df')
        extras=dict(EXTRA_VARIANTS.get(d['id'],{}))
        extras.setdefault('industry',INDUSTRY_TAGS.get(d['id'],'general'))
        if dark:
            extras.setdefault('card_background', d['surface'])
            extras.setdefault('secondary', '#64748b')
            extras.setdefault('accent', d['primary'])
            extras.setdefault('success', '#34d399')
        d.update(extras)
        result.append(Theme(**d).model_dump())
    return result
