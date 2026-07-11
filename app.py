import os
import json
import re
import time
import hmac
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import markdown
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from dotenv import load_dotenv
from threading import Lock

load_dotenv()

# === In-Memory Cache ===
class SimpleCache:
    """Permanent in-memory cache - only invalidated by admin actions"""
    def __init__(self):
        self._data = {}
        self._lock = Lock()

    def get(self, key):
        with self._lock:
            return self._data.get(key)

    def set(self, key, value):
        with self._lock:
            self._data[key] = value

    def invalidate(self, key=None):
        with self._lock:
            if key:
                self._data.pop(key, None)
            else:
                self._data.clear()

cache = SimpleCache()  # Permanent cache, invalidated only by admin
html_cache = SimpleCache()  # Cache for rendered HTML pages

# === Login Rate Limiter ===
class LoginRateLimiter:
    """Rate limiter to prevent brute-force login attacks"""
    def __init__(self, max_attempts=5, lockout_seconds=900):
        self._attempts = {}  # {ip: {'count': int, 'first_attempt': timestamp}}
        self._lockouts = {}  # {ip: lockout_until_timestamp}
        self._lock = Lock()
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds  # 15 minutes default

    def is_locked(self, ip):
        with self._lock:
            if ip in self._lockouts:
                if time.time() < self._lockouts[ip]:
                    return True
                else:
                    del self._lockouts[ip]
                    self._attempts.pop(ip, None)
            return False

    def record_failure(self, ip):
        with self._lock:
            now = time.time()
            if ip not in self._attempts:
                self._attempts[ip] = {'count': 1, 'first_attempt': now}
            else:
                # Reset if first attempt was more than lockout period ago
                if now - self._attempts[ip]['first_attempt'] > self.lockout_seconds:
                    self._attempts[ip] = {'count': 1, 'first_attempt': now}
                else:
                    self._attempts[ip]['count'] += 1

            if self._attempts[ip]['count'] >= self.max_attempts:
                self._lockouts[ip] = now + self.lockout_seconds
                return True  # Now locked
            return False

    def clear(self, ip):
        with self._lock:
            self._attempts.pop(ip, None)
            self._lockouts.pop(ip, None)

    def get_remaining_lockout(self, ip):
        with self._lock:
            if ip in self._lockouts:
                remaining = self._lockouts[ip] - time.time()
                return max(0, int(remaining))
            return 0

login_limiter = LoginRateLimiter(max_attempts=5, lockout_seconds=900)  # 5 attempts, 15 min lockout

app = Flask(__name__)

# Optional Sentry error monitoring — a no-op until BOTH the sentry_sdk package
# and the SENTRY_DSN env var are present, so it never breaks startup.
try:
    import sentry_sdk
    if os.getenv('SENTRY_DSN'):
        sentry_sdk.init(dsn=os.getenv('SENTRY_DSN'), traces_sample_rate=0.0)
except ImportError:
    pass

# Behind Caddy: honor X-Forwarded-Proto/Host so request.url_root is https
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
# Fail closed: a missing SECRET_KEY would silently sign sessions with a shared
# default, so refuse to start rather than run insecurely.
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError("SECRET_KEY must be set")
# Session cookie hardening. SECURE defaults on for prod HTTPS; local dev over
# http can disable it via SESSION_COOKIE_SECURE=0 so cookies still stick.
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', '1') != '0'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB (review photos: up to 4 phone shots/request)
# Public web base URL (for links sent outside a request, e.g. LINE messages).
# Env-driven so a domain change never needs a code edit.
SITE_URL = os.environ.get('SITE_URL', 'https://abbeystoys.com').rstrip('/')

def _auth_next(dest, is_new, method):
    """Append GA4 signal params so base.html fires login / sign_up client-side."""
    ev = 'signup' if is_new else 'login'
    sep = '&' if '?' in dest else '?'
    return f"{dest}{sep}_auth={ev}&_m={method}"

def _safe_next(target):
    """Guard against open-redirect: only allow same-site relative paths.
    Rejects protocol-relative ('//evil.com') and backslash tricks ('/\\evil')."""
    if target and target.startswith('/') and not target.startswith('//') \
            and not target.startswith('/\\'):
        return target
    return '/'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year cache for static files

@app.after_request
def add_cache_headers(response):
    """Add cache headers for static files"""
    if request.path.startswith('/static/images/'):
        # Cache images for 1 year (they rarely change)
        response.headers['Cache-Control'] = 'public, max-age=31536000'
    elif request.path.startswith('/static/'):
        # Cache other static files (CSS, JS) for 1 week
        response.headers['Cache-Control'] = 'public, max-age=604800'
    return response

# === Locale / i18n ===

TRANSLATIONS = {
    'en': {
        'home': 'Home',
        'products': 'Products',
        'all_products': 'All Products',
        'tags': 'Tags',
        'codex': 'Codex',
        'blog': 'Blog',
        'cart': 'Shopping List',
        'search_placeholder': 'Search products...',
        'add_to_list': 'Add to List',
        'sold_out': 'Sold Out',
        'pre_order': 'Pre-order',
        'sale': 'Sale',
        'new': 'New',
        'in_stock': 'In Stock',
        'show_deprecated': 'Show Discontinued',
        'factions': 'Factions',
        'out_of_stock': 'Out of Stock',
        'quantity': 'Quantity',
        'menu': 'Menu',
        'categories': 'Categories',
        'shop_now': 'Shop Now',
        'new_arrivals': 'New Arrivals',
        'on_sale': 'On Sale Now',
        'featured': 'Featured Products',
        'view_all': 'View All',
        'view_all_new': 'View All New Arrivals',
        'view_all_sale': 'View All Sale Items',
        'view_all_posts': 'View All Posts',
        'currency_symbol': '$',
        'send_for_quote': 'Send List for Quote',
        'clear_list': 'Clear List',
        'added_to_list': 'Added to list!',
        'welcome': "Welcome to Abbey's Toys",
        'tagline': 'PREMIUM ACTION FIGURES',
        'hero_subtitle': 'Premium Action Figures & Collectibles',
        'browse_products': 'Browse Products',
        'related_products': 'Related Products',
        'search_results': 'Search Results',
        'showing_results_for': 'Showing results for',
        'clear_search': 'Clear search',
        'clear_filter': 'Clear filter',
        'browse_all_tags': 'Browse all tags',
        'products_found': 'product(s) found',
        'no_products_search': 'No products found matching',
        'no_products_category': 'No products found in this category.',
        'filters': 'Filters',
        'sort_default': 'Default',
        'sort_price_asc': 'Price ↑',
        'sort_price_desc': 'Price ↓',
        'series': 'Series',
        'scale': 'Scale',
        'size': 'Size',
        'weight': 'Weight',
        'tags_label': 'Tags',
        'sku': 'SKU',
        'expected': 'Expected',
        'your_shopping_list': 'Your Shopping List',
        'list_empty': 'Your shopping list is empty.',
        'total': 'Total',
        'send_your_list': 'Send Your List',
        'preview': 'Preview',
        'copy_to_clipboard': 'Copy to Clipboard',
        'or_send_via': 'Or send via:',
        'email': 'Email',
        'your_name': 'Your Name',
        'your_email': 'Your Email',
        'additional_notes': 'Additional Notes (optional)',
        'send_email': 'Send Email',
        'back': 'Back',
        'remove': 'Remove',
        'recent_blog': 'Recent Blog Posts',
        'read_more': 'Read more →',
        'view_promotion': 'View Promotion →',
        'view_details': 'View Details →',
        'browse_by_tags': 'Browse by Tags',
        'click_tag': 'Click a tag to see all products with that tag',
        'no_tags': 'No tags found.',
        'promotions': 'Promotions',
        'active_promotion': 'Active Promotion',
        'back_to_promotions': '← Back to Promotions',
        'back_to_blog': '← Back to Blog',
        'back_to_codex': 'Back to Codex',
        'codex_entries': 'Codex Entries',
        'contact_price': 'Contact for Price',
        'contact_via_line': 'Contact Us via LINE',
        'copy_list': 'Copy Your Shopping List',
        'copy_list_desc': 'Click the button below to copy your list to clipboard',
        'add_line': 'Add Our LINE Account',
        'add_line_desc': 'Click the button below to add us on LINE',
        'add_friend_line': 'Add Friend on LINE',
        'paste_send': 'Paste & Send',
        'paste_send_desc': 'After adding us, paste the copied list in the chat and send!',
        'back_to_list': '← Back to Shopping List',
        'clear_confirm': 'Are you sure you want to clear your shopping list?',
        'no_image': 'No Image',
        'no_products_yet': 'No products available yet.',
        'tag_label': 'Tag',
        'return_policy': 'Return & Exchange Policy',
        'terms_of_service': 'Terms of Service',
        'shopping_guide': 'Shopping Guide',
    },
    'zhtw': {
        'home': '首頁',
        'products': '商品',
        'all_products': '所有商品',
        'tags': '標籤',
        'codex': 'Codex',
        'blog': '部落格',
        'cart': '購物清單',
        'search_placeholder': '搜尋商品...',
        'add_to_list': '加入清單',
        'sold_out': '已售完',
        'pre_order': '預購',
        'sale': '特價',
        'new': '新品',
        'in_stock': '有庫存',
        'show_deprecated': '顯示絕版商品',
        'factions': '派系',
        'out_of_stock': '缺貨',
        'quantity': '數量',
        'menu': '選單',
        'categories': '分類',
        'shop_now': '立即選購',
        'new_arrivals': '新品上架',
        'on_sale': '特價商品',
        'featured': '精選商品',
        'view_all': '查看全部',
        'view_all_new': '查看所有新品',
        'view_all_sale': '查看所有特價商品',
        'view_all_posts': '查看所有文章',
        'currency_symbol': 'NT$',
        'send_for_quote': '傳送詢價清單',
        'clear_list': '清空清單',
        'added_to_list': '已加入清單！',
        'welcome': '歡迎來到阿北玩具堂',
        'tagline': '精品模型公仔',
        'hero_subtitle': '專賣 JOYTOY、戰鎚40K、歐美系可動玩具｜雙倉庫現貨齊全，出貨快速',
        'browse_products': '瀏覽商品',
        'related_products': '相關商品',
        'search_results': '搜尋結果',
        'showing_results_for': '搜尋結果：',
        'clear_search': '清除搜尋',
        'clear_filter': '清除篩選',
        'browse_all_tags': '瀏覽所有標籤',
        'products_found': '件商品',
        'no_products_search': '找不到符合的商品',
        'no_products_category': '此分類目前沒有商品。',
        'filters': '篩選',
        'sort_default': '預設',
        'sort_price_asc': '價格 ↑',
        'sort_price_desc': '價格 ↓',
        'series': '系列',
        'scale': '比例',
        'size': '尺寸',
        'weight': '重量',
        'tags_label': '標籤',
        'sku': '貨號',
        'expected': '預計到貨',
        'your_shopping_list': '您的購物清單',
        'list_empty': '您的購物清單是空的。',
        'total': '合計',
        'send_your_list': '傳送清單',
        'preview': '預覽',
        'copy_to_clipboard': '複製到剪貼簿',
        'or_send_via': '或透過以下方式傳送：',
        'email': '電子郵件',
        'your_name': '您的姓名',
        'your_email': '您的電子郵件',
        'additional_notes': '備註（選填）',
        'send_email': '傳送郵件',
        'back': '返回',
        'remove': '移除',
        'recent_blog': '最新部落格文章',
        'read_more': '閱讀更多 →',
        'view_promotion': '查看活動 →',
        'view_details': '查看詳情 →',
        'browse_by_tags': '依標籤瀏覽',
        'click_tag': '點擊標籤查看相關商品',
        'no_tags': '目前沒有標籤。',
        'promotions': '促銷活動',
        'active_promotion': '進行中',
        'back_to_promotions': '← 返回促銷活動',
        'back_to_blog': '← 返回部落格',
        'back_to_codex': '返回 Codex',
        'codex_entries': 'Codex 條目',
        'contact_price': '請洽詢價格',
        'contact_via_line': '透過 LINE 聯繫我們',
        'copy_list': '複製您的購物清單',
        'copy_list_desc': '點擊下方按鈕複製清單至剪貼簿',
        'add_line': '加入我們的 LINE 帳號',
        'add_line_desc': '點擊下方按鈕加入我們的 LINE',
        'add_friend_line': '加入好友',
        'paste_send': '貼上並傳送',
        'paste_send_desc': '加入好友後，在聊天室貼上清單並傳送！',
        'back_to_list': '← 返回購物清單',
        'clear_confirm': '確定要清空購物清單嗎？',
        'no_image': '無圖片',
        'no_products_yet': '目前沒有商品。',
        'tag_label': '標籤',
        'return_policy': '退換貨說明',
        'terms_of_service': '服務條款',
        'shopping_guide': '購物須知',
    }
}

def public_route(rule, **options):
    """Register a public route. The site is zh-TW only (abbeystoys.com)."""
    def decorator(f):
        app.add_url_rule(rule, view_func=f, **options)
        return f
    return decorator

@app.before_request
def detect_locale():
    from flask import g
    g.locale = 'zhtw'

_pos_db_stamp = [None]

@app.before_request
def invalidate_on_pos_change():
    """Any POS write bumps the DB file mtime -> drop all caches so the
    site reflects it immediately (realtime)."""
    import posdb as _posdb
    stamp = _posdb.db_mtime()
    if _pos_db_stamp[0] != stamp:
        _pos_db_stamp[0] = stamp
        cache.invalidate()
        html_cache.invalidate()

@app.before_request
def admin_moved_to_pos():
    """Content management now lives in the POS (網站商店 section)."""
    if request.path.startswith('/admin'):
        return redirect('https://warpmonger.johnactionfigure.com/storefront/', code=302)

@app.route('/en', defaults={'rest': ''}, strict_slashes=False)
@app.route('/en/<path:rest>')
def legacy_en_redirect(rest):
    """The English locale was dropped — everything is zh-TW at the root."""
    target = '/' + rest
    if request.query_string:
        target += '?' + request.query_string.decode()
    return redirect(target, code=301)

@app.route('/zhtw', defaults={'rest': ''}, strict_slashes=False)
@app.route('/zhtw/<path:rest>')
def legacy_zhtw_redirect(rest):
    """Old /zhtw/... URLs — zh-TW is the root now."""
    target = '/' + rest
    if request.query_string:
        target += '?' + request.query_string.decode()
    return redirect(target, code=301)

@app.context_processor
def inject_locale():
    """Inject locale-related variables into all templates"""
    if request.path.startswith('/admin') or request.path.startswith('/api'):
        return {}
    from flask import g
    locale = getattr(g, 'locale', 'en')
    is_zhtw = locale == 'zhtw'
    return {
        'locale': locale,
        'is_zhtw': is_zhtw,
        't': TRANSLATIONS.get(locale, TRANSLATIONS['zhtw']),
        'url_prefix': '' if is_zhtw else '/en',
    }

@app.context_processor
def inject_seo_config():
    """Site-level SEO config from env: GSC verification token + social URLs
    (used in Organization schema sameAs). Both optional."""
    if request.path.startswith('/admin') or request.path.startswith('/api'):
        return {}
    social = [s.strip() for s in os.environ.get('SITE_SOCIAL_LINKS', '').split(',') if s.strip()]
    return {
        'google_site_verification': os.environ.get('GOOGLE_SITE_VERIFICATION', ''),
        'social_links': social,
        # GA4 measurement ID — env-overridable so switching properties needs no
        # code change. Default keeps the current property. Set '' to disable.
        'ga4_id': os.environ.get('GA4_MEASUREMENT_ID', 'G-HYSSEZVZNK'),
    }

@app.context_processor
def inject_canonical():
    """Canonical URL for <link rel=canonical>. Defaults to the full request URL
    (self-referencing, unchanged). The product listing fragments into many
    sort/filter/search combinations of the SAME products, so we canonicalize it
    to the clean path keeping only the facets that define a distinct,
    uniquely-titled page — category and tag. Everything else (sort, search,
    pre_order/on_sale/new_arrival/in_stock) is dropped so those variants
    consolidate onto the canonical instead of diluting indexing."""
    if request.path.startswith('/admin') or request.path.startswith('/api'):
        return {}
    canonical = request.url
    if request.endpoint == 'products_page':
        from urllib.parse import urlencode
        kept = [(k, request.args[k]) for k in ('category', 'tag')
                if request.args.get(k)]
        canonical = request.base_url + ('?' + urlencode(kept) if kept else '')
    return {'canonical_url': canonical}

@app.context_processor
def inject_nav_categories():
    """Inject categories into all templates for navigation dropdown"""
    from functools import lru_cache
    # Only inject for public pages (not admin)
    if request.path.startswith('/admin') or request.path.startswith('/api'):
        return {}
    return {'nav_categories': get_categories()}

# Custom Jinja2 filter for NTD price formatting
@app.template_filter('ntd')
def format_ntd(value):
    """Format number as NTD integer with comma separators"""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "0"

@app.template_filter('twtime')
def format_twtime(value, fmt='%Y-%m-%d %H:%M'):
    """DB timestamp (UTC) -> Taiwan time (UTC+8) for display."""
    if not value:
        return ''
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S')
        return (dt + timedelta(hours=8)).strftime(fmt)
    except Exception:
        return str(value)[:16]

# Custom Jinja2 filter for formatting month
@app.template_filter('format_month')
def format_month(date_str):
    """Convert YYYY-MM or YYYY-MM-DD to Month Year format"""
    if not date_str:
        return ''
    try:
        # Split and take first two parts (year and month)
        parts = date_str.split('-')
        year = parts[0]
        month = parts[1]
        months = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December']
        return f"{months[int(month)]} {year}"
    except:
        return date_str

# Paths
CONTENT_DIR = os.path.join(os.path.dirname(__file__), 'content')
PRODUCTS_DIR = os.path.join(CONTENT_DIR, 'products')
BLOG_DIR = os.path.join(CONTENT_DIR, 'blog')
PROMOTIONS_DIR = os.path.join(CONTENT_DIR, 'promotions')
CATEGORIES_DIR = os.path.join(CONTENT_DIR, 'categories')
CODEX_DIR = os.path.join(CONTENT_DIR, 'codex')
PAGES_DIR = os.path.join(CONTENT_DIR, 'pages')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
FEATURED_TAGS_FILE = os.path.join(DATA_DIR, 'featured_tags.json')
FEATURED_PRODUCTS_FILE = os.path.join(DATA_DIR, 'featured_products.json')
FEATURED_TAGS_ICONS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'images', 'featured_tags')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov', 'avi', 'webm'}

# Ensure directories exist
os.makedirs(PRODUCTS_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)
os.makedirs(PROMOTIONS_DIR, exist_ok=True)
os.makedirs(CATEGORIES_DIR, exist_ok=True)
os.makedirs(CODEX_DIR, exist_ok=True)
os.makedirs(PAGES_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(FEATURED_TAGS_ICONS_DIR, exist_ok=True)

# ===== Utility Functions =====

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_thumbnail(image_path, thumbnail_path, size=(300, 300)):
    """Create thumbnail from image"""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumbnail_path, quality=85, optimize=True)
        return True
    except Exception as e:
        print(f"Error creating thumbnail: {e}")
        return False

def slugify(text):
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text

def parse_frontmatter(content):
    """Parse YAML-like frontmatter from markdown file"""
    if not content.startswith('---'):
        return {}, content

    try:
        parts = content.split('---', 2)
        if len(parts) < 3:
            return {}, content

        frontmatter_text = parts[1].strip()
        body = parts[2].strip()

        # Simple key: value parser
        frontmatter = {}
        for line in frontmatter_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()

                # Handle lists (e.g., images: ["a.jpg", "b.jpg"])
                if value.startswith('[') and value.endswith(']'):
                    value = json.loads(value)
                # Handle booleans
                elif value.lower() in ['true', 'false']:
                    value = value.lower() == 'true'
                # Handle numbers
                elif value.replace('.', '').isdigit():
                    value = float(value) if '.' in value else int(value)

                frontmatter[key] = value

        return frontmatter, body
    except Exception as e:
        print(f"Error parsing frontmatter: {e}")
        return {}, content

def create_frontmatter(data, body):
    """Create markdown file with frontmatter"""
    lines = ['---']
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f'{key}: {json.dumps(value)}')
        elif isinstance(value, bool):
            lines.append(f'{key}: {str(value).lower()}')
        else:
            lines.append(f'{key}: {value}')
    lines.append('---')
    lines.append('')
    lines.append(body)
    return '\n'.join(lines)

# ===== Product Functions =====

def get_categories():
    """Get list of product categories from categories directory"""
    # Check cache first
    cached = cache.get('categories')
    if cached is not None:
        return cached

    categories = []

    if not os.path.exists(CATEGORIES_DIR):
        return []

    for category_slug in os.listdir(CATEGORIES_DIR):
        category_path = os.path.join(CATEGORIES_DIR, category_slug)
        if not os.path.isdir(category_path) or category_slug.startswith('.'):
            continue

        category_file = os.path.join(category_path, 'category.md')
        if not os.path.exists(category_file):
            continue

        with open(category_file, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        categories.append({
            'slug': category_slug,
            'name': frontmatter.get('name', category_slug),
            'description': body,
            'order_weight': frontmatter.get('order_weight', 0),
            'icon': frontmatter.get('icon', '')
        })

    # Sort by order_weight (descending), then by name (ascending)
    categories.sort(key=lambda c: (-c['order_weight'], c['name'].lower()))

    # Cache before returning
    cache.set('categories', categories)
    return categories

def get_category(slug):
    """Get single category by slug"""
    category_path = os.path.join(CATEGORIES_DIR, slug)
    category_file = os.path.join(category_path, 'category.md')

    if not os.path.exists(category_file):
        return None

    with open(category_file, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)

    return {
        'slug': slug,
        'name': frontmatter.get('name', slug),
        'description': body,
        'order_weight': frontmatter.get('order_weight', 0),
        'icon': frontmatter.get('icon', '')
    }

def save_category(slug, data):
    """Save category to file"""
    category_path = os.path.join(CATEGORIES_DIR, slug)
    os.makedirs(category_path, exist_ok=True)

    # Create images directory
    images_dir = os.path.join(category_path, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # Prepare frontmatter
    frontmatter_data = {
        'name': data.get('name', ''),
        'order_weight': data.get('order_weight', 0),
        'icon': data.get('icon', '')
    }

    # Save category.md
    category_file = os.path.join(category_path, 'category.md')
    content = create_frontmatter(frontmatter_data, data.get('description', ''))
    with open(category_file, 'w', encoding='utf-8') as f:
        f.write(content)

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()
    return True

def delete_category(slug):
    """Delete category"""
    import shutil
    category_path = os.path.join(CATEGORIES_DIR, slug)

    if os.path.exists(category_path):
        shutil.rmtree(category_path)
        # Invalidate cache
        cache.invalidate()
        html_cache.invalidate()
        return True
    return False

def get_products(category=None, search=None):
    """Get all products or products in a category, optionally filtered by search query"""
    # Check cache first (only for non-search queries, search will filter cached results)
    cache_key = f"products:{category or 'all'}"

    if not search:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    else:
        # For search, get cached full/category list first, then filter
        cached = cache.get(cache_key)
        if cached is not None:
            # Filter cached products by search
            search_lower = search.lower()
            filtered = []
            for product in cached:
                title_match = search_lower in product['title'].lower()
                cn_name_match = search_lower in product['cn_name'].lower() if product['cn_name'] else False
                zhtw_name_match = search_lower in product['zhtw_name'].lower() if product['zhtw_name'] else False
                id_match = search_lower in str(product['id']).lower() if product['id'] else False
                sku_match = search_lower in str(product['sku']).lower() if product['sku'] else False
                if title_match or cn_name_match or zhtw_name_match or id_match or sku_match:
                    filtered.append(product)
            return filtered

    products = []

    # Get categories (either all or just the specified one)
    if category:
        categories = [category]
    else:
        # Get all category slugs
        categories = [cat['slug'] for cat in get_categories()]

    for cat_slug in categories:
        cat_path = os.path.join(PRODUCTS_DIR, cat_slug)
        if not os.path.exists(cat_path):
            continue

        for product_slug in os.listdir(cat_path):
            product_path = os.path.join(cat_path, product_slug)
            if not os.path.isdir(product_path):
                continue

            product_file = os.path.join(product_path, 'product.md')
            if not os.path.exists(product_file):
                continue

            with open(product_file, 'r', encoding='utf-8') as f:
                content = f.read()

            frontmatter, body = parse_frontmatter(content)

            # Read tags if exists
            tags_file = os.path.join(product_path, 'tags.txt')
            tags = []
            if os.path.exists(tags_file):
                with open(tags_file, 'r', encoding='utf-8') as f:
                    tags = [line.strip() for line in f if line.strip()]

            product = {
                'slug': product_slug,
                'category': cat_slug,
                'title': frontmatter.get('title', product_slug),
                'price': frontmatter.get('price', 0),
                'description': body,
                'images': frontmatter.get('images', []),
                'in_stock': frontmatter.get('in_stock', True),
                'sku': frontmatter.get('sku', ''),
                'tags': tags,
                'is_pre_order': frontmatter.get('is_pre_order', False),
                'available_date': frontmatter.get('available_date', ''),
                'is_on_sale': frontmatter.get('is_on_sale', False),
                'sale_price': frontmatter.get('sale_price', 0),
                'is_new_arrival': frontmatter.get('is_new_arrival', False),
                # Additional fields from CSV
                'id': frontmatter.get('id', ''),
                'cn_name': frontmatter.get('cn_name', ''),
                'zhtw_name': frontmatter.get('zhtw_name', ''),
                'series': frontmatter.get('series', ''),
                'scale': frontmatter.get('scale', ''),
                'size': frontmatter.get('size', ''),
                'weight': frontmatter.get('weight', ''),
                # Backend-only pricing fields
                'zhtw_price': frontmatter.get('zhtw_price', 0),
                'cost': frontmatter.get('cost', 0),
                'final_price': frontmatter.get('final_price', 0),
                'cost_tw': frontmatter.get('cost_tw', 0),
                # Ordering
                'order_weight': frontmatter.get('order_weight', 0),
                # Grouping
                'group': frontmatter.get('group', '')
            }

            # Apply search filter if provided
            if search:
                search_lower = search.lower()
                title_match = search_lower in product['title'].lower()
                cn_name_match = search_lower in product['cn_name'].lower() if product['cn_name'] else False
                zhtw_name_match = search_lower in product['zhtw_name'].lower() if product['zhtw_name'] else False
                id_match = search_lower in str(product['id']).lower() if product['id'] else False
                sku_match = search_lower in str(product['sku']).lower() if product['sku'] else False

                if not (title_match or cn_name_match or zhtw_name_match or id_match or sku_match):
                    continue

            products.append(product)

    # Sort products: first by order_weight (descending), then by title (ascending)
    products.sort(key=lambda p: (-p['order_weight'], p['title'].lower()))

    # Cache before returning (only for non-search queries)
    if not search:
        cache.set(cache_key, products)

    return products

def get_all_tags():
    """Get all unique tags with product counts"""
    # Check cache first
    cached = cache.get('all_tags')
    if cached is not None:
        return cached

    products = get_products()
    tag_counts = {}

    for product in products:
        for tag in product.get('tags', []):
            if tag in tag_counts:
                tag_counts[tag] += 1
            else:
                tag_counts[tag] = 1

    # Convert to list of dicts and sort by count (descending), then name
    tags = [{'name': name, 'count': count} for name, count in tag_counts.items()]
    tags.sort(key=lambda t: (-t['count'], t['name'].lower()))

    # Cache before returning
    cache.set('all_tags', tags)
    return tags

def get_featured_tags():
    """Get featured tags for homepage display"""
    cached = cache.get('featured_tags')
    if cached is not None:
        return cached

    if not os.path.exists(FEATURED_TAGS_FILE):
        return []

    try:
        with open(FEATURED_TAGS_FILE, 'r', encoding='utf-8') as f:
            tags = json.load(f)
        # Sort by order_weight (descending)
        tags.sort(key=lambda t: -t.get('order_weight', 0))
        cache.set('featured_tags', tags)
        return tags
    except:
        return []

def save_featured_tags(tags):
    """Save featured tags to file"""
    with open(FEATURED_TAGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tags, f, indent=2, ensure_ascii=False)
    cache.invalidate('featured_tags')
    html_cache.invalidate()

def get_featured_products_refs():
    """Get list of featured product references (category/slug)"""
    if not os.path.exists(FEATURED_PRODUCTS_FILE):
        return []

    try:
        with open(FEATURED_PRODUCTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_featured_products_refs(refs):
    """Save featured product references to file"""
    with open(FEATURED_PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(refs, f, indent=2, ensure_ascii=False)
    html_cache.invalidate()

def get_featured_products_for_homepage():
    """Get featured products with full details for homepage"""
    refs = get_featured_products_refs()
    if not refs:
        return []

    all_products = get_products()
    featured = []

    for ref in refs:
        for product in all_products:
            if f"{product['category']}/{product['slug']}" == ref:
                featured.append(product)
                break

    return featured

def get_product(category, slug):
    """Get single product by category slug and product slug"""
    product_path = os.path.join(PRODUCTS_DIR, category, slug)
    product_file = os.path.join(product_path, 'product.md')

    if not os.path.exists(product_file):
        return None

    with open(product_file, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)

    # Read tags
    tags_file = os.path.join(product_path, 'tags.txt')
    tags = []
    if os.path.exists(tags_file):
        with open(tags_file, 'r', encoding='utf-8') as f:
            tags = [line.strip() for line in f if line.strip()]

    return {
        'slug': slug,
        'category': category,
        'title': frontmatter.get('title', slug),
        'price': frontmatter.get('price', 0),
        'description': body,
        'images': frontmatter.get('images', []),
        'in_stock': frontmatter.get('in_stock', True),
        'sku': frontmatter.get('sku', ''),
        'tags': tags,
        'is_pre_order': frontmatter.get('is_pre_order', False),
        'available_date': frontmatter.get('available_date', ''),
        'is_on_sale': frontmatter.get('is_on_sale', False),
        'sale_price': frontmatter.get('sale_price', 0),
        'is_new_arrival': frontmatter.get('is_new_arrival', False),
        # Additional fields from CSV
        'id': frontmatter.get('id', ''),
        'cn_name': frontmatter.get('cn_name', ''),
        'zhtw_name': frontmatter.get('zhtw_name', ''),
        'series': frontmatter.get('series', ''),
        'scale': frontmatter.get('scale', ''),
        'size': frontmatter.get('size', ''),
        'weight': frontmatter.get('weight', ''),
        # Backend-only pricing fields
        'zhtw_price': frontmatter.get('zhtw_price', 0),
        'cost': frontmatter.get('cost', 0),
        'final_price': frontmatter.get('final_price', 0),
        'cost_tw': frontmatter.get('cost_tw', 0),
        # Ordering
        'order_weight': frontmatter.get('order_weight', 0),
        # Grouping
        'group': frontmatter.get('group', '')
    }

def save_product(category, slug, data):
    """Save product to file"""
    product_path = os.path.join(PRODUCTS_DIR, category, slug)
    os.makedirs(product_path, exist_ok=True)

    # Create images directory
    images_dir = os.path.join(product_path, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # Prepare frontmatter
    frontmatter_data = {
        'title': data.get('title', ''),
        'price': data.get('price', 0),
        'sku': data.get('sku', ''),
        'in_stock': data.get('in_stock', True),
        'images': data.get('images', []),
        'is_pre_order': data.get('is_pre_order', False),
        'available_date': data.get('available_date', ''),
        'is_on_sale': data.get('is_on_sale', False),
        'sale_price': data.get('sale_price', 0),
        'is_new_arrival': data.get('is_new_arrival', False),
        # Additional fields from CSV
        'id': data.get('id', ''),
        'cn_name': data.get('cn_name', ''),
        'zhtw_name': data.get('zhtw_name', ''),
        'series': data.get('series', ''),
        'scale': data.get('scale', ''),
        'size': data.get('size', ''),
        'weight': data.get('weight', ''),
        # Backend-only pricing fields
        'zhtw_price': data.get('zhtw_price', 0),
        'cost': data.get('cost', 0),
        'final_price': data.get('final_price', 0),
        'cost_tw': data.get('cost_tw', 0),
        # Ordering
        'order_weight': data.get('order_weight', 0),
        # Grouping
        'group': data.get('group', '')
    }

    # Save product.md
    product_file = os.path.join(product_path, 'product.md')
    content = create_frontmatter(frontmatter_data, data.get('description', ''))
    with open(product_file, 'w', encoding='utf-8') as f:
        f.write(content)

    # Save tags
    if 'tags' in data:
        tags_file = os.path.join(product_path, 'tags.txt')
        with open(tags_file, 'w', encoding='utf-8') as f:
            for tag in data['tags']:
                f.write(f"{tag}\n")

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()
    return True

# ===== Blog Functions =====

def get_blog_posts():
    """Get all blog posts"""
    posts = []

    if not os.path.exists(BLOG_DIR):
        return posts

    for filename in os.listdir(BLOG_DIR):
        if not filename.endswith('.md'):
            continue

        filepath = os.path.join(BLOG_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        slug = filename[:-3]  # Remove .md
        posts.append({
            'slug': slug,
            'title': frontmatter.get('title', slug),
            'date': frontmatter.get('date', ''),
            'author': frontmatter.get('author', ''),
            'excerpt': frontmatter.get('excerpt', body[:200]),
            'content': body,
            'tags': frontmatter.get('tags', [])
        })

    # Sort by date (newest first)
    posts.sort(key=lambda x: x['date'], reverse=True)
    return posts

def get_blog_post(slug):
    """Get single blog post"""
    filepath = os.path.join(BLOG_DIR, f"{slug}.md")

    if not os.path.exists(filepath):
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)

    return {
        'slug': slug,
        'title': frontmatter.get('title', slug),
        'date': frontmatter.get('date', ''),
        'author': frontmatter.get('author', ''),
        'content': body,
        'tags': frontmatter.get('tags', [])
    }

def save_blog_post(slug, data):
    """Save blog post to file"""
    frontmatter_data = {
        'title': data.get('title', ''),
        'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
        'author': data.get('author', ''),
        'excerpt': data.get('excerpt', ''),
        'tags': data.get('tags', [])
    }

    filepath = os.path.join(BLOG_DIR, f"{slug}.md")
    content = create_frontmatter(frontmatter_data, data.get('content', ''))

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return True

# ===== Promotion Functions =====

def get_promotion_banner(slug):
    """Get banner image URL for a promotion from static folder"""
    static_promo_dir = os.path.join(app.static_folder, 'images', 'promotions', slug)
    if not os.path.exists(static_promo_dir):
        return None

    # Look for banner with any extension
    for filename in os.listdir(static_promo_dir):
        if filename.startswith('banner.'):
            return f"/static/images/promotions/{slug}/{filename}"
    return None

def get_promotions():
    """Get all promotions"""
    promotions = []

    if not os.path.exists(PROMOTIONS_DIR):
        return promotions

    for slug in os.listdir(PROMOTIONS_DIR):
        promo_dir = os.path.join(PROMOTIONS_DIR, slug)
        if not os.path.isdir(promo_dir):
            continue

        promo_file = os.path.join(promo_dir, 'promotion.md')
        if not os.path.exists(promo_file):
            continue

        with open(promo_file, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        # Get banner image from static folder
        banner = get_promotion_banner(slug)

        promotions.append({
            'slug': slug,
            'title': frontmatter.get('title', slug),
            'date': frontmatter.get('date', ''),
            'excerpt': frontmatter.get('excerpt', body[:200]),
            'content': body,
            'products': frontmatter.get('products', []),
            'active': frontmatter.get('active', False),
            'banner': banner
        })

    # Sort by date (newest first)
    promotions.sort(key=lambda x: x['date'], reverse=True)
    return promotions

def get_promotion(slug):
    """Get single promotion"""
    promo_dir = os.path.join(PROMOTIONS_DIR, slug)
    promo_file = os.path.join(promo_dir, 'promotion.md')

    if not os.path.exists(promo_file):
        return None

    with open(promo_file, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)

    # Get banner image from static folder
    banner = get_promotion_banner(slug)

    return {
        'slug': slug,
        'title': frontmatter.get('title', slug),
        'date': frontmatter.get('date', ''),
        'excerpt': frontmatter.get('excerpt', ''),
        'content': body,
        'products': frontmatter.get('products', []),
        'active': frontmatter.get('active', False),
        'banner': banner
    }

def save_promotion(slug, data):
    """Save promotion to file"""
    promo_dir = os.path.join(PROMOTIONS_DIR, slug)
    os.makedirs(promo_dir, exist_ok=True)

    frontmatter_data = {
        'title': data.get('title', ''),
        'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
        'excerpt': data.get('excerpt', ''),
        'products': data.get('products', []),
        'active': data.get('active', False)
    }

    promo_file = os.path.join(promo_dir, 'promotion.md')
    content = create_frontmatter(frontmatter_data, data.get('content', ''))

    with open(promo_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return True

def get_active_promotion():
    """Get the currently active promotion for homepage banner"""
    promotions = get_promotions()
    for promo in promotions:
        if promo.get('active') and promo.get('banner'):
            return promo
    return None

# ===== Codex Functions =====

def get_codex_entries():
    """Get all codex entries"""
    # Check cache first
    cached = cache.get('codex_entries')
    if cached is not None:
        return cached

    entries = []

    if not os.path.exists(CODEX_DIR):
        return entries

    for filename in os.listdir(CODEX_DIR):
        if not filename.endswith('.md'):
            continue

        filepath = os.path.join(CODEX_DIR, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, body = parse_frontmatter(content)

        slug = filename[:-3]  # Remove .md
        entries.append({
            'slug': slug,
            'title': frontmatter.get('title', slug),
            'aliases': frontmatter.get('aliases', []),
            'content': body,
            'excerpt': body[:200] + '...' if len(body) > 200 else body
        })

    # Sort alphabetically by title
    entries.sort(key=lambda x: x['title'].lower())

    # Cache before returning
    cache.set('codex_entries', entries)
    return entries

def get_codex_entry(slug):
    """Get single codex entry by slug"""
    filepath = os.path.join(CODEX_DIR, f"{slug}.md")

    if not os.path.exists(filepath):
        return None

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)

    return {
        'slug': slug,
        'title': frontmatter.get('title', slug),
        'aliases': frontmatter.get('aliases', []),
        'content': body
    }

def save_codex_entry(slug, data):
    """Save codex entry to file"""
    # Prepare frontmatter
    frontmatter_data = {
        'title': data.get('title', ''),
        'aliases': data.get('aliases', [])
    }

    # Save codex entry .md file
    filepath = os.path.join(CODEX_DIR, f"{slug}.md")
    content = create_frontmatter(frontmatter_data, data.get('content', ''))

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()
    return True

def build_codex_lookup():
    """Build a lookup dictionary for codex terms (title and aliases -> slug)"""
    # Check cache first
    cached = cache.get('codex_lookup')
    if cached is not None:
        return cached

    lookup = {}
    entries = get_codex_entries()

    for entry in entries:
        # Map title to slug
        lookup[entry['title'].lower()] = entry['slug']
        # Map aliases to slug
        for alias in entry.get('aliases', []):
            lookup[alias.lower()] = entry['slug']

    # Cache before returning
    cache.set('codex_lookup', lookup)
    return lookup

def build_codex_zhtw():
    """slug -> zh-TW display name, for bilingual 中文（English）crosslinks."""
    cached = cache.get('codex_zhtw')
    if cached is not None:
        return cached
    zhtw = {e['slug']: (e.get('title_zhtw') or '').strip()
            for e in get_codex_entries()}
    cache.set('codex_zhtw', zhtw)
    return zhtw

def process_codex_links(text):
    """Convert [[term]] syntax to codex links"""
    from flask import g
    locale = getattr(g, 'locale', 'zhtw')
    prefix = '' if locale == 'zhtw' else '/en'
    codex_lookup = build_codex_lookup()
    codex_zhtw = build_codex_zhtw()

    def replace_codex_link(match):
        term = match.group(1)
        # support [[target|display]] — link on target, show display text
        target, sep, display = term.partition('|')
        display = (display or target).strip()
        target = target.strip()

        slug = codex_lookup.get(target.lower())
        if slug:
            # Bilingual label 中文（English）on the default (zh-TW) site, when we
            # have a Chinese name and the display text is still English. Keep the
            # href/slug identical so existing links (and the quiz) never break.
            zh = codex_zhtw.get(slug, '')
            label = display
            if (locale == 'zhtw' and zh and zh != display
                    and not re.search(r'[一-鿿]', display)):
                label = f'{zh}（{display}）'
            return (f'<a href="{prefix}/codex/{slug}" class="codex-term" '
                    f'data-codex="{slug}">{label}</a>')
        # Term not found in codex, just return the text without brackets
        return display

    # Match [[anything]]
    pattern = r'\[\[([^\]]+)\]\]'
    return re.sub(pattern, replace_codex_link, text)

# ===== Routes - Public =====

@public_route('/')
def home():
    """Homepage"""
    all_products = get_products()

    # category showcase: each category with product count + a cover image
    category_cards = []
    for cat in get_categories():
        cat_products = [p for p in all_products if p['category'] == cat['slug']]
        if not cat_products:
            continue
        with_img = next((p for p in cat_products if p['images']), None)
        cover = None
        if with_img:
            stem = with_img['images'][0].rsplit('.', 1)[0]
            cover = f"/static/images/products/{with_img['category']}/{with_img['slug']}/thumb_{stem}.jpg"
        category_cards.append({
            'slug': cat['slug'], 'name': cat['name'],
            'count': len(cat_products), 'cover': cover,
            'weight': cat.get('order_weight', 0),
        })
    category_cards.sort(key=lambda c: (-c['weight'], -c['count']))

    # Get featured products (manually selected) or fallback to first 8
    featured = get_featured_products_for_homepage()
    if not featured:
        featured = all_products[:8]

    # Get special sections
    new_arrivals = [p for p in all_products if p.get('is_new_arrival', False)][:4]

    posts = get_blog_posts()[:3]  # Recent posts
    featured_tags = get_featured_tags()
    active_promo = get_active_promotion()
    return render_template('public/home.html',
                         products=featured,
                         category_cards=category_cards,
                         new_arrivals=new_arrivals,
                         posts=posts,
                         featured_tags=featured_tags,
                         active_promo=active_promo)

@public_route('/tags')
def tags_page():
    """Tag cloud page"""
    tags = get_all_tags()
    return render_template('public/tags.html', tags=tags)

@public_route('/products')
def products_page():
    """Product catalog page"""
    category = request.args.get('category')
    tag = request.args.get('tag')
    search = request.args.get('search', '').strip()
    show_pre_order = request.args.get('pre_order') == 'true'
    show_new_arrival = request.args.get('new_arrival') == 'true'
    show_in_stock = request.args.get('in_stock') == 'true'
    show_deprecated = request.args.get('deprecated') == 'true'
    sort_by = request.args.get('sort', 'default')  # default, price_asc, price_desc

    # Check HTML cache for simple category pages (no search/tag/filters)
    from flask import g
    locale = getattr(g, 'locale', 'en')
    is_simple_page = not tag and not search and not show_pre_order and not show_new_arrival and not show_in_stock and not show_deprecated and sort_by == 'default'
    cache_key = f"html_products_{locale}_{category or 'all'}"

    # The rendered page embeds the header (avatar/account links) for the current
    # member, so only anonymous visitors — who all share one identical header —
    # may read or write this shared cache. Logged-in users always render fresh.
    is_anon = not current_member()

    if is_simple_page and is_anon:
        cached_html = html_cache.get(cache_key)
        if cached_html:
            return cached_html

    # Get products with search filter
    products = get_products(category, search if search else None)

    # Faction sub-nav: which curated faction tags appear in THIS category
    # (computed category-wide, independent of the active tag, so you can switch
    # factions). Only on category pages.
    faction_nav = []
    if category:
        import posdb as _posdb
        faction_set = set(_posdb.get_faction_tags())
        if faction_set:
            counts = {}
            for p in get_products(category):
                if not show_deprecated and p.get('availability') == 'inquiry':
                    continue
                for t in p.get('tags', []):
                    if t in faction_set:
                        counts[t] = counts.get(t, 0) + 1
            faction_nav = sorted(({'tag': t, 'count': n} for t, n in counts.items()),
                                 key=lambda x: -x['count'])

    # Filter by tag if specified
    if tag:
        products = [p for p in products if tag in p.get('tags', [])]

    # Filter by pre-order if specified
    if show_pre_order:
        products = [p for p in products if p.get('is_pre_order', False)]

    # Filter by new arrival if specified
    if show_new_arrival:
        products = [p for p in products if p.get('is_new_arrival', False)]

    # Filter by in stock if specified
    if show_in_stock:
        products = [p for p in products if p.get('in_stock', True)]

    # Hide 絕版/詢價 (inquiry) items by default; the 顯示絕版商品 filter shows them
    if not show_deprecated:
        products = [p for p in products if p.get('availability') != 'inquiry']

    # Sort products based on sort_by parameter
    if sort_by == 'price_asc':
        # Sort by price low to high (use sale_price if on sale)
        products.sort(key=lambda p: p.get('sale_price', 0) if p.get('is_on_sale') and p.get('sale_price', 0) > 0 else p.get('price', 0))
    elif sort_by == 'price_desc':
        # Sort by price high to low (use sale_price if on sale)
        products.sort(key=lambda p: p.get('sale_price', 0) if p.get('is_on_sale') and p.get('sale_price', 0) > 0 else p.get('price', 0), reverse=True)
    else:
        # Default: Sort by group for visual clustering (grouped products together, then by order_weight and title)
        products.sort(key=lambda p: (p.get('group') or 'zzz', -p.get('order_weight', 0), p['title'].lower()))

    categories = get_categories()

    # Get category name for display
    current_category_name = None
    if category:
        cat_obj = get_category(category)
        if cat_obj:
            current_category_name = cat_obj['name']

    html = render_template('public/products.html',
                         products=products,
                         categories=categories,
                         current_category=category,
                         current_category_name=current_category_name,
                         current_tag=tag,
                         current_search=search,
                         show_pre_order=show_pre_order,
                         show_new_arrival=show_new_arrival,
                         show_in_stock=show_in_stock,
                         show_deprecated=show_deprecated,
                         faction_nav=faction_nav,
                         current_sort=sort_by)

    # Cache simple pages (anonymous only — see is_anon note above)
    if is_simple_page and is_anon:
        html_cache.set(cache_key, html)

    return html

@public_route('/products/<category>/<slug>')
def product_detail(category, slug):
    """Product detail page"""
    product = get_product(category, slug)
    if not product:
        return "Product not found", 404

    # Pick the description body by locale: zh-TW on the default site, English
    # on /en (each falls back to the other so a missing translation still shows
    # something). Process codex links first, then convert markdown to HTML.
    from flask import g
    _zh = product.get('description_zhtw') or ''
    _en = product.get('description_enus') or ''
    if getattr(g, 'locale', 'zhtw') == 'zhtw':
        _desc = _zh or _en or product.get('description') or ''
    else:
        _desc = _en or _zh or product.get('description') or ''
    description_with_codex = process_codex_links(_desc)
    product['description_html'] = markdown.markdown(description_with_codex)
    # Plain, crosslink-stripped text for meta/schema (og:description, JSON-LD):
    # [[Term]] / [[target|Display]] -> the readable name, newlines -> spaces.
    import re as _re_meta
    _plain = _re_meta.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]',
                          lambda m: m.group(2) or m.group(1), _desc)
    product['description_plain'] = " ".join(_plain.split())

    # Get category name for display
    cat_obj = get_category(category)
    category_name = cat_obj['name'] if cat_obj else category

    # Build related products list with priority: same group -> matched tags -> same category
    current_tags = set(product.get('tags', []))
    current_group = product.get('group', '')
    all_products = get_products()
    category_products = [p for p in all_products if p['category'] == category and p['slug'] != slug]

    # Separate into tiers
    group_products = []
    tag_products = []
    other_products = []

    for p in category_products:
        if current_group and p.get('group') == current_group:
            group_products.append(p)
        elif current_tags and set(p.get('tags', [])) & current_tags:
            # Count matching tags for sorting
            match_count = len(set(p.get('tags', [])) & current_tags)
            tag_products.append((match_count, p))
        else:
            other_products.append(p)

    # Sort tag_products by match count (descending)
    tag_products.sort(key=lambda x: -x[0])
    tag_products = [p for _, p in tag_products]

    # Combine: group first, then tag matches, then rest of category (max 16 items)
    related = (group_products + tag_products + other_products)[:16]

    # Reviews (商品評價): approved reviews + aggregate for this product. Keyed on
    # product.id, matching the wishlist/notify convention. The logged-in
    # member's own review (any status) is passed so the form can prefill/edit.
    review_sku = product.get('id') or product.get('sku')
    reviews = memberdb.approved_reviews(review_sku) if review_sku else []
    review_stats = memberdb.review_stats(review_sku) if review_sku else {'count': 0, 'average': None}
    _m = current_member()
    my_review = memberdb.get_review(_m['id'], review_sku) if (_m and review_sku) else None

    return render_template('public/product-detail.html',
                         product=product,
                         category_name=category_name,
                         related=related,
                         reviews=reviews,
                         review_stats=review_stats,
                         review_sku=review_sku,
                         my_review=my_review,
                         review_photo_url=_review_photo_url)

@public_route('/blog')
def blog_page():
    """Blog listing page"""
    posts = get_blog_posts()
    return render_template('public/blog.html', posts=posts)

@public_route('/blog/<slug>')
def blog_post_page(slug):
    """Blog post detail page"""
    post = get_blog_post(slug)
    if not post:
        return "Post not found", 404

    # Convert markdown to HTML
    post['content_html'] = markdown.markdown(post['content'])

    return render_template('public/blog-post.html', post=post)

@public_route('/promotions')
def promotions_page():
    """Promotions listing page"""
    promotions = get_promotions()
    return render_template('public/promotions.html', promotions=promotions)

@public_route('/promotions/<slug>')
def promotion_page(slug):
    """Promotion detail page"""
    promo = get_promotion(slug)
    if not promo:
        return "Promotion not found", 404

    # Convert markdown to HTML
    promo['content_html'] = markdown.markdown(promo['content'])

    # Get product details for the promotion
    promo_products = []
    all_products = get_products()
    for product_ref in promo.get('products', []):
        # product_ref format: "category/slug"
        for product in all_products:
            if f"{product['category']}/{product['slug']}" == product_ref:
                promo_products.append(product)
                break

    return render_template('public/promotion.html', promotion=promo, products=promo_products)

@public_route('/codex')
def codex_page():
    """Codex listing page"""
    entries = get_codex_entries()
    return render_template('public/codex.html', entries=entries)

@public_route('/codex/<slug>')
def codex_entry_page(slug):
    """Codex entry detail page"""
    entry = get_codex_entry(slug)
    if not entry:
        return "Codex entry not found", 404

    # zh-TW body by default, English on /en (fall back to whichever exists).
    from flask import g
    _zh = entry.get('content') or ''
    _en = entry.get('content_enus') or ''
    if getattr(g, 'locale', 'zhtw') == 'zhtw':
        _body = _zh or _en
    else:
        _body = _en or _zh
    # Process [[crosslinks]] in the body first, then markdown -> HTML (same as
    # product descriptions; without this the body shows literal [[Term]]).
    entry['content_html'] = markdown.markdown(process_codex_links(_body))
    # Plain, crosslink-stripped text for the meta description.
    entry['content_plain'] = " ".join(
        re.sub(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]',
               lambda m: m.group(2) or m.group(1), _body).split())

    # Related products, so lore pages funnel visitors to buyable products:
    #  - tag match on the codex title/aliases (faction codexes), OR
    #  - the codex title appearing in the product name (character codexes, e.g.
    #    the Alpharius entry -> the Alpharius figure). In-stock first.
    terms = {entry['title'].strip().lower()}
    terms |= {str(a).strip().lower() for a in entry.get('aliases', []) if a}
    name_term = entry['title'].strip().lower()

    def _related(p):
        tags = {str(t).strip().lower() for t in (p.get('tags') or [])}
        if terms & tags:
            return True
        name = f"{p.get('title') or ''} {p.get('zhtw_name') or ''}".lower()
        return len(name_term) >= 4 and name_term in name

    related_products = [p for p in get_products() if _related(p)]
    related_products.sort(key=lambda p: (not p.get('in_stock'), -(p.get('order_weight') or 0)))
    related_products = related_products[:12]

    # Get all entries for navigation
    all_entries = get_codex_entries()

    return render_template('public/codex-entry.html', entry=entry,
                           all_entries=all_entries, related_products=related_products)

@public_route('/cart')
def cart_page():
    """Shopping cart/list page"""
    telegram_username = os.environ.get('TELEGRAM_USERNAME', 'warpmonger')
    return render_template('public/cart.html', telegram_username=telegram_username)


@public_route('/cart/line')
def cart_line_page():
    """LINE contact page with instructions"""
    line_id = os.environ.get('LINE_ID', '@warpmonger')
    return render_template('public/line-contact.html', line_id=line_id)


# === Static Pages (Policy / Info) ===

def get_page(slug):
    """Load a static page from content/pages/ with locale support"""
    from flask import g
    locale = getattr(g, 'locale', 'en')
    # Try locale-specific file first, then fallback to default
    if locale != 'en':
        path = os.path.join(PAGES_DIR, f'{slug}.{locale}.md')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                meta, body = parse_frontmatter(f.read())
            meta['content'] = body
            return meta
    path = os.path.join(PAGES_DIR, f'{slug}.md')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            meta, body = parse_frontmatter(f.read())
        meta['content'] = body
        return meta
    return None

ALLOWED_PAGES = ['return-policy', 'terms', 'shopping-guide']

@public_route('/page/<slug>')
def static_page(slug):
    """Render a static info/policy page"""
    # these are now proper webpage routes, not DB markdown pages
    _moved = {'shopping-guide': '/guide', 'return-policy': '/returns', 'terms': '/terms'}
    if slug in _moved:
        return redirect(_moved[slug], code=301)
    if slug not in ALLOWED_PAGES:
        return "Page not found", 404
    page = get_page(slug)
    if not page:
        return "Page not found", 404
    page['content_html'] = markdown.markdown(page['content'])
    return render_template('public/page.html', page=page)


# === Shopping List Email API ===

def format_shopping_list_html(items, user_name, user_email, user_message):
    """Format shopping list as HTML for email"""
    total = sum(item['price'] * item['quantity'] for item in items)

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #8B0000; border-bottom: 2px solid #8B0000; padding-bottom: 10px;">Shopping List Inquiry</h1>

        <p><strong>From:</strong> {user_name}</p>
        <p><strong>Email:</strong> {user_email}</p>

        {f'<p><strong>Message:</strong> {user_message}</p>' if user_message else ''}

        <h2 style="color: #C9B037;">Items Requested:</h2>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <thead>
                <tr style="background: #1a1a1a; color: #d4d4d4;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #333;">Product</th>
                    <th style="padding: 10px; text-align: center; border: 1px solid #333;">Qty</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #333;">Price</th>
                    <th style="padding: 10px; text-align: right; border: 1px solid #333;">Subtotal</th>
                </tr>
            </thead>
            <tbody>
    """

    for item in items:
        subtotal = item['price'] * item['quantity']
        if item.get('inStock') == False:
            status_prefix = '<span style="color: #8B0000; font-weight: bold;">[Out of Stock]</span> '
        elif item.get('isPreOrder') == True:
            status_prefix = '<span style="color: #0088cc; font-weight: bold;">[Pre-Order]</span> '
        else:
            status_prefix = ''
        html += f"""
                <tr>
                    <td style="padding: 10px; border: 1px solid #ddd;">{status_prefix}{item['title']}</td>
                    <td style="padding: 10px; text-align: center; border: 1px solid #ddd;">{item['quantity']}</td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #ddd;">${item['price']:.2f}</td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #ddd;">${subtotal:.2f}</td>
                </tr>
        """

    html += f"""
            </tbody>
            <tfoot>
                <tr style="background: #f5f5f5; font-weight: bold;">
                    <td colspan="3" style="padding: 10px; text-align: right; border: 1px solid #ddd;">Total:</td>
                    <td style="padding: 10px; text-align: right; border: 1px solid #ddd; color: #8B0000;">${total:.2f}</td>
                </tr>
            </tfoot>
        </table>

        <p style="color: #666; font-size: 0.9em;">This inquiry was sent from Warpmonger. Please respond to the customer at their provided email address.</p>
    </body>
    </html>
    """
    return html


def format_shopping_list_text(items, user_name, user_email, user_message):
    """Format shopping list as plain text for email"""
    total = sum(item['price'] * item['quantity'] for item in items)

    text = f"Shopping List Inquiry\n{'='*40}\n\n"
    text += f"From: {user_name}\n"
    text += f"Email: {user_email}\n"
    if user_message:
        text += f"Message: {user_message}\n"
    text += "\nItems Requested:\n\n"

    for i, item in enumerate(items, 1):
        subtotal = item['price'] * item['quantity']
        if item.get('inStock') == False:
            status_prefix = '[Out of Stock] '
        elif item.get('isPreOrder') == True:
            status_prefix = '[Pre-Order] '
        else:
            status_prefix = ''
        text += f"{i}. {status_prefix}{item['title']}\n"
        text += f"   Qty: {item['quantity']} x ${item['price']:.2f} = ${subtotal:.2f}\n\n"

    text += f"{'='*40}\n"
    text += f"Total: ${total:.2f}\n"

    return text


def send_shopping_list_email(items, user_email, user_name, user_message):
    """Send shopping list email to both shop owner and user"""
    smtp_server = os.environ.get('SMTP_SERVER')
    smtp_port = int(os.environ.get('SMTP_PORT', 587))
    smtp_user = os.environ.get('SMTP_USERNAME')
    smtp_pass = os.environ.get('SMTP_PASSWORD')
    smtp_from = os.environ.get('SMTP_FROM', smtp_user)
    shop_email = os.environ.get('SHOP_EMAIL', smtp_from)

    if not all([smtp_server, smtp_user, smtp_pass]):
        raise ValueError("SMTP configuration is incomplete")

    # Prepare content
    text_content = format_shopping_list_text(items, user_name, user_email, user_message)
    html_content = format_shopping_list_html(items, user_name, user_email, user_message)

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)

        # Email 1: Send to shop owner
        msg_shop = MIMEMultipart('alternative')
        msg_shop['Subject'] = f'Shopping List Inquiry from {user_name}'
        msg_shop['From'] = smtp_from
        msg_shop['Reply-To'] = os.environ.get('REPLY_TO', smtp_from)
        msg_shop['To'] = shop_email
        msg_shop['Reply-To'] = user_email
        msg_shop.attach(MIMEText(text_content, 'plain'))
        msg_shop.attach(MIMEText(html_content, 'html'))
        server.send_message(msg_shop)

        # Email 2: Send confirmation to user
        msg_user = MIMEMultipart('alternative')
        msg_user['Subject'] = 'Your Warpmonger Shopping List - We received your inquiry!'
        msg_user['From'] = smtp_from
        msg_user['Reply-To'] = os.environ.get('REPLY_TO', smtp_from)
        msg_user['To'] = user_email

        user_text = f"Hi {user_name},\n\nThank you for your inquiry! We have received your shopping list and will get back to you soon.\n\n" + text_content
        user_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #8B0000;">Thank You for Your Inquiry!</h1>
            <p>Hi {user_name},</p>
            <p>We have received your shopping list and will get back to you soon to discuss the details.</p>
            <hr style="border: 1px solid #333; margin: 20px 0;">
            {html_content}
        </body>
        </html>
        """

        msg_user.attach(MIMEText(user_text, 'plain'))
        msg_user.attach(MIMEText(user_html, 'html'))
        server.send_message(msg_user)


@app.route('/api/send-list', methods=['POST'])
def send_list():
    """Send shopping list via email"""
    data = request.get_json()

    items = data.get('items', [])
    user_email = data.get('email', '').strip()
    user_name = data.get('name', '').strip()
    user_message = data.get('message', '').strip()

    # Validation
    if not items:
        return jsonify({'success': False, 'error': 'No items in the list'}), 400
    if not user_name:
        return jsonify({'success': False, 'error': 'Name is required'}), 400
    if not user_email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400

    try:
        send_shopping_list_email(items, user_email, user_name, user_message)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    except Exception as e:
        print(f"Error sending email: {e}")
        return jsonify({'success': False, 'error': 'Failed to send email. Please try again.'}), 500


@app.route('/sitemap.xml')
def sitemap():
    """Dynamic sitemap. Single zh-TW locale (no /en — it 301s to root).
    Includes products, categories, tags, codex, blog and static pages."""
    from flask import Response
    import posdb as _posdb

    root = request.url_root
    # DB-file mtime is an honest lastmod for all DB-driven content (any POS
    # edit bumps it). Fall back to today if unavailable.
    try:
        db_lastmod = datetime.fromtimestamp(_posdb.db_mtime()).strftime('%Y-%m-%d')
    except Exception:
        db_lastmod = datetime.now().strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    from urllib.parse import quote

    pages = [
        {'loc': root, 'lastmod': db_lastmod, 'changefreq': 'daily', 'priority': '1.0'},
        {'loc': root + 'products', 'lastmod': db_lastmod, 'changefreq': 'daily', 'priority': '0.9'},
        {'loc': root + 'codex', 'lastmod': db_lastmod, 'changefreq': 'weekly', 'priority': '0.6'},
        {'loc': root + 'tags', 'lastmod': db_lastmod, 'changefreq': 'weekly', 'priority': '0.4'},
        {'loc': root + 'blog', 'lastmod': db_lastmod, 'changefreq': 'weekly', 'priority': '0.5'},
        {'loc': root + 'faq', 'lastmod': today, 'changefreq': 'monthly', 'priority': '0.5'},
    ]

    # Category listing pages (browsed as /products?category=<slug>)
    for cat in get_categories():
        pages.append({'loc': f"{root}products?category={quote(cat['slug'])}",
                      'lastmod': db_lastmod, 'changefreq': 'weekly', 'priority': '0.7'})

    # All products
    for product in get_products():
        pages.append({'loc': f"{root}products/{product['category']}/{product['slug']}",
                      'lastmod': db_lastmod, 'changefreq': 'weekly', 'priority': '0.8'})

    # Tag listing pages — skip very thin tags (<3 products) to avoid low-value URLs
    for tag in get_all_tags():
        if tag.get('count', 0) >= 3:
            pages.append({'loc': f"{root}products?tag={quote(tag['name'])}",
                          'lastmod': db_lastmod, 'changefreq': 'weekly', 'priority': '0.5'})

    # Codex entries (lore pages — strong long-tail)
    for entry in get_codex_entries():
        pages.append({'loc': f"{root}codex/{entry['slug']}",
                      'lastmod': db_lastmod, 'changefreq': 'monthly', 'priority': '0.5'})

    # Blog posts
    for post in get_blog_posts():
        pages.append({'loc': f"{root}blog/{post['slug']}",
                      'lastmod': post.get('date') or db_lastmod,
                      'changefreq': 'monthly', 'priority': '0.5'})

    # Static pages (policy / info)
    for page_slug in ALLOWED_PAGES:
        pages.append({'loc': f"{root}page/{page_slug}",
                      'lastmod': today, 'changefreq': 'monthly', 'priority': '0.3'})

    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for p in pages:
        loc = p['loc'].replace('&', '&amp;')
        xml.append('  <url>')
        xml.append(f'    <loc>{loc}</loc>')
        xml.append(f'    <lastmod>{p["lastmod"]}</lastmod>')
        xml.append(f'    <changefreq>{p["changefreq"]}</changefreq>')
        xml.append(f'    <priority>{p["priority"]}</priority>')
        xml.append('  </url>')
    xml.append('</urlset>')

    return Response('\n'.join(xml), mimetype='application/xml')

@app.route('/sitemap-images.xml')
def sitemap_images():
    """Generate image sitemap for better image search indexing"""
    from flask import Response

    products = get_products()

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'

    from xml.sax.saxutils import escape
    for product in products:
        if product.get('images'):
            # zh-TW name for image search; fall back to English title
            name = escape(product.get('zhtw_name') or product.get('title') or '')
            xml += '  <url>\n'
            xml += f'    <loc>{request.url_root}products/{product["category"]}/{product["slug"]}</loc>\n'

            for image in product['images'][:10]:  # Max 10 images per product
                if not image.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):  # Skip videos
                    image_url = escape(f'{request.url_root}static/images/products/{product["category"]}/{product["slug"]}/{image}')
                    xml += '    <image:image>\n'
                    xml += f'      <image:loc>{image_url}</image:loc>\n'
                    xml += f'      <image:title>{name}</image:title>\n'
                    xml += f'      <image:caption>{name}｜JOYTOY 可動模型 - 阿北玩具堂</image:caption>\n'
                    xml += '    </image:image>\n'

            xml += '  </url>\n'

    xml += '</urlset>'

    return Response(xml, mimetype='application/xml')

@app.route('/merchant-feed.xml')
def merchant_feed():
    """Google Merchant Center / free Shopping listings product feed (RSS 2.0).
    Submit this URL in Merchant Center. Only sellable, priced, published
    products with an image are included."""
    from flask import Response
    from xml.sax.saxutils import escape

    root = request.url_root
    # availability mapping from our internal availability engine
    AVAIL = {'in_stock': 'in_stock', 'preorder': 'preorder',
             'incoming': 'backorder', 'orderable': 'backorder'}

    items = []
    for p in get_products():
        price = p.get('final_price') or 0
        avail = AVAIL.get(p.get('availability'))
        imgs = p.get('images') or []
        # need a real price, a sellable availability, and at least one image
        if not price or not avail or not imgs:
            continue
        img = next((i for i in imgs
                    if not i.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))), None)
        if not img:
            continue
        name = p.get('zhtw_name') or p.get('title') or ''
        en = p.get('title') or ''
        title = name + (f'（{en}）' if en and en != name else '')
        desc_bits = [name] + [b for b in (p.get('series'), p.get('scale')) if b]
        desc = '｜'.join(desc_bits) + ' JOYTOY 可動模型。台灣現貨／預購，阿北玩具堂。'
        link = f"{root}products/{p['category']}/{p['slug']}"
        img_link = f"{root}static/images/products/{p['category']}/{p['slug']}/{img}"
        barcode = (p.get('sku') or '').strip()   # posdb 'sku' = barcode number
        gtin = barcode if barcode.isdigit() and len(barcode) in (8, 12, 13, 14) else ''
        mpn = (p.get('id') or '').strip()        # JT SKU

        # material — category/name aware (figures PVC/ABS, cases acrylic, tools metal)
        _tl = [str(t).lower() for t in (p.get('tags') or [])]
        _nm = (name + ' ' + en).lower()
        if any('display case' in t for t in _tl) or 'display case' in _nm or '展示盒' in name:
            material = 'Acrylic'
        elif p.get('category') == 'tools':
            material = 'Metal'
        else:
            material = 'PVC, ABS'

        # Google requires availability_date for preorder/backorder. Use the real
        # (future) preorder date when we have one, else an honest estimate:
        # ~2 wk for 集運/在途, ~3 wk for 調貨 (matches the site's arrival copy).
        avail_date = ''
        if avail in ('preorder', 'backorder'):
            from datetime import timedelta
            raw = (p.get('available_date') or '').strip()  # 'YYYY-MM-DD' or ''
            use = ''
            if raw:
                try:
                    if datetime.strptime(raw, '%Y-%m-%d').date() > datetime.now().date():
                        use = raw
                except ValueError:
                    pass
            if not use:
                days = 14 if p.get('availability') == 'incoming' else 21
                use = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
            avail_date = f'{use}T09:00+0800'

        it = ['    <item>',
              f'      <g:id>{escape(mpn or barcode or p["slug"])}</g:id>',
              f'      <g:title>{escape(title[:150])}</g:title>',
              f'      <g:description>{escape(desc[:5000])}</g:description>',
              f'      <g:link>{escape(link)}</g:link>',
              f'      <g:image_link>{escape(img_link)}</g:image_link>',
              '      <g:condition>new</g:condition>',
              f'      <g:availability>{avail}</g:availability>',
              *( [f'      <g:availability_date>{avail_date}</g:availability_date>'] if avail_date else [] ),
              f'      <g:price>{int(round(price))} TWD</g:price>',
              '      <g:brand>JOYTOY</g:brand>',
              f'      <g:material>{material}</g:material>',
              '      <g:google_product_category>6058</g:google_product_category>',
              '      <g:identifier_exists>' + ('true' if gtin else 'false') + '</g:identifier_exists>']
        if gtin:
            it.append(f'      <g:gtin>{gtin}</g:gtin>')
        if mpn:
            it.append(f'      <g:mpn>{escape(mpn)}</g:mpn>')
        if p.get('is_on_sale') and (p.get('sale_price') or 0) > 0 and p['sale_price'] < price:
            it.append(f'      <g:sale_price>{int(round(p["sale_price"]))} TWD</g:sale_price>')
        it.append('    </item>')
        items.append('\n'.join(it))

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<rss version="2.0" xmlns:g="http://base.google.com/ns/1.0">\n'
           '  <channel>\n'
           "    <title>ABBEY'S TOYS 阿北玩具堂</title>\n"
           f'    <link>{root}</link>\n'
           '    <description>JOYTOY／戰鎚40K 可動模型商品資料</description>\n'
           + '\n'.join(items) +
           '\n  </channel>\n</rss>')
    return Response(xml, mimetype='application/xml')

FAQ_ITEMS = [
    ("運費怎麼計算？",
     "單筆消費滿 NT$1,000 免運費；未滿 NT$1,000 酌收 NT$60。"),
    ("「現貨」和「預購」差在哪？大概多久到貨？",
     "現貨商品下單後盡快出貨；標示「約2週到貨」為台灣／集運調貨，約 2 週內；"
     "缺貨可訂購商品由原廠調貨約 2-3 週。預購商品依商品頁標示的到貨日，"
     "「不需預付」，到貨後我們會通知您付款再出貨。"),
    ("有哪些付款方式？",
     "提供銀行轉帳（先審後付：送出訂單後顯示轉帳帳戶，轉帳完成回報帳號後五碼，確認入帳後出貨）、"
     "貨到付款（超商取貨付款），以及 LINE Pay 線上付款。"),
    ("下單後可以取消或退貨嗎？",
     "訂單成立、尚未付款前，可到「會員中心 → 我的訂單」直接按「取消訂單」。"
     "已付款或已出貨的訂單，可在同一頁按「申請退貨／退款」，選擇要退的商品與原因，"
     "阿北確認後為您退款，狀態與進度都會顯示在訂單上並以 LINE／Email 通知。"),
    ("可以怎麼取貨／寄送？",
     "支援 7-11、全家 店到店取貨，以及郵局宅配。結帳時可選擇門市或填寫地址。"),
    ("會員價是什麼？怎麼取得？",
     "註冊成為會員即享會員價（一般為定價 9 折，若商品有特價則以較低者為準）。"
     "登入後商品頁與購物車會直接顯示您的會員價。"),
    ("標示「絕版詢價」的商品還買得到嗎？",
     "部分停產／絕版商品不顯示價格，可透過 LINE 與我們詢價，我們會協助尋貨與報價。"),
    ("JOYTOY 是什麼品牌？",
     "JOYTOY（暗源）是知名可動兵人模型品牌，擁有 Warhammer 40,000、The Horus Heresy 等官方授權，"
     "推出 1/18 等比例的可動模型，做工細緻、關節可動，適合收藏與展示。"),
    ("如何收到到貨或補貨通知？",
     "加入會員並綁定 LINE 後，將商品加入「到貨通知」，當該商品到貨或現貨補貨時，我們會主動以 LINE／Email 通知您。"),
]

@public_route('/faq')
def faq_page():
    """FAQ page with FAQPage structured data (rich result eligible)."""
    return render_template('public/faq.html', faq_items=FAQ_ITEMS)

@public_route('/guide')
def shopping_guide_page():
    """購物說明 — the canonical how-to-buy page (availability, payment,
    shipping, preorder, inquiry, cancel/return)."""
    return render_template('public/guide.html')

@public_route('/returns')
def return_policy_page():
    """退換貨說明 — proper webpage (was a DB markdown page)."""
    return render_template('public/return.html')

@public_route('/terms')
def terms_page():
    """服務條款 — proper webpage (was a DB markdown page)."""
    return render_template('public/terms.html')

@app.route('/api/quiz-result', methods=['POST'])
def api_quiz_result():
    """Persist a completed 原體 quiz result for analysis (fire-and-forget)."""
    data = request.get_json(silent=True) or {}
    rk = (data.get('result_key') or '').strip()[:16]
    if not rk:
        return jsonify({'success': False}), 400
    try:
        memberdb.record_quiz_result(
            rk, (data.get('character') or '')[:100], (data.get('legion') or '')[:100],
            data.get('scores'), session.get('member_id'))
    except Exception as e:
        print(f"quiz result save failed: {e}")
        return jsonify({'success': False}), 500
    return jsonify({'success': True})

@app.route('/favicon.ico')
def favicon_root():
    """Serve favicon at the domain root — Google's favicon crawler and browsers
    request /favicon.ico directly, regardless of the <link rel="icon"> tags."""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/apple-touch-icon.png')
@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon_root():
    """Serve the apple-touch-icon at the root path (iOS/crawlers probe here)."""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon-192.png', mimetype='image/png')

@app.route('/robots.txt')
def robots():
    """Generate robots.txt"""
    from flask import Response

    txt = f"""User-agent: *
Allow: /

Sitemap: {request.url_root}sitemap.xml
Sitemap: {request.url_root}sitemap-images.xml
"""

    return Response(txt, mimetype='text/plain')

@app.route('/feed.xml')
@app.route('/rss.xml')
def rss_feed():
    """Generate RSS feed for blog posts"""
    from flask import Response

    posts = get_blog_posts()[:20]  # Latest 20 posts

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
    xml += '  <channel>\n'
    xml += '    <title>Warpmonger Blog - Action Figure News &amp; Updates</title>\n'
    xml += f'    <link>{request.url_root}blog</link>\n'
    xml += '    <description>Latest news, tips, and updates about premium action figures and collectibles from Warpmonger.</description>\n'
    xml += '    <language>en-us</language>\n'
    xml += f'    <lastBuildDate>{datetime.now().strftime("%a, %d %b %Y %H:%M:%S +0000")}</lastBuildDate>\n'
    xml += f'    <atom:link href="{request.url_root}feed.xml" rel="self" type="application/rss+xml"/>\n'

    for post in posts:
        xml += '    <item>\n'
        xml += f'      <title>{post["title"]}</title>\n'
        xml += f'      <link>{request.url_root}blog/{post["slug"]}</link>\n'
        xml += f'      <guid isPermaLink="true">{request.url_root}blog/{post["slug"]}</guid>\n'
        xml += f'      <description><![CDATA[{post.get("excerpt", "")}]]></description>\n'
        if post.get('date'):
            try:
                pub_date = datetime.strptime(post['date'], '%Y-%m-%d').strftime('%a, %d %b %Y 00:00:00 +0000')
                xml += f'      <pubDate>{pub_date}</pubDate>\n'
            except:
                pass
        if post.get('author'):
            xml += f'      <author>noreply@johnactionfigure.com ({post["author"]})</author>\n'
        xml += '    </item>\n'

    xml += '  </channel>\n'
    xml += '</rss>'

    return Response(xml, mimetype='application/rss+xml')


# ===== API Routes - Products =====

@app.route('/api/products', methods=['GET'])
def api_get_products():
    """Get all products"""
    category = request.args.get('category')
    products = get_products(category)
    return jsonify({'products': products})

@app.route('/api/products/<category>/<slug>', methods=['GET'])
def api_get_product(category, slug):
    """Get single product"""
    product = get_product(category, slug)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    return jsonify({'product': product})




@app.route('/api/categories', methods=['GET'])
def api_get_categories():
    """Get all categories"""
    categories = get_categories()
    return jsonify({'categories': categories})

@app.route('/api/categories/<slug>', methods=['GET'])
def api_get_category(slug):
    """Get single category"""
    category = get_category(slug)
    if not category:
        return jsonify({'error': 'Category not found'}), 404
    return jsonify({'category': category})





@app.route('/api/products/autocomplete', methods=['GET'])
def api_autocomplete():
    """Get autocomplete suggestions for product search"""
    query = request.args.get('q', '').strip()

    if not query or len(query) < 2:
        return jsonify({'suggestions': []})

    # Get all products matching the search query
    products = get_products(search=query)

    # Limit to top 10 results
    suggestions = []
    for product in products[:10]:
        suggestions.append({
            'title': product['title'],
            'id': product.get('id', ''),
            'cn_name': product.get('cn_name', ''),
            'zhtw_name': product.get('zhtw_name', ''),
            'category': product['category'],
            'slug': product['slug'],
            'image': product['images'][0] if product['images'] else None
        })

    return jsonify({'suggestions': suggestions})

# ===== API Routes - Blog =====

@app.route('/api/blog', methods=['GET'])
def api_get_blog_posts():
    """Get all blog posts"""
    posts = get_blog_posts()
    return jsonify({'posts': posts})

@app.route('/api/blog/<slug>', methods=['GET'])
def api_get_blog_post(slug):
    """Get single blog post"""
    post = get_blog_post(slug)
    if not post:
        return jsonify({'error': 'Post not found'}), 404
    return jsonify({'post': post})





# ===== API Routes - Promotions =====

@app.route('/api/promotions', methods=['GET'])
def api_get_promotions():
    """Get all promotions"""
    promotions = get_promotions()
    return jsonify({'promotions': promotions})

@app.route('/api/promotions/<slug>', methods=['GET'])
def api_get_promotion(slug):
    """Get single promotion"""
    promo = get_promotion(slug)
    if not promo:
        return jsonify({'error': 'Promotion not found'}), 404
    return jsonify({'promotion': promo})






# ===== API Routes - Codex =====

@app.route('/api/codex', methods=['GET'])
def api_get_codex_entries():
    """Get all codex entries"""
    entries = get_codex_entries()
    return jsonify({'entries': entries})

@app.route('/api/codex/<slug>', methods=['GET'])
def api_get_codex_entry(slug):
    """Get single codex entry for tooltip"""
    entry = get_codex_entry(slug)
    if not entry:
        return jsonify({'error': 'Entry not found'}), 404

    # If requested from admin, include products that reference this codex
    if request.args.get('include_products') == 'true':
        products = get_products()
        # Search terms: title and aliases
        search_terms = [entry['title'].lower()]
        if entry.get('aliases'):
            search_terms.extend([a.lower() for a in entry['aliases']])

        referencing_products = []
        for product in products:
            description = (product.get('description') or '').lower()
            # Check if any search term appears in description
            for term in search_terms:
                if term in description:
                    referencing_products.append({
                        'slug': product['slug'],
                        'category': product['category'],
                        'title': product['title']
                    })
                    break

        entry['products'] = referencing_products
        entry['product_count'] = len(referencing_products)

    return jsonify({'entry': entry})




# ===== API Routes - Tags =====






# ===== API Routes - Images =====



# ===== Static Files =====

@app.route('/static/images/products/<category>/<slug>/<filename>')
def serve_product_image(category, slug, filename):
    """Serve product images from the POS media dir (media/<SKU>/), with
    on-demand thumbnail generation for thumb_* names. Falls back to the
    legacy content/ dir for anything not in the POS."""
    import posdb as _posdb
    media_dir = _posdb.media_dir_for(category, slug)
    if media_dir and os.path.isdir(media_dir):
        path = os.path.join(media_dir, filename)
        if not os.path.exists(path) and filename.startswith('thumb_'):
            stem = filename[len('thumb_'):].rsplit('.', 1)[0]
            for f in os.listdir(media_dir):
                if f.rsplit('.', 1)[0] == stem and not f.startswith('thumb_'):
                    create_thumbnail(os.path.join(media_dir, f), path)
                    break
        if os.path.exists(path):
            return send_from_directory(media_dir, filename)
    images_dir = os.path.join(PRODUCTS_DIR, category, slug, 'images')
    return send_from_directory(images_dir, filename)

@app.route('/static/images/categories/<slug>/<filename>')
def serve_category_icon(slug, filename):
    """Serve category icons"""
    images_dir = os.path.join(CATEGORIES_DIR, slug, 'images')
    return send_from_directory(images_dir, filename)

# ===== Cache Warming =====

def warm_cache():
    """Pre-load all data into cache on startup to avoid cold start delays"""
    print("Warming cache...")

    # Load all products
    products = get_products()
    print(f"  - Loaded {len(products)} products")

    # Load all categories
    categories = get_categories()
    print(f"  - Loaded {len(categories)} categories")

    # Load codex entries
    codex_entries = get_codex_entries()
    print(f"  - Loaded {len(codex_entries)} codex entries")

    # Build codex lookup
    build_codex_lookup()
    print("  - Built codex lookup")

    # Load tags
    tags = get_all_tags()
    print(f"  - Loaded {len(tags)} tags")

    # Load featured tags
    featured_tags = get_featured_tags()
    print(f"  - Loaded {len(featured_tags)} featured tags")

    # Note: HTML pages are cached on first request (can't pre-render due to request context)
    print("Cache warming complete! (HTML pages cache on first visit)")

# Warm cache on import (works with gunicorn/uwsgi)
warm_cache()

# ===== API Routes - Featured Tags =====






# ===== API Routes - Featured Products =====



# ===== Main =====

# ===== Web checkout (orders staged into the POS via its storefront API) =====

POS_API_URL = os.environ.get('POS_API_URL', 'http://127.0.0.1:8000')
STOREFRONT_API_KEY = os.environ.get('STOREFRONT_API_KEY', '')

def _valid_storefront_key(submitted):
    """Timing-safe check of the X-Storefront-Key header against the shared
    secret. False if either side is empty (no key configured = deny all)."""
    if not submitted or not STOREFRONT_API_KEY:
        return False
    return hmac.compare_digest(submitted, STOREFRONT_API_KEY)

BANK_TRANSFER_INFO = os.environ.get(
    'BANK_TRANSFER_INFO',
    '兆豐國際商業銀行 民生分行（銀行代碼 017）\n帳號：03609026033\n戶名：阿北的店')

_store_cache = {}

def _load_stores(carrier):
    """7-11 / 全家 store directories live in the POS repo's data dir."""
    if carrier not in _store_cache:
        import posdb as _posdb
        fname = 'seven_eleven_stores.json' if carrier == '711' else 'fami_stores.json'
        path = os.path.join(os.path.dirname(_posdb.POS_DB), fname)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                _store_cache[carrier] = json.load(f)
        except Exception:
            _store_cache[carrier] = []
    return _store_cache[carrier]


@app.route('/api/stores')
def api_stores():
    carrier = request.args.get('carrier', '711')
    q = (request.args.get('q') or '').strip()
    if carrier not in ('711', 'fami') or len(q) < 2:
        return jsonify({'stores': []})
    hits = []
    for s in _load_stores(carrier):
        if q in s.get('name', '') or q in s.get('address', '') \
           or q in s.get('town', '') or q in s.get('city', ''):
            hits.append({'code': s['code'], 'name': s['name'], 'address': s['address']})
            if len(hits) >= 20:
                break
    return jsonify({'stores': hits})


def _resolve_cart_items(raw_items):
    """Resolve client cart lines against live POS data. Returns (lines, errors).
    Members get 會員價; guests pay the public price."""
    import posdb as _posdb
    is_member = bool(current_member())
    lines, errors = [], []
    for raw in raw_items[:50]:
        product = _posdb.get_product(str(raw.get('category') or ''), str(raw.get('slug') or ''))
        if not product:
            errors.append(f"{raw.get('title') or raw.get('slug')} 已下架")
            continue
        qty = max(1, min(99, int(raw.get('quantity') or 1)))
        if product['availability'] == 'inquiry':
            price = 0
        elif is_member and product['member_price']:
            price = product['member_price']
        else:
            price = product['final_price']
        lines.append({
            'sku': product['id'],
            'category': product['category'], 'slug': product['slug'],
            'title': product['zhtw_name'] or product['title'],
            'image': product['images'][0] if product['images'] else '',
            'qty': qty,
            'price': price,
            'availability': product['availability'],
            'available_date': product['available_date'],
            'available_display': product.get('available_display', ''),
        })
    return lines, errors


@app.route('/api/checkout/resolve', methods=['POST'])
def checkout_resolve():
    data = request.get_json(silent=True) or {}
    lines, errors = _resolve_cart_items(data.get('items') or [])
    return jsonify({'items': lines, 'errors': errors})


@app.route('/api/checkout/submit', methods=['POST'])
def checkout_submit():
    import urllib.request
    import urllib.error
    data = request.get_json(silent=True) or {}
    lines, errors = _resolve_cart_items(data.get('items') or [])
    if errors:
        return jsonify({'success': False, 'error': '、'.join(errors)}), 400
    if not lines:
        return jsonify({'success': False, 'error': '清單是空的'}), 400

    member = current_member()
    if member:
        if data.get('phone') and not member.get('phone'):
            memberdb.set_member_phone(member['id'], data['phone'].strip())
        if not data.get('email') and member.get('email'):
            data['email'] = member['email']
    elif not (data.get('email') or '').strip():
        # guests must leave an email so we can reach them about the order
        return jsonify({'success': False,
                        'error': '未登入時請留 email，以便接收訂單通知'}), 400

    payload = json.dumps({
        'member': bool(member),
        'name': data.get('name'), 'phone': data.get('phone'),
        'email': data.get('email'), 'line_id': data.get('line_id'),
        'delivery_method': data.get('delivery_method'),
        'recipient_name': data.get('recipient_name'),
        'recipient_phone': data.get('recipient_phone'),
        'store_code': data.get('store_code'), 'store_name': data.get('store_name'),
        'address': data.get('address'),
        'payment_method': data.get('payment_method'),
        'ship_together': bool(data.get('ship_together', True)),
        'note': data.get('note'),
        'items': [{'sku': l['sku'], 'qty': l['qty']} for l in lines],
    }).encode()

    req = urllib.request.Request(
        POS_API_URL + '/api/storefront/orders', data=payload,
        headers={'Content-Type': 'application/json',
                 'X-Storefront-Key': STOREFRONT_API_KEY},
        method='POST')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get('detail', '訂單送出失敗')
        except Exception:
            detail = '訂單送出失敗'
        return jsonify({'success': False, 'error': detail}), 400
    except Exception:
        return jsonify({'success': False, 'error': '系統忙碌中，請稍後再試或改用 LINE 聯絡'}), 502

    if member:
        used = {
            'label': None,
            'recipient_name': data.get('recipient_name') or data.get('name'),
            'recipient_phone': data.get('recipient_phone') or data.get('phone'),
            'delivery': data.get('delivery_method'),
            'store_code': data.get('store_code'),
            'store_name': data.get('store_name'),
            'address': data.get('address'),
        }
        try:
            if not memberdb.find_matching_address(member['id'], used):
                memberdb.save_address(member['id'], used)
        except Exception as e:
            print(f"auto-save address failed: {e}")

    try:
        _send_order_emails(result['order_no'], data, lines, result)
    except Exception as e:
        print(f"order email failed: {e}")

    if member and member.get('line_user_id'):
        try:
            import linepush
            if linepush.enabled():
                grand = result.get('grand_total_twd', result.get('total_twd', 0))
                linepush.push_text(member['line_user_id'],
                    f"感謝訂購！訂單 {result['order_no']} 已收到，"
                    f"合計 NT${int(grand):,}。確認後會再通知您。")
        except Exception as e:
            print(f"line order push failed: {e}")

    # LINE Pay: create the payment request for the chargeable part
    # (現貨/調貨 items + shipping; preorders are pay-on-arrival, inquiry
    # unpriced). Use the POS's own charge_now_twd so the amount matches
    # its _charge_now_twd exactly — the confirm step rejects a mismatch.
    if data.get('payment_method') == 'linepay':
        import linepay
        charge = result.get('charge_now_twd', 0)
        if linepay.enabled() and charge > 0:
            try:
                base = request.url_root.rstrip('/')
                pay_url, txn = linepay.request_payment(
                    result['order_no'], charge,
                    f"阿北玩具堂訂單 {result['order_no']}",
                    f"{base}/linepay/confirm",
                    f"{base}/linepay/cancel?orderId={result['order_no']}",
                )
                result['payment_url'] = pay_url
                result['charge_twd'] = charge
            except Exception as e:
                print(f"linepay request failed: {e}")
                # order stands; fall back to manual LINE Pay link flow

    # magic-link token so the success page can offer order management to guests
    result['order_token'] = _order_token(result['order_no'])
    return jsonify(result)


def _pos_api(method, path, body=None):
    import urllib.request
    req = urllib.request.Request(
        POS_API_URL + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 'X-Storefront-Key': STOREFRONT_API_KEY},
        method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


@app.route('/linepay/confirm')
def linepay_confirm():
    import linepay
    txn = request.args.get('transactionId')
    order_no = request.args.get('orderId')
    if not txn or not order_no:
        return redirect('/checkout/success?payerr=1')
    try:
        info = _pos_api('GET', f'/api/storefront/orders/{order_no}')
        charge = info.get('charge_twd') or 0
        linepay.confirm_payment(txn, charge)
        _pos_api('POST', f'/api/storefront/orders/{order_no}/payment',
                 {'payment_status': '已付款', 'payment_note': f'LINE Pay {txn}'})
        params = f'no={order_no}&pm=linepay&paid=1&total={int(charge)}&t={_order_token(order_no)}'
    except Exception as e:
        print(f"linepay confirm failed: {e}")
        params = f'no={order_no}&pm=linepay&payerr=1&t={_order_token(order_no)}'
    return redirect('/checkout/success?' + params)


@app.route('/linepay/cancel')
def linepay_cancel():
    order_no = request.args.get('orderId', '')
    return redirect(f'/checkout/success?no={order_no}&pm=linepay&paycancel=1')


# ===== PayUni (統一金流) integrated payment =====
import payuni


def _payuni_mer_trade_no(order_no):
    """PayUni MerTradeNo: alphanumeric + unique per attempt. AB260708-001 ->
    AB260708001 + 5-digit time suffix. Recover order_no from the first 11 chars."""
    import time
    return f"{order_no.replace('-', '')}{int(time.time()) % 100000:05d}"


def _order_no_from_mtn(mtn):
    base = (mtn or "")[:11]            # AB + yymmdd(6) + NNN(3)
    return base[:8] + '-' + base[8:11] if len(base) >= 11 else None


def _payuni_pending_note(info):
    pt = str(info.get('PaymentType', ''))
    payno = info.get('PayNo') or info.get('CodeNo') or ''
    if pt == '2':
        return f"ATM 待轉帳 帳號 {payno}"[:100]
    if pt == '3':
        return f"超商代碼 {payno}"[:100]
    return f"付款處理中 {payno}"[:100]


@app.route('/payuni/pay/<order_no>')
def payuni_pay(order_no):
    """Build the PayUni UPP request and auto-submit the browser to their page."""
    import time
    from datetime import datetime, timedelta
    token = request.args.get('t', '')
    if not _authorized_for_order(order_no, token):
        return redirect('/order-lookup?no=' + (order_no or ''))
    if not payuni.enabled():
        return "PayUni 尚未設定，請改用其他付款方式或聯絡阿北。", 503
    import posdb as _posdb
    order = _posdb.get_web_order(order_no)
    if not order or order.get('payment_status') != '待付款' or int(order.get('amount_due') or 0) <= 0:
        return redirect(f'/order/{order_no}?t={_order_token(order_no)}')
    base = request.url_root.rstrip('/')
    prod = ';'.join(f"{it.get('zhtw_name') or it.get('en_name')}x{it['quantity']}"
                    for it in order['items'][:5]) or '阿北玩具堂訂單'
    info = {
        'MerID': payuni.mer_id(),
        'MerTradeNo': _payuni_mer_trade_no(order_no),
        'TradeAmt': int(order['amount_due']),
        'Timestamp': int(time.time()),
        'ProdDesc': prod[:150],
        'UsrMail': order.get('email') or '',
        'ReturnURL': f'{base}/payuni/return',
        'NotifyURL': f'{base}/payuni/notify',
        'ExpireDate': (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
        # enable methods (LINE Pay stays on the direct integration)
        'Credit': 1, 'CreditInst': '3,6,12', 'CreditUnionPay': 1,
        'ApplePay': 1, 'GooglePay': 1, 'SamsungPay': 1,
        'ATM': 1, 'CVS': 1, 'ICash': 1, 'JKoPay': 1, 'Aftee': 1,
    }
    return render_template('public/payuni_redirect.html',
                           action=payuni.api_url('upp'),
                           fields=payuni.build_request(info))


def _payuni_apply(info, source):
    """Apply a verified PayUni result to the order (idempotent). Called from
    both the server-to-server notify and the browser return."""
    if info.get('Status') != 'SUCCESS':
        print(f"[payuni {source}] not SUCCESS: {info.get('Status')} / {info.get('Message')}")
        return
    order_no = _order_no_from_mtn(info.get('MerTradeNo', ''))
    if not order_no:
        print(f"[payuni {source}] cannot recover order_no from {info.get('MerTradeNo')}")
        return
    ts = str(info.get('TradeStatus', ''))
    print(f"[payuni {source}] order {order_no} TradeStatus={ts} PaymentType={info.get('PaymentType')}")
    try:
        if ts == '1':          # paid
            _pos_api('POST', f'/api/storefront/orders/{order_no}/payment',
                     {'payment_status': '已付款',
                      'payment_note': f"PayUni {info.get('TradeNo', '')} PT{info.get('PaymentType', '')}"})
            print(f"[payuni {source}] {order_no} -> 已付款")
        elif ts == '0':        # ATM/CVS code issued, awaiting payment
            _pos_api('POST', f'/api/storefront/orders/{order_no}/payment',
                     {'payment_status': '待付款',
                      'payment_note': _payuni_pending_note(info)})
        elif ts == '4':        # ATM/CVS code expired unpaid
            _pos_api('POST', f'/api/storefront/orders/{order_no}/payment',
                     {'payment_status': '待付款',
                      'payment_note': 'PayUni 付款逾期（代碼失效，可重新付款）'})
            print(f"[payuni {source}] {order_no} 付款逾期")
    except Exception as e:
        print(f"[payuni {source}] update failed: {e}")


@app.route('/payuni/notify', methods=['POST'])
def payuni_notify():
    """Server-to-server payment result from PayUni."""
    if not payuni.enabled():
        return 'disabled', 503
    print(f"[payuni notify] keys={list(request.form.keys())}")
    info = payuni.verify_callback(request.form)
    if not info:
        print("[payuni notify] HASH VERIFY FAILED (or missing EncryptInfo)")
        return 'bad hash', 400
    _payuni_apply(info, 'notify')
    return 'OK'


@app.route('/payuni/return', methods=['POST', 'GET'])
def payuni_return():
    """Customer's browser lands here after PayUni. Also applies the result,
    in case the server-to-server notify is delayed/absent (e.g. sandbox)."""
    info = payuni.verify_callback(request.form) if request.method == 'POST' else None
    if info:
        print(f"[payuni return] keys={list(request.form.keys())}")
        _payuni_apply(info, 'return')
    else:
        print(f"[payuni return] method={request.method} form_keys={list(request.form.keys())} args={dict(request.args)}")
    order_no = _order_no_from_mtn((info or {}).get('MerTradeNo', '')) or request.args.get('no', '')
    if order_no:
        return redirect(f'/order/{order_no}?t={_order_token(order_no)}')
    return redirect('/order-lookup')


@app.route('/payuni/refund-page/<order_no>')
def payuni_refund_page(order_no):
    """ATM/超商 refund: the buyer enters their bank account on PayUni's page."""
    import re
    token = request.args.get('t', '')
    if not _authorized_for_order(order_no, token):
        return redirect('/order-lookup?no=' + (order_no or ''))
    if not payuni.enabled():
        return 'PayUni 未設定', 503
    import posdb as _posdb
    order = _posdb.get_web_order(order_no)
    m = re.search(r'PayUni\s+(\d+)', (order or {}).get('payment_note', '') or '')
    if not order or not m:
        return redirect(f'/order/{order_no}?t={_order_token(order_no)}')
    action, fields = payuni.offline_refund_fields(m.group(1), request.url_root.rstrip('/'))
    return render_template('public/payuni_redirect.html', action=action, fields=fields)


@app.route('/payuni/refund-done', methods=['POST', 'GET'])
def payuni_refund_done():
    return render_template('public/payuni_refund_done.html')


def _send_order_emails(order_no, data, lines, totals):
    """Branded HTML order-confirmation to the customer + a copy to the shop.
    `totals` is the POS create-order response (total/shipping/grand/charge_now)."""
    import mailer
    shop_email = os.environ.get('SHOP_EMAIL',
                                os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USERNAME'))
    order_url = f"{SITE_URL}/order/{order_no}?t={_order_token(order_no)}"
    mailer.send_order_confirmation(order_no, data, lines, totals,
                                   BANK_TRANSFER_INFO, shop_email=shop_email,
                                   order_url=order_url)


# 16 results: 代表人物 + 軍團, keyed by 4-axis combo
# axes: I忠誠/X反骨 · H熱血/C沉穩 · F信念/R理性 · D直率/S深沉
QUIZ_RESULTS = {
    'ICRD': {'character': '羅伯特·基里曼', 'legion': '極限戰士', 'codex': 'roboute-guilliman', 'term': '極限戰士'},
    'ICRS': {'character': '貝利薩留·考爾', 'legion': '機械神教', 'codex': 'belisarius-cawl', 'term': None},
    'ICFD': {'character': '羅格·多恩', 'legion': '帝國之拳', 'codex': 'rogal-dorn', 'term': '帝國之拳'},
    'ICFS': {'character': '萊恩·艾爾莊森', 'legion': '暗黑天使', 'codex': 'lion-eljonson', 'term': '暗黑天使'},
    'IHFD': {'character': '聖吉爾斯', 'legion': '血天使', 'codex': 'sanguinius', 'term': '血天使'},
    'IHFS': {'character': '賈曼·汗', 'legion': '白疤', 'codex': None, 'term': '白疤'},
    'IHRD': {'character': '里曼·魯斯', 'legion': '太空野狼', 'codex': 'leman-russ', 'term': '太空野狼'},
    'IHRS': {'character': '康斯坦丁·瓦爾多', 'legion': '帝皇禁軍', 'codex': 'constantin-valdor', 'term': '禁軍'},
    'XCRD': {'character': '佩圖拉博', 'legion': '鋼鐵勇士', 'codex': 'perturabo', 'term': '鋼鐵勇士'},
    'XCRS': {'character': '阿爾法留斯', 'legion': '阿爾法軍團', 'codex': 'alpharius', 'term': '阿爾法軍團'},
    'XCFD': {'character': '莫塔里安', 'legion': '死亡守衛', 'codex': 'mortarion', 'term': '死亡守衛'},
    'XCFS': {'character': '馬格努斯', 'legion': '千子', 'codex': 'magnus', 'term': '千子'},
    'XHFD': {'character': '安格隆', 'legion': '吞世者', 'codex': None, 'term': '吞世者'},
    'XHFS': {'character': '康拉德·科茲', 'legion': '午夜領主', 'codex': 'night-lords', 'term': '午夜領主'},
    'XHRD': {'character': '歐克大老大', 'legion': '歐克', 'codex': 'orks', 'term': '歐克'},
    'XHRS': {'character': '荷魯斯', 'legion': '荷魯斯之子', 'codex': 'horus', 'term': '荷魯斯之子'},
}


@public_route('/quiz')
def quiz_page():
    """陣營心理測驗 — result links to codex + that legion's products.
    Product link prefers the legion tag once products are tagged."""
    import posdb as _posdb
    all_tags = set()
    for prod in _posdb.get_products():
        all_tags.update(prod.get('tags') or [])
    results = {}
    for key, r in QUIZ_RESULTS.items():
        url = None
        if r['term']:
            url = (f"/products?tag={r['term']}" if r['term'] in all_tags
                   else f"/products?search={r['term']}")
        results[key] = {**r, 'products_url': url}
    return render_template('public/quiz.html', results=results)


@public_route('/checkout')
def checkout_page():
    member = current_member()
    addresses = memberdb.list_addresses(member['id']) if member else []
    return render_template('public/checkout.html', addresses=addresses)


@public_route('/checkout/success')
def checkout_success():
    return render_template('public/checkout-success.html',
                           bank_info=BANK_TRANSFER_INFO)


# ===== Membership: Google Sign-In + member area =====

import memberdb
memberdb.init()

# ----- product review photos (member-uploaded, site-owned) -----
# Stored alongside members.db under data/ so they survive deploys (deploy.sh
# ships code only, never data/). Served by /review-photo/<file>; the POS admin
# renders them via absolute URLs built from SITE_PUBLIC_URL.
REVIEW_PHOTOS_DIR = os.path.join(os.path.dirname(memberdb.DB_PATH), 'review_photos')
os.makedirs(REVIEW_PHOTOS_DIR, exist_ok=True)
REVIEW_PHOTO_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'heic', 'heif'}
MAX_REVIEW_PHOTOS = 4
SITE_PUBLIC_URL = os.environ.get('SITE_PUBLIC_URL', 'https://abbeystoys.com').rstrip('/')


def _process_review_photo(file_storage):
    """Validate + re-encode an uploaded review photo into a safe JPEG (strips
    EXIF/metadata, caps dimensions, neutralizes malicious payloads) plus a
    thumbnail. Returns the stored base filename (<hex>.jpg) or None on failure."""
    import uuid
    fn = (file_storage.filename or '').lower()
    ext = fn.rsplit('.', 1)[1] if '.' in fn else ''
    if ext not in REVIEW_PHOTO_EXTS:
        return None
    try:
        img = Image.open(file_storage.stream)
        img = img.convert('RGB')
        img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        base = uuid.uuid4().hex
        img.save(os.path.join(REVIEW_PHOTOS_DIR, base + '.jpg'),
                 'JPEG', quality=85, optimize=True)
        thumb = img.copy()
        thumb.thumbnail((400, 400), Image.Resampling.LANCZOS)
        thumb.save(os.path.join(REVIEW_PHOTOS_DIR, base + '_thumb.jpg'),
                   'JPEG', quality=82, optimize=True)
        return base + '.jpg'
    except Exception as e:
        print(f"review photo process failed: {e}")
        return None


def _review_photo_url(filename, thumb=False):
    """Absolute URL for a stored review photo (or its thumbnail)."""
    name = filename[:-4] + '_thumb.jpg' if thumb and filename.endswith('.jpg') else filename
    return f"{SITE_PUBLIC_URL}/review-photo/{name}"

GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')


def current_member():
    mid = session.get('member_id')
    return memberdb.get_member(mid) if mid else None


@app.context_processor
def inject_member():
    if request.path.startswith('/api'):
        return {}
    return {'member': current_member()}


@app.route('/auth/google')
def auth_google():
    import secrets
    from urllib.parse import urlencode
    if not GOOGLE_CLIENT_ID:
        return "Google 登入尚未設定", 503
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    session['link_mode'] = bool(request.args.get('link')) and bool(current_member())
    session['login_next'] = request.args.get('next') or request.referrer or '/'
    params = urlencode({
        'client_id': GOOGLE_CLIENT_ID,
        'redirect_uri': request.url_root.rstrip('/') + '/auth/google/callback',
        'response_type': 'code',
        'scope': 'openid email profile',
        'state': state,
        'prompt': 'select_account',
    })
    return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + params)


@app.route('/auth/google/callback')
def auth_google_callback():
    import urllib.request
    from urllib.parse import urlencode
    if request.args.get('state') != session.pop('oauth_state', None):
        return "登入驗證失敗，請重試", 400
    code = request.args.get('code')
    if not code:
        return redirect('/')
    body = urlencode({
        'code': code,
        'client_id': GOOGLE_CLIENT_ID,
        'client_secret': GOOGLE_CLIENT_SECRET,
        'redirect_uri': request.url_root.rstrip('/') + '/auth/google/callback',
        'grant_type': 'authorization_code',
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                'https://oauth2.googleapis.com/token', data=body), timeout=15) as resp:
            tokens = json.loads(resp.read())
        req = urllib.request.Request(
            'https://openidconnect.googleapis.com/v1/userinfo',
            headers={'Authorization': 'Bearer ' + tokens['access_token']})
        with urllib.request.urlopen(req, timeout=15) as resp:
            info = json.loads(resp.read())
    except Exception as e:
        print(f"google oauth failed: {e}")
        return "Google 登入失敗，請重試", 502
    current = current_member()
    if session.pop('link_mode', False) and current:
        result = memberdb.link_identity(
            current['id'], 'google', info['sub'],
            info.get('email'), info.get('name'), info.get('picture'))
        return redirect(f'/account?link={result}')
    member = memberdb.find_or_create_by_identity(
        'google', info['sub'], info.get('email'), info.get('name'), info.get('picture'))
    session.permanent = True
    session['member_id'] = member['id']
    return redirect(_auth_next(_safe_next(session.pop('login_next', '/')), member.get('_is_new'), 'google'))


LINE_LOGIN_CHANNEL_ID = os.environ.get('LINE_LOGIN_CHANNEL_ID', '')
LINE_LOGIN_CHANNEL_SECRET = os.environ.get('LINE_LOGIN_CHANNEL_SECRET', '')


@public_route('/login')
def login_page():
    if current_member():
        return redirect('/account')
    return render_template('public/login.html',
                           has_google=bool(GOOGLE_CLIENT_ID),
                           has_line=bool(LINE_LOGIN_CHANNEL_ID))


@app.route('/auth/line')
def auth_line():
    import secrets
    from urllib.parse import urlencode
    if not LINE_LOGIN_CHANNEL_ID:
        return "LINE 登入尚未設定", 503
    state = secrets.token_urlsafe(24)
    session['oauth_state'] = state
    session['link_mode'] = bool(request.args.get('link')) and bool(current_member())
    session['login_next'] = request.args.get('next') or request.referrer or '/'
    params = urlencode({
        'response_type': 'code',
        'client_id': LINE_LOGIN_CHANNEL_ID,
        'redirect_uri': request.url_root.rstrip('/') + '/auth/line/callback',
        'state': state,
        'scope': 'profile openid',
        'bot_prompt': 'aggressive',   # prompt adding the 官方帳號 as friend
    })
    return redirect('https://access.line.me/oauth2/v2.1/authorize?' + params)


@app.route('/auth/line/callback')
def auth_line_callback():
    import urllib.request
    from urllib.parse import urlencode
    if request.args.get('state') != session.pop('oauth_state', None):
        return "登入驗證失敗，請重試", 400
    code = request.args.get('code')
    if not code:
        return redirect('/')
    body = urlencode({
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': request.url_root.rstrip('/') + '/auth/line/callback',
        'client_id': LINE_LOGIN_CHANNEL_ID,
        'client_secret': LINE_LOGIN_CHANNEL_SECRET,
    }).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                'https://api.line.me/oauth2/v2.1/token', data=body), timeout=15) as resp:
            tokens = json.loads(resp.read())
        req = urllib.request.Request(
            'https://api.line.me/v2/profile',
            headers={'Authorization': 'Bearer ' + tokens['access_token']})
        with urllib.request.urlopen(req, timeout=15) as resp:
            prof = json.loads(resp.read())
    except Exception as e:
        print(f"line login failed: {e}")
        return "LINE 登入失敗，請重試", 502
    current = current_member()
    if session.pop('link_mode', False) and current:
        result = memberdb.link_identity(
            current['id'], 'line', prof['userId'],
            None, prof.get('displayName'), prof.get('pictureUrl'))
        memberdb.set_line_user(current['id'], prof['userId'])
        return redirect(f'/account?link={result}')
    member = memberdb.find_or_create_by_identity(
        'line', prof['userId'], None, prof.get('displayName'), prof.get('pictureUrl'))
    # LINE login binds notifications automatically
    memberdb.set_line_user(member['id'], prof['userId'])
    session.permanent = True
    session['member_id'] = member['id']
    return redirect(_auth_next(_safe_next(session.pop('login_next', '/')), member.get('_is_new'), 'line'))


@app.route('/auth/logout')
def auth_logout():
    session.pop('member_id', None)
    return redirect('/')


@public_route('/account')
def account_page():
    member = current_member()
    if not member:
        return redirect('/login?next=/account')
    import posdb as _posdb
    orders = _posdb.get_member_orders(member.get('email'), member.get('phone'))
    wish_skus = memberdb.wishlist_skus(member['id'])
    wish_products = []
    for prod in _posdb.get_products():
        if prod['id'] in wish_skus:
            wish_products.append(prod)
    notify = set(memberdb.notify_skus(member['id']))
    return render_template('public/account.html', member=member,
                           orders=orders, wish_products=wish_products,
                           notify_skus=notify, bank_info=BANK_TRANSFER_INFO,
                           addresses=memberdb.list_addresses(member['id']),
                           identities=memberdb.identities_for(member['id']),
                           line_bind_code=memberdb.get_bind_code(member['id']))


@app.route('/api/wishlist', methods=['POST'])
def api_wishlist():
    member = current_member()
    if not member:
        return jsonify({'error': 'login', 'login_url': '/login'}), 401
    sku = (request.get_json(silent=True) or {}).get('sku', '').strip()
    if not sku:
        return jsonify({'error': 'bad sku'}), 400
    added = memberdb.wishlist_toggle(member['id'], sku)
    return jsonify({'success': True, 'added': added})


@app.route('/api/notify', methods=['POST'])
def api_notify():
    member = current_member()
    if not member:
        return jsonify({'error': 'login', 'login_url': '/login'}), 401
    sku = (request.get_json(silent=True) or {}).get('sku', '').strip()
    if not sku:
        return jsonify({'error': 'bad sku'}), 400
    added = memberdb.notify_toggle(member['id'], sku)
    return jsonify({'success': True, 'added': added})


# ----- product reviews (商品評價) -----

@app.route('/review-photo/<path:filename>')
def review_photo(filename):
    """Serve a member-uploaded review photo from data/review_photos/."""
    name = os.path.basename(filename)
    if not name.endswith('.jpg'):
        return '', 404
    return send_from_directory(REVIEW_PHOTOS_DIR, name, max_age=86400)


@app.route('/api/reviews', methods=['POST'])
def api_submit_review():
    """Member submits (or edits) a product review. Multipart form: sku,
    category, slug, rating(1-5), title, body, photos[] (files), keep(csv of
    existing photo filenames to retain on edit). Lands as 'pending'."""
    member = current_member()
    if not member:
        return jsonify({'error': 'login', 'login_url': '/login'}), 401
    f = request.form
    sku = (f.get('sku') or '').strip()
    category = (f.get('category') or '').strip()
    slug = (f.get('slug') or '').strip()
    try:
        rating = int(f.get('rating') or 0)
    except (TypeError, ValueError):
        rating = 0
    if not sku or rating < 1 or rating > 5:
        return jsonify({'error': 'bad', 'message': '請給 1-5 星評分'}), 400
    title = (f.get('title') or '').strip()[:120]
    body = (f.get('body') or '').strip()[:4000]

    import posdb as _posdb
    product = _posdb.get_product(category, slug) if category and slug else None
    product_name = ((product or {}).get('zhtw_name')
                    or (product or {}).get('title') or sku)

    # verified purchase: does the member's order history contain this product?
    verified = False
    try:
        for o in _posdb.get_member_orders(member.get('email'), member.get('phone')):
            for it in o.get('items', []):
                if it.get('slug') == slug and it.get('category_slug') == category:
                    verified = True
                    break
            if verified:
                break
    except Exception as e:
        print(f"review verified-purchase check failed: {e}")

    # photos: keep chosen existing ones (validated against the member's own
    # current review), then append newly uploaded files up to the cap.
    existing = memberdb.get_review(member['id'], sku)
    allowed_keep = set(existing['photos']) if existing else set()
    photos = [p for p in (f.get('keep') or '').split(',') if p.strip() in allowed_keep]
    photo_errors = 0
    for fs in request.files.getlist('photos'):
        if not fs or not fs.filename:
            continue
        if len(photos) >= MAX_REVIEW_PHOTOS:
            break
        name = _process_review_photo(fs)
        if name:
            photos.append(name)
        else:
            photo_errors += 1

    rid = memberdb.save_review(member['id'], sku, {
        'category': category, 'slug': slug, 'product_name': product_name,
        'rating': rating, 'title': title, 'body': body, 'photos': photos,
        'verified_purchase': verified, 'author_name': member.get('name') or '會員',
    })
    if not rid:
        return jsonify({'error': 'save', 'message': '儲存失敗'}), 500
    msg = '感謝您的評價！送出後經審核就會顯示。'
    if photo_errors:
        msg += f'（{photo_errors} 張照片格式不支援，已略過）'
    return jsonify({'success': True, 'status': 'pending', 'message': msg})


def _review_api_dict(r):
    """Serialize a review row for the POS moderation API (absolute media URLs)."""
    return {
        'id': r['id'],
        'sku': r['sku'],
        'product_name': r.get('product_name'),
        'product_url': (f"{SITE_PUBLIC_URL}/products/{r['category']}/{r['slug']}"
                        if r.get('category') and r.get('slug') else None),
        'rating': r['rating'],
        'title': r.get('title'),
        'body': r.get('body'),
        'author_name': r.get('author_name'),
        'member_email': r.get('member_email'),
        'verified_purchase': bool(r.get('verified_purchase')),
        'status': r.get('status'),
        'created_at': r.get('created_at'),
        'reviewed_at': r.get('reviewed_at'),
        'photos': [_review_photo_url(p) for p in r.get('photos', [])],
        'thumbs': [_review_photo_url(p, thumb=True) for p in r.get('photos', [])],
    }


@app.route('/api/internal/reviews/pending', methods=['GET'])
def api_internal_reviews_pending():
    """POS moderation queue: reviews awaiting approval. Shared-secret auth."""
    if not _valid_storefront_key(request.headers.get('X-Storefront-Key')):
        return jsonify({'error': 'bad key'}), 401
    out = [_review_api_dict(r) for r in memberdb.pending_reviews()]
    return jsonify({'reviews': out, 'count': len(out)})


@app.route('/api/internal/reviews/list', methods=['GET'])
def api_internal_reviews_list():
    """POS review history: reviews by status (default all), newest first."""
    if not _valid_storefront_key(request.headers.get('X-Storefront-Key')):
        return jsonify({'error': 'bad key'}), 401
    status = (request.args.get('status') or 'all').strip().lower()
    if status not in ('all', 'pending', 'approved', 'rejected'):
        status = 'all'
    rows = memberdb.reviews_by_status(None if status == 'all' else status)
    out = [_review_api_dict(r) for r in rows]
    return jsonify({'reviews': out, 'count': len(out), 'status': status})


@app.route('/api/internal/reviews/<int:review_id>/<action>', methods=['POST'])
def api_internal_review_action(review_id, action):
    """POS moderation: approve or reject a pending review. Shared-secret auth."""
    if not _valid_storefront_key(request.headers.get('X-Storefront-Key')):
        return jsonify({'error': 'bad key'}), 401
    status = {'approve': 'approved', 'reject': 'rejected'}.get(action)
    if not status:
        return jsonify({'error': 'bad action'}), 400
    updated = memberdb.set_review_status(review_id, status)
    if not updated:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'success': True, 'status': updated['status']})


@app.route('/api/internal/notify', methods=['POST'])
def api_internal_notify():
    """POS -> customer notification. Resolves the best channel:
    member LINE binding (matched by phone/email) first, email fallback.
    Auth: same shared secret as the storefront API."""
    if not _valid_storefront_key(request.headers.get('X-Storefront-Key')):
        return jsonify({'error': 'bad key'}), 401
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()
    email = (data.get('email') or '').strip()
    message = (data.get('message') or '').strip()

    # email variants (LINE stays plain text; email gets branded HTML)
    email_subject = '[阿北玩具堂] 訂單通知'
    email_html = None
    email_text = None

    # optional server-side templates (site owns e.g. bank info)
    tmpl = data.get('template')
    if tmpl in ('order_confirmed', 'payment_received'):
        import mailer
        d = data.get('data') or {}
        order_no = d.get('order_no', '')
        pm = d.get('payment_method')
        pstatus = d.get('payment_status')
        bank = None
        if tmpl == 'order_confirmed':
            headline = f"訂單 {order_no} 已確認"
            paras = [f"總額 NT${int(d.get('grand_total', 0)):,}（含運費），已開始為您處理。"]
            if pm == 'transfer' and pstatus != '已付款':
                bank = BANK_TRANSFER_INFO
                paras.append("若尚未轉帳，請轉帳至下方帳戶，並回覆帳號後五碼（或到會員中心回報），確認入帳後出貨。")
            elif pm == 'cod':
                paras.append("將盡快為您安排出貨，到店取貨時付款即可。")
            elif pm == 'linepay':
                paras.append("感謝您的付款，將盡快為您安排出貨。")
            email_subject = f"[阿北玩具堂] 訂單確認 {order_no}"
        else:  # payment_received
            headline = f"已收到款項 — 訂單 {order_no}"
            paras = ["我們已確認收到您的款項，將盡快為您安排出貨，出貨後會再通知您。"]
            email_subject = f"[阿北玩具堂] 收到款項 {order_no}"
        line_lines = [headline] + paras
        if bank:
            line_lines.append(f"轉帳帳戶：{bank}")
        line_lines.append("— ABBEY'S TOYS 阿北玩具堂")
        message = "\n".join(line_lines)
        email_html = mailer.render_status_html(headline, paras, bank_info=bank, order_no=order_no)
        email_text = mailer.render_status_text(headline, paras, bank_info=bank)
    elif tmpl == 'quote_sent':
        import mailer
        d = data.get('data') or {}
        inquiry_no = d.get('inquiry_no', '')
        q_items = d.get('items') or []
        expires = d.get('expires_at', '')
        line_lines = [f"阿北玩具堂 報價回覆（{inquiry_no}）", ""]
        for it in q_items:
            qty = it.get('qty', 1)
            if it.get('status') == '無法供貨':
                line_lines.append(f"・{it.get('name', '商品')} x{qty}：無法供貨")
            elif it.get('price'):
                line_lines.append(f"・{it.get('name', '商品')} x{qty}：NT${int(it['price']):,}")
            else:
                line_lines.append(f"・{it.get('name', '商品')} x{qty}：—")
        if expires:
            line_lines += ["", f"報價有效至 {expires}。"]
        line_lines.append("請回覆想要的商品，阿北再幫您安排下單與付款。")
        line_lines.append("— ABBEY'S TOYS 阿北玩具堂")
        message = "\n".join(line_lines)
        email_subject = f"[阿北玩具堂] 報價回覆 {inquiry_no}"
        email_html = mailer.render_quote_html(inquiry_no, q_items, expires)
        email_text = mailer.render_quote_text(inquiry_no, q_items, expires)
    elif tmpl == 'return_update':
        import mailer
        d = data.get('data') or {}
        rno = d.get('request_no', '')
        ono = d.get('order_no', '')
        status = d.get('status', '')
        headline = f"退貨申請更新 — {rno}"
        if status == '申請中':
            headline = f"退貨申請已收到 — {rno}"
            paras = ["我們已收到您的退貨申請，會盡快為您處理，並在有進度時通知您。"]
        elif status == '處理中':
            paras = [f"您的退貨申請（訂單 {ono}）已受理，我們會盡快為您處理退款，完成後再通知您。"]
        elif status == '已退款':
            headline = f"退款完成 — {rno}"
            amt = d.get('refund_amount')
            line = "您的退款已完成" + (f"，退款金額 NT${int(amt):,}" if amt else "") + "。"
            paras = [line]
            if d.get('refund_note'):
                paras.append(d['refund_note'])
        elif status == '已拒絕':
            paras = ["很抱歉，您的退貨申請經確認後未能受理。"]
            if d.get('refund_note'):
                paras.append(f"原因：{d['refund_note']}")
            paras.append("如有疑問，歡迎直接回覆或用 LINE 聯絡阿北。")
        else:
            paras = [f"您的退貨申請 {rno} 狀態更新為 {status}。"]
        message = "\n".join([headline] + paras + ["— ABBEY'S TOYS 阿北玩具堂"])
        email_subject = f"[阿北玩具堂] {headline}"
        email_html = mailer.render_status_html(headline, paras, order_no=ono)
        email_text = mailer.render_status_text(headline, paras)
    elif tmpl == 'payment_due':
        import mailer
        d = data.get('data') or {}
        ono = d.get('order_no', '')
        pm = d.get('payment_method')
        amount = d.get('amount')
        headline = f"預購商品已到貨，請付款 — {ono}"
        order_link = f"{SITE_URL}/order/{ono}?t={_order_token(ono)}"
        amt_str = f" NT${int(amount):,}" if amount else ""
        paras = [f"您的預購商品已到貨！請完成付款{amt_str}，我們就會安排出貨。"]
        bank = None
        if pm == 'transfer':
            bank = BANK_TRANSFER_INFO
            paras.append("請轉帳至下方帳戶，並到訂單頁回報帳號後五碼。")
        elif pm == 'linepay':
            paras.append("請到訂單頁使用 LINE Pay 完成付款。")
        line_lines = [headline] + paras
        if bank:
            line_lines.append(f"轉帳帳戶：{bank}")
        line_lines.append(f"訂單頁：{order_link}")
        message = "\n".join(line_lines + ["— ABBEY'S TOYS 阿北玩具堂"])
        email_subject = f"[阿北玩具堂] 預購到貨請付款 {ono}"
        email_html = mailer.render_status_html(headline, paras, bank_info=bank,
                                               action_url=order_link, action_label='前往付款')
        email_text = mailer.render_status_text(headline, paras, bank_info=bank)
    elif tmpl == 'order_cancelled':
        import mailer
        d = data.get('data') or {}
        ono = d.get('order_no', '')
        headline = f"訂單已取消 — {ono}"
        paras = ["您的訂單已取消。如果這不是您本人操作或有疑問，歡迎直接回覆或用 LINE 聯絡阿北。"]
        message = "\n".join([headline] + paras + ["— ABBEY'S TOYS 阿北玩具堂"])
        email_subject = f"[阿北玩具堂] 訂單已取消 {ono}"
        email_html = mailer.render_status_html(headline, paras)
        email_text = mailer.render_status_text(headline, paras)

    if not message or not (phone or email):
        return jsonify({'success': False, 'error': 'need message and phone/email'}), 400

    # find a bound member by phone or email
    line_user_id = None
    member_email = None
    import sqlite3 as _sq
    conn = _sq.connect(memberdb.DB_PATH)
    conn.row_factory = _sq.Row
    row = None
    if phone:
        row = conn.execute("SELECT * FROM members WHERE phone = ?", (phone,)).fetchone()
    if not row and email:
        row = conn.execute("SELECT * FROM members WHERE email = ?", (email,)).fetchone()
    conn.close()
    if row:
        line_user_id = row['line_user_id']
        member_email = row['email']

    sent = []
    if line_user_id:
        try:
            import linepush
            if linepush.enabled():
                linepush.push_text(line_user_id, message)
                sent.append('line')
        except Exception as e:
            print(f"notify line push failed: {e}")
    if not sent:
        target = email or member_email
        if target:
            try:
                import mailer
                if email_html is None:
                    # raw message (no template) -> wrap in the branded shell
                    paras = [p for p in message.split('\n') if p.strip()]
                    email_html = mailer.render_status_html('訂單通知', paras)
                    email_text = mailer.render_status_text('訂單通知', paras)
                if mailer.send_email(target, email_subject, email_html, email_text or message):
                    sent.append('email')
            except Exception as e:
                print(f"notify email failed: {e}")
    return jsonify({'success': bool(sent), 'channels': sent,
                    'error': None if sent else '客戶未綁定 LINE 且無法寄送 email'})


@app.route('/api/internal/payuni-refund', methods=['POST'])
def api_payuni_refund():
    """POS -> reverse a PayUni charge (trade_close 退款). Auth: storefront key."""
    if not _valid_storefront_key(request.headers.get('X-Storefront-Key')):
        return jsonify({'error': 'bad key'}), 401
    import payuni
    if not payuni.enabled():
        return jsonify({'success': False, 'error': 'PayUni 未設定'}), 503
    data = request.get_json(silent=True) or {}
    trade_no = (data.get('trade_no') or '').strip()
    amount = int(data.get('amount') or 0)
    payment_type = str(data.get('payment_type') or '1')
    order_no = (data.get('order_no') or '').strip()
    if not trade_no or amount <= 0:
        return jsonify({'success': False, 'error': '缺少交易序號或金額'}), 400
    res = payuni.refund(trade_no, amount, payment_type)
    if res.get('needs_bank'):
        # ATM/超商: the buyer enters their bank account on PayUni's hosted page
        link = (f"{SITE_URL}/payuni/refund-page/{order_no}?t={_order_token(order_no)}"
                if order_no else '')
        return jsonify({'success': True, 'needs_bank': True, 'refund_url': link})
    print(f"[payuni refund] trade_no={trade_no} amt={amount} pt={payment_type} -> {res['status']} {res.get('message')}")
    return jsonify({'success': res['ok'], 'needs_bank': False, 'status': res['status'],
                    'message': res.get('message', ''),
                    'error': None if res['ok'] else (res.get('message') or res['status'])})


@app.route('/line/webhook', methods=['POST'])
def line_webhook():
    """LINE 官方帳號 webhook: binds members via their binding code."""
    import linepush
    body = request.get_data()
    if not linepush.valid_signature(body, request.headers.get('X-Line-Signature', '')):
        return 'bad signature', 403
    events = (request.get_json(silent=True) or {}).get('events', [])
    for ev in events:
        try:
            if ev.get('type') == 'follow':
                linepush.reply_text(ev['replyToken'],
                    '歡迎加入阿北玩具堂！\n\n如果您是網站會員，到會員中心取得「綁定碼」並傳給我，'
                    f'之後到貨通知、訂單通知都會從這裡傳給您。\n\n{SITE_URL}/account')
            elif ev.get('type') == 'message' and ev.get('message', {}).get('type') == 'text':
                text = ev['message']['text'].strip().upper()
                if text.startswith('AB') and len(text) == 8:
                    member = memberdb.bind_line_user(text, ev['source']['userId'])
                    if member:
                        linepush.reply_text(ev['replyToken'],
                            f"綁定成功！{member.get('name') or ''} 您好，"
                            '之後到貨與訂單通知都會傳到這裡。')
                    else:
                        linepush.reply_text(ev['replyToken'],
                            f'找不到這個綁定碼，請到會員中心確認：{SITE_URL}/account')
        except Exception as e:
            print(f'line webhook event failed: {e}')
    return 'OK'


@app.route('/api/account/line-unbind', methods=['POST'])
def api_line_unbind():
    member = current_member()
    if not member:
        return jsonify({'error': 'login'}), 401
    memberdb.unbind_line(member['id'])
    return jsonify({'success': True})


@app.route('/api/account/addresses', methods=['POST'])
def api_save_address():
    member = current_member()
    if not member:
        return jsonify({'error': 'login'}), 401
    data = request.get_json(silent=True) or {}
    if data.get('delivery') in ('711', 'fami') and not data.get('store_code'):
        return jsonify({'success': False, 'error': '請選擇門市'}), 400
    if data.get('delivery') == 'post' and not (data.get('address') or '').strip():
        return jsonify({'success': False, 'error': '請填寫地址'}), 400
    addr_id = memberdb.save_address(member['id'], data, data.get('id'))
    if not addr_id:
        return jsonify({'success': False, 'error': '儲存失敗'}), 400
    return jsonify({'success': True, 'id': addr_id})


@app.route('/api/account/addresses/<int:addr_id>/delete', methods=['POST'])
def api_delete_address(addr_id):
    member = current_member()
    if not member:
        return jsonify({'error': 'login'}), 401
    memberdb.delete_address(member['id'], addr_id)
    return jsonify({'success': True})


@app.route('/api/account/addresses/<int:addr_id>/default', methods=['POST'])
def api_default_address(addr_id):
    member = current_member()
    if not member:
        return jsonify({'error': 'login'}), 401
    memberdb.set_default_address(member['id'], addr_id)
    return jsonify({'success': True})


@app.route('/api/account/profile', methods=['POST'])
def api_account_profile():
    member = current_member()
    if not member:
        return jsonify({'error': 'login'}), 401
    data = request.get_json(silent=True) or {}
    phone = (data.get('phone') or '').strip()
    if phone and not phone.replace('+', '').replace('-', '').replace(' ', '').isdigit():
        return jsonify({'success': False, 'error': '電話格式不正確'}), 400
    memberdb.update_profile(member['id'], {
        'name': data.get('name'),
        'phone': phone,
        'line_id': data.get('line_id'),
        'default_delivery': data.get('default_delivery')
            if data.get('default_delivery') in ('711', 'fami', 'post', '') else None,
        'default_store_code': data.get('default_store_code'),
        'default_store_name': data.get('default_store_name'),
        'default_address': data.get('default_address'),
    })
    return jsonify({'success': True})


def _order_token(order_no):
    """Stateless magic-link token for an order (guest self-service)."""
    import hmac, hashlib
    return hmac.new(app.secret_key.encode(),
                    (order_no or '').encode(), hashlib.sha256).hexdigest()[:20]


def _authorized_for_order(order_no, token=None):
    """Access to an order: a valid magic-link token, OR a logged-in member
    whose email/phone matches the order."""
    if not order_no:
        return False
    import hmac
    if token and hmac.compare_digest(token, _order_token(order_no)):
        return True
    member = current_member()
    if member:
        import posdb as _posdb
        return any(o['order_no'] == order_no for o in
                   _posdb.get_member_orders(member.get('email'), member.get('phone')))
    return False


@app.route('/api/account/report-transfer', methods=['POST'])
def api_report_transfer():
    data = request.get_json(silent=True) or {}
    order_no = (data.get('order_no') or '').strip()
    digits = (data.get('digits') or '').strip()
    if not order_no or not digits.isdigit() or len(digits) != 5:
        return jsonify({'success': False, 'error': '請輸入 5 位數字'}), 400
    if not _authorized_for_order(order_no, data.get('token')):
        return jsonify({'success': False, 'error': '找不到這筆訂單'}), 403
    try:
        _pos_api('POST', f'/api/storefront/orders/{order_no}/payment',
                 {'payment_status': '待確認', 'payment_note': f'後五碼 {digits}'})
    except Exception as e:
        print(f"report transfer failed: {e}")
        return jsonify({'success': False, 'error': '回報失敗，請稍後再試'}), 502
    return jsonify({'success': True})


@app.route('/api/account/return-request', methods=['POST'])
def api_return_request():
    import urllib.error
    data = request.get_json(silent=True) or {}
    order_no = (data.get('order_no') or '').strip()
    items = data.get('items') or []
    if not order_no or not items:
        return jsonify({'success': False, 'error': '請選擇訂單與商品'}), 400
    if not _authorized_for_order(order_no, data.get('token')):
        return jsonify({'success': False, 'error': '找不到這筆訂單'}), 403
    try:
        resp = _pos_api('POST', '/api/storefront/returns', {
            'order_no': order_no,
            'reason': (data.get('reason') or '').strip(),
            'note': (data.get('note') or '').strip(),
            'items': [{'sku': i.get('sku'), 'qty': int(i.get('qty') or 1)} for i in items],
        })
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get('detail', '申請失敗')
        except Exception:
            detail = '申請失敗'
        return jsonify({'success': False, 'error': detail}), 400
    except Exception as e:
        print(f"return request failed: {e}")
        return jsonify({'success': False, 'error': '系統忙碌中，請稍後再試'}), 502
    # alert the shop of a new return request (best-effort)
    try:
        import mailer
        shop = os.environ.get('SHOP_EMAIL',
                              os.environ.get('SMTP_FROM') or os.environ.get('SMTP_USERNAME'))
        rno = resp.get('request_no')
        if shop and rno:
            paras = [f"訂單 {order_no} 有新的退貨申請（{rno}）。",
                     "請到 網站退貨 頁面受理／退款。"]
            mailer.send_email(shop, f"[阿北玩具堂] 新退貨申請 {rno}",
                              mailer.render_status_html(f"新退貨申請 {rno}", paras),
                              mailer.render_status_text(f"新退貨申請 {rno}", paras))
    except Exception as e:
        print(f"return shop alert failed: {e}")
    return jsonify(resp)


@app.route('/api/account/cancel-order', methods=['POST'])
def api_cancel_order():
    import urllib.error
    data = request.get_json(silent=True) or {}
    order_no = (data.get('order_no') or '').strip()
    if not order_no:
        return jsonify({'success': False, 'error': '缺少訂單編號'}), 400
    if not _authorized_for_order(order_no, data.get('token')):
        return jsonify({'success': False, 'error': '找不到這筆訂單'}), 403
    try:
        resp = _pos_api('POST', f'/api/storefront/orders/{order_no}/cancel')
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get('detail', '取消失敗')
        except Exception:
            detail = '取消失敗'
        return jsonify({'success': False, 'error': detail}), 400
    except Exception as e:
        print(f"cancel order failed: {e}")
        return jsonify({'success': False, 'error': '系統忙碌中，請稍後再試'}), 502
    return jsonify(resp)


@app.route('/api/order/linepay-init', methods=['POST'])
def api_order_linepay_init():
    """(Re)start LINE Pay for a 待付款 order from the order page — used after a
    failed LINE Pay, or a LINE Pay preorder once payment is due. Uses the POS's
    charge amount so the confirm step matches."""
    import linepay
    data = request.get_json(silent=True) or {}
    order_no = (data.get('order_no') or '').strip()
    if not _authorized_for_order(order_no, data.get('token')):
        return jsonify({'success': False, 'error': '找不到這筆訂單'}), 403
    try:
        info = _pos_api('GET', f'/api/storefront/orders/{order_no}')
    except Exception:
        return jsonify({'success': False, 'error': '系統忙碌中，請稍後再試'}), 502
    if info.get('payment_status') != '待付款':
        return jsonify({'success': False, 'error': '此訂單目前無法以 LINE Pay 付款'}), 400
    charge = int(info.get('charge_twd') or 0)
    if not linepay.enabled() or charge <= 0:
        return jsonify({'success': False, 'error': 'LINE Pay 暫時無法使用，請改用轉帳或聯絡阿北'}), 400
    try:
        base = request.url_root.rstrip('/')
        pay_url, txn = linepay.request_payment(
            order_no, charge, f"阿北玩具堂訂單 {order_no}",
            f"{base}/linepay/confirm",
            f"{base}/linepay/cancel?orderId={order_no}")
        return jsonify({'success': True, 'payment_url': pay_url})
    except Exception as e:
        print(f"order linepay init failed: {e}")
        return jsonify({'success': False, 'error': 'LINE Pay 啟動失敗'}), 502


@app.route('/order/<order_no>')
def guest_order_page(order_no):
    """View/manage a single order without login (magic-link token or member)."""
    token = request.args.get('t', '')
    if not _authorized_for_order(order_no, token):
        return redirect('/order-lookup?no=' + (order_no or ''))
    import posdb as _posdb
    order = _posdb.get_web_order(order_no)
    if not order:
        return redirect('/order-lookup')
    return render_template('public/order.html', order=order,
                           token=_order_token(order_no), bank_info=BANK_TRANSFER_INFO)


@app.route('/order-lookup', methods=['GET', 'POST'])
def order_lookup():
    """Guest order lookup: order number + the email/phone used at checkout.
    Order numbers are sequential, so throttle guesses per IP."""
    error = None
    prefill = (request.args.get('no') or '').strip()
    if request.method == 'POST':
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(',')[0].strip()
        if login_limiter.is_locked(client_ip):
            remaining = login_limiter.get_remaining_lockout(client_ip)
            error = f'嘗試次數過多，請於 {remaining // 60 + 1} 分鐘後再試。'
            return render_template('public/order-lookup.html', error=error, prefill=prefill), 429

        order_no = (request.form.get('order_no') or '').strip()
        contact = (request.form.get('contact') or '').strip()
        import posdb as _posdb
        order = _posdb.get_web_order(order_no) if order_no else None
        matched = bool(order) and bool(contact) and (
            hmac.compare_digest(contact, order.get('email') or '')
            or hmac.compare_digest(contact, order.get('phone') or ''))
        if matched:
            login_limiter.clear(client_ip)
            return redirect('/order/' + order_no + '?t=' + _order_token(order_no))
        login_limiter.record_failure(client_ip)
        error = '找不到符合的訂單，請確認訂單編號與 email／電話。'
        prefill = order_no
    return render_template('public/order-lookup.html', error=error, prefill=prefill)


# ===== POS-DB data layer (realtime) =====
# The POS SQLite DB is now the source of truth; posdb.py mirrors the dict
# shapes of the flat-file loaders above, so we simply rebind the names.
# The flat-file implementations remain above for reference/rollback.
import posdb as _posdb

get_products = _posdb.get_products
get_product = _posdb.get_product
get_categories = _posdb.get_categories
get_category = _posdb.get_category
get_featured_products_refs = _posdb.get_featured_products_refs
get_featured_tags = _posdb.get_featured_tags
get_blog_posts = _posdb.get_blog_posts
get_blog_post = _posdb.get_blog_post
get_codex_entries = _posdb.get_codex_entries
get_codex_entry = _posdb.get_codex_entry
get_promotions = _posdb.get_promotions
get_promotion = _posdb.get_promotion
get_active_promotion = _posdb.get_active_promotion
get_page = _posdb.get_page
get_tag_glossary = _posdb.get_tag_glossary


@app.template_filter('tag_label')
def tag_label_filter(tag):
    """Display a tag in zh-TW (via the tag_glossary) on the default site,
    keep the English key everywhere else (filter links, /en). Falls back to
    the raw tag when there's no mapping."""
    from flask import g
    if not tag or getattr(g, 'locale', 'zhtw') != 'zhtw':
        return tag
    return _posdb.get_tag_glossary().get(tag, tag)


@app.errorhandler(404)
def not_found(e):
    """Branded, localized 404 page."""
    return render_template('public/404.html'), 404


if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=5006)
