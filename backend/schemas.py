from typing import Literal
from pydantic import Field, field_validator
from core import Input

def safe_url(value):
    if value and not (value.startswith('https://') or (value.startswith('/') and not value.startswith('//'))):
        raise ValueError('Use a secure URL or a relative store path')
    return value

class Variant(Input):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    sku: str = Field(min_length=1,max_length=80)
    options: dict[str,str] = Field(default_factory=dict,max_length=12)
    price: int = Field(ge=0,le=1000000000)

class Product(Input):
    name: str = Field(min_length=2,max_length=180)
    name_bn: str = Field(default='',max_length=180)
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$',max_length=180)
    sku: str = Field(min_length=1,max_length=80)
    brand: str = Field(min_length=1,max_length=80)
    category: str = Field(min_length=1,max_length=80)
    description: str = Field(default='',max_length=20000)
    description_bn: str = Field(default='',max_length=20000)
    subtitle: str = Field(default='',max_length=240)
    price: int = Field(ge=0,le=1000000000)
    compare_price: int = Field(default=0,ge=0,le=1000000000)
    images: list[str] = Field(default_factory=list,max_length=24)
    specs: dict[str,str] = Field(default_factory=dict,max_length=50)
    variants: list[Variant] = Field(min_length=1,max_length=100)
    warranty: str = Field(default='1-year limited warranty',max_length=500)
    badge: str = Field(default='',max_length=40)
    featured: bool = False
    collection: str = Field(default='',max_length=80)
    seo_title: str = Field(default='',max_length=180)
    seo_description: str = Field(default='',max_length=500)
    sale_ends_at: str = Field(default='',max_length=30)
    @field_validator('images')
    @classmethod
    def images_valid(cls, value):
        return [safe_url(x) for x in value]
    @field_validator('variants')
    @classmethod
    def variants_unique(cls, value):
        if len({v.id for v in value})!=len(value) or len({v.sku for v in value})!=len(value):
            raise ValueError('Variant IDs and SKUs must be unique')
        return value

class Theme(Input):
    id: str = Field(pattern=r'^[a-z0-9-]{1,80}$')
    name: str = Field(min_length=2,max_length=80)
    description: str = Field(default='',max_length=240)
    primary: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    background: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    surface: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    text: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    muted: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    border: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    dark_background: str = Field(default='#161b18',pattern=r'^#[0-9a-fA-F]{6}$')
    dark_surface: str = Field(default='#232a25',pattern=r'^#[0-9a-fA-F]{6}$')
    dark_text: str = Field(default='#f4f6f2',pattern=r'^#[0-9a-fA-F]{6}$')
    heading_font: Literal['Manrope','DM Sans','Space Grotesk','IBM Plex Mono','Playfair Display','Outfit'] = 'Manrope'
    body_font: Literal['DM Sans','Manrope','Space Grotesk','Outfit'] = 'DM Sans'
    radius: int = Field(default=6,ge=0,le=24)
    spacing: int = Field(default=64,ge=32,le=100)
    gap: int = Field(default=24,ge=8,le=40)
    width: int = Field(default=1440,ge=1080,le=1680)
    columns: int = Field(default=4,ge=3,le=5)
    card_style: Literal['clean','bordered','elevated','technical','fashion','food','grocery'] = 'clean'
    image_ratio: Literal['square','landscape','portrait'] = 'square'
    header_style: Literal['classic','centered','compact','bordered'] = 'classic'
    hero_style: Literal['editorial','centered','compact','panoramic'] = 'editorial'
    footer_style: Literal['dark','light','minimal'] = 'dark'
    button_style: Literal['solid','outline','pill'] = 'solid'
    motion: bool = True
    motion_duration: int = Field(default=180,ge=0,le=800)
    motion_easing: Literal['ease','ease-in','ease-out','ease-in-out','linear'] = 'ease-out'
    heading_scale: float = Field(default=1.0,ge=0.85,le=1.4)
    body_font_size: int = Field(default=16,ge=13,le=19)
    heading_weight: int = Field(default=800,ge=300,le=900)
    body_weight: int = Field(default=400,ge=300,le=700)
    letter_spacing: int = Field(default=0,ge=-1,le=4)
    line_height: int = Field(default=155,ge=120,le=200)
    shadow_style: Literal['none','soft','medium','strong'] = 'soft'
    input_style: Literal['square','rounded','pill'] = 'rounded'
    product_badge_style: Literal['solid','outline','soft'] = 'solid'
    micro_interactions: bool = True
    industry: Literal['electronics','general','fashion','food','sweets','grocery','beauty','gaming','accessories','marketplace','home'] = 'electronics'
    secondary: str = Field(default='#5b8f5b',pattern=r'^#[0-9a-fA-F]{6}$')
    accent: str = Field(default='#f0b429',pattern=r'^#[0-9a-fA-F]{6}$')
    success: str = Field(default='#3f9d63',pattern=r'^#[0-9a-fA-F]{6}$')
    card_background: str = Field(default='#ffffff',pattern=r'^#[0-9a-fA-F]{6}$')
    category_style: Literal['grid','rail','mosaic'] = 'grid'
    product_layout: Literal['classic','stacked','split'] = 'classic'
    icon_style: Literal['thin','regular','bold'] = 'regular'
    animation_level: Literal['none','subtle','rich'] = 'subtle'
    loading_style: Literal['none','minimal','branded'] = 'branded'

class Section(Input):
    id: str = Field(max_length=80)
    type: Literal['hero','banner','text','image','image_text','products','categories','brands','features','faq','cta','spacer','divider']
    title: str = Field(default='',max_length=240)
    title_bn: str = Field(default='',max_length=240)
    subtitle: str = Field(default='',max_length=3000)
    subtitle_bn: str = Field(default='',max_length=3000)
    eyebrow: str = Field(default='',max_length=100)
    image: str = Field(default='',max_length=2000)
    button: str = Field(default='',max_length=80)
    link: str = Field(default='/shop',max_length=2000)
    enabled: bool = True
    mobile: bool = True
    desktop: bool = True
    alignment: Literal['left','center','right'] = 'left'
    padding: int = Field(default=0,ge=0,le=120)
    background: str = Field(default='',pattern=r'^(#[0-9a-fA-F]{6})?$')
    color: str = Field(default='',pattern=r'^(#[0-9a-fA-F]{6})?$')
    font_size: int = Field(default=0,ge=0,le=72)
    border: bool = False
    limit: int = Field(default=4,ge=1,le=16)
    category: str = Field(default='',max_length=80)
    product_ids: list[str] = Field(default_factory=list,max_length=12)
    items: list[dict[str,str]] = Field(default_factory=list,max_length=30)
    @field_validator('image','link')
    @classmethod
    def urls(cls,value):
        return safe_url(value)

class Page(Input):
    title: str = Field(min_length=1,max_length=180)
    slug: str = Field(pattern=r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
    seo_title: str = Field(default='',max_length=180)
    seo_description: str = Field(default='',max_length=500)
    indexable: bool = True
    sections: list[Section] = Field(default_factory=list,max_length=60)

class Features(Input):
    search: bool = True
    wishlist: bool = True
    compare: bool = True
    reviews: bool = True
    quick_add: bool = True
    guest_checkout: bool = True
    registration: bool = True
    support: bool = True
    ai_chat: bool = False
    ai_authoring: bool = False
    coupons: bool = True
    cod: bool = True
    bank_transfer: bool = True
    online_payments: bool = False
    shipping: bool = True
    pickup: bool = True
    multicurrency: bool = True
    multilingual: bool = True
    dark_mode: bool = True
    analytics: bool = False
    location_picker: bool = True
    courier_delivery: bool = False
    loyalty: bool = False
    store_credit: bool = False
    returns: bool = False
    notifications: bool = True
    otp_login: bool = False
    phone_auth: bool = False
    social_login: bool = False
    email_verification: bool = False
    ai_customer: bool = False
    ai_admin: bool = False
    ai_product_gen: bool = False
    ai_translation: bool = False
    ai_seo: bool = False
    ai_support_suggest: bool = False
    ai_recommendations: bool = False
    ai_location: bool = False
    ai_analytics: bool = False

class Currency(Input):
    code: str = Field(pattern=r'^[A-Z]{3}$')
    symbol: str = Field(max_length=8)
    rate: float = Field(gt=0,le=100000)
    decimals: int = Field(default=2,ge=0,le=3)
    enabled: bool = True

class Address(Input):
    '''Structured Bangladesh delivery address resolved through the location system.'''
    label: str = Field(default='',max_length=60)
    division_id: str = Field(default='',max_length=120)
    district_id: str = Field(default='',max_length=120)
    upazila_id: str = Field(default='',max_length=120)
    area_id: str = Field(default='',max_length=140)
    postcode: str = Field(default='',max_length=10)
    address_line: str = Field(default='',max_length=400)
    phone: str = Field(default='',max_length=25)

class Shipping(Input):
    id: str = Field(pattern=r'^[a-z0-9-]+$')
    name: str = Field(min_length=1,max_length=100)
    fee: int = Field(ge=0,le=1000000)
    free_above: int = Field(default=0,ge=0)
    estimate: str = Field(default='',max_length=200)
    enabled: bool = True
    divisions: list[str] = Field(default_factory=list,max_length=8)
    districts: list[str] = Field(default_factory=list,max_length=200)
    courier: str = Field(default='',max_length=40)

class PaymentMethod(Input):
    id: Literal['cod','bank_transfer','stripe','sslcommerz','bkash','nagad','rocket','upay','paypal','mock']
    label: str = Field(min_length=1,max_length=100)
    enabled: bool = True
    min_amount: int = Field(default=0,ge=0)
    max_amount: int = Field(default=100000000,gt=0)
    instructions: str = Field(default='',max_length=3000)

class SocialLink(Input):
    label: str = Field(min_length=1,max_length=40)
    url: str = Field(max_length=2000)
    @field_validator('url')
    @classmethod
    def url_valid(cls,value):
        return safe_url(value)

class NavLink(Input):
    label: str = Field(min_length=1,max_length=80)
    url: str = Field(max_length=2000)
    @field_validator('url')
    @classmethod
    def url_valid(cls,value):
        return safe_url(value)

class AuthConfig(Input):
    background_image: str = Field(default='',max_length=2000)
    @field_validator('background_image')
    @classmethod
    def img_valid(cls,value):
        return safe_url(value)
    style: Literal['split','card','centered'] = 'split'

# ---- Website builder: site-wide header/footer/auth/checkout document ----
class SiteHeaderBlock(Input):
    id: str = Field(min_length=1,max_length=60)
    type: Literal['announcement','utility_message','track_order','support_link','language','currency',
                  'menu','logo','search','contact',
                  'notifications','dark_mode','account','wishlist','compare','cart'] = 'logo'
    enabled: bool = True
    label: str = Field(default='',max_length=120)
    url: str = Field(default='',max_length=2000)
    @field_validator('url')
    @classmethod
    def url_valid(cls,value):
        return safe_url(value)

class SiteHeader(Input):
    layout: Literal['classic','centered','compact','bordered'] = 'classic'
    sticky: bool = True
    top: list[SiteHeaderBlock] = Field(default_factory=list,max_length=12)
    main: list[SiteHeaderBlock] = Field(default_factory=list,max_length=6)
    actions: list[SiteHeaderBlock] = Field(default_factory=list,max_length=10)
    show_nav: bool = True
    show_browse: bool = True
    nav_deal_label: str = Field(default='New arrivals',max_length=60)
    utility_message: str = Field(default='',max_length=160)

class SiteFooterColumn(Input):
    id: str = Field(min_length=1,max_length=60)
    type: Literal['brand','links','newsletter','social','text'] = 'links'
    title: str = Field(default='',max_length=120)
    text: str = Field(default='',max_length=500)
    enabled: bool = True
    links: list[NavLink] = Field(default_factory=list,max_length=12)

class SiteFooter(Input):
    style: Literal['dark','light','minimal'] = 'dark'
    columns: list[SiteFooterColumn] = Field(default_factory=list,max_length=6)
    show_social: bool = True
    social_links: list[SocialLink] = Field(default_factory=list,max_length=8)
    show_payments: bool = True
    payment_badges: list[str] = Field(default_factory=list,max_length=12)
    copyright: str = Field(default='',max_length=200)
    legal_links: list[NavLink] = Field(default_factory=list,max_length=8)

class SiteAuth(Input):
    form_title: str = Field(default='Welcome back.', min_length=1, max_length=80)
    button_label: str = Field(default='Sign in', min_length=1, max_length=40)
    layout: Literal['split','card','centered'] = 'split'
    side_heading: str = Field(default='',max_length=160)
    side_text: str = Field(default='',max_length=400)
    side_image: str = Field(default='',max_length=2000)
    @field_validator('side_image')
    @classmethod
    def side_img_valid(cls,value):
        return safe_url(value)
    side_bullets: list[str] = Field(default_factory=list,max_length=6)
    allow_email: bool = True
    allow_phone: bool = True
    allow_otp: bool = True
    allow_social: bool = True
    show_register: bool = True
    card_note: str = Field(default='',max_length=200)

class SiteCheckoutField(Input):
    key: Literal['name','email','phone','address','city','postal_code','notes'] = 'name'
    enabled: bool = True
    label: str = Field(default='',max_length=80)
    required: bool = True

class SiteCheckout(Input):
    layout: Literal['two_column','single'] = 'two_column'
    fields: list[SiteCheckoutField] = Field(default_factory=list,max_length=8)
    show_coupon: bool = True
    trust_badges: list[str] = Field(default_factory=list,max_length=6)
    thank_you_title: str = Field(default='',max_length=120)
    thank_you_message: str = Field(default='',max_length=300)
    terms_label: str = Field(default='',max_length=160)

class SiteConfig(Input):
    header: SiteHeader = Field(default_factory=SiteHeader)
    footer: SiteFooter = Field(default_factory=SiteFooter)
    auth: SiteAuth = Field(default_factory=SiteAuth)
    checkout: SiteCheckout = Field(default_factory=SiteCheckout)

# ---- Mira AI storefront widget configuration ----
class MiraConfig(Input):
    position: Literal['bottom_right','bottom_left'] = 'bottom_right'
    icon: Literal['sparkles','bot','chat'] = 'sparkles'
    greeting: str = Field(default='',max_length=300)
    quick_prompts: list[str] = Field(default_factory=list,max_length=6)
    delay_ms: int = Field(default=0,ge=0,le=10000)
    pages: list[Literal['home','shop','product','cart','checkout','account','support','assistant','page']] = Field(default_factory=list,max_length=10)

class HeaderConfig(Input):
    sticky: bool = True
    show_announcement: bool = True
    show_announcement_cta: bool = True
    show_search: bool = True
    show_wishlist: bool = True
    show_compare: bool = True
    show_language: bool = True
    show_currency: bool = True
    show_track_order: bool = True

class FooterConfig(Input):
    show_newsletter: bool = True
    social_links: list[SocialLink] = Field(default_factory=list,max_length=8)
    payment_badges: list[str] = Field(default_factory=list,max_length=12)
    copyright: str = Field(default='',max_length=200)

class Settings(Input):
    brand: str = Field(min_length=1,max_length=50)
    country: str = Field(default='BD',pattern=r'^[A-Z]{2}$')
    timezone: str = Field(default='Asia/Dhaka',max_length=80)
    base_currency: str = Field(default='BDT',pattern=r'^[A-Z]{3}$')
    tagline: str = Field(default='',max_length=200)
    announcement: str = Field(default='',max_length=240)
    announcement_bn: str = Field(default='',max_length=240)
    email: str = Field(default='',max_length=150)
    phone: str = Field(default='',max_length=80)
    address: str = Field(default='',max_length=500)
    footer_text: str = Field(default='',max_length=500)
    demo_catalog: bool = True
    features: Features
    currencies: list[Currency] = Field(min_length=1,max_length=30)
    shipping: list[Shipping] = Field(min_length=1,max_length=20)
    payments: list[PaymentMethod] = Field(min_length=1,max_length=10)
    tax_rate: float = Field(default=0,ge=0,le=100)
    tax_inclusive: bool = True
    loyalty_earn_rate: float = Field(default=1,ge=0,le=100)
    loyalty_point_poisha: int = Field(default=50,ge=1,le=1000)
    affiliate_commission_pct: float = Field(default=5,ge=0,le=50)
    navigation: list[NavLink] = Field(default_factory=list,max_length=15)
    footer_links: list[NavLink] = Field(default_factory=list,max_length=25)
    translations: dict[str,dict[str,str]] = Field(default_factory=dict,max_length=12)
    mode: Literal['live','maintenance','coming_soon'] = 'live'
    maintenance_message: str = Field(default='We will be back shortly.',max_length=500)
    brand_logo: str = Field(default='',max_length=2000)
    brand_logo_height: int = Field(default=36,ge=18,le=120)
    not_found_message: str = Field(default='',max_length=300)
    auth_config: AuthConfig = Field(default_factory=AuthConfig)
    header_config: HeaderConfig = Field(default_factory=HeaderConfig)
    footer_config: FooterConfig = Field(default_factory=FooterConfig)
    mira_config: MiraConfig = Field(default_factory=MiraConfig)
    seo_title: str = Field(default='VOLTORA — Technology for your everyday.',max_length=180)
    seo_description: str = Field(default='',max_length=500)
    @field_validator('currencies')
    @classmethod
    def currencies_valid(cls,value):
        if len({x.code for x in value})!=len(value):
            raise ValueError('Currency codes must be unique')
        if not any(x.rate==1 and x.enabled for x in value):
            raise ValueError('The base currency must remain enabled at rate 1')
        return value