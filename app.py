import os
import json
import re
import time
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
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
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
        'welcome': 'Welcome to Warpmonger',
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
        'welcome': '歡迎來到 Warpmonger',
        'tagline': '精品模型公仔',
        'hero_subtitle': '精品模型公仔與收藏品',
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
    """Register a route for both EN and ZH-TW locales."""
    def decorator(f):
        app.add_url_rule(rule, view_func=f, **options)
        zhtw_endpoint = options.get('endpoint', f.__name__) + '_zhtw'
        app.add_url_rule('/zhtw' + rule, view_func=f, endpoint=zhtw_endpoint, **options)
        return f
    return decorator

@app.before_request
def detect_locale():
    from flask import g
    g.locale = 'zhtw' if request.path.startswith('/zhtw') else 'en'

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
        't': TRANSLATIONS.get(locale, TRANSLATIONS['en']),
        'url_prefix': '/zhtw' if is_zhtw else '',
    }

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
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
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

# ===== Authentication =====

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def load_users():
    """Load users from JSON file"""
    if not os.path.exists(USERS_FILE):
        # Create default admin user
        default_users = {
            'admin': {
                'password_hash': generate_password_hash('admin123'),
                'role': 'admin'
            }
        }
        save_users(default_users)
        return default_users

    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_users(users):
    """Save users to JSON file"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, indent=2)

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

def process_codex_links(text):
    """Convert [[term]] syntax to codex links"""
    from flask import g
    locale = getattr(g, 'locale', 'en')
    prefix = '/zhtw' if locale == 'zhtw' else ''
    codex_lookup = build_codex_lookup()

    def replace_codex_link(match):
        term = match.group(1)
        term_lower = term.lower()

        if term_lower in codex_lookup:
            slug = codex_lookup[term_lower]
            return f'<a href="{prefix}/codex/{slug}" class="codex-term" data-codex="{slug}">{term}</a>'
        else:
            # Term not found in codex, just return the text without brackets
            return term

    # Match [[anything]]
    pattern = r'\[\[([^\]]+)\]\]'
    return re.sub(pattern, replace_codex_link, text)

# ===== Routes - Public =====

@public_route('/')
def home():
    """Homepage"""
    all_products = get_products()

    # Get featured products (manually selected) or fallback to first 8
    featured = get_featured_products_for_homepage()
    if not featured:
        featured = all_products[:8]

    # Get special sections
    new_arrivals = [p for p in all_products if p.get('is_new_arrival', False)][:4]
    on_sale = [p for p in all_products if p.get('is_on_sale', False)][:4]

    posts = get_blog_posts()[:3]  # Recent posts
    featured_tags = get_featured_tags()
    active_promo = get_active_promotion()
    return render_template('public/home.html',
                         products=featured,
                         new_arrivals=new_arrivals,
                         on_sale=on_sale,
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
    show_on_sale = request.args.get('on_sale') == 'true'
    show_new_arrival = request.args.get('new_arrival') == 'true'
    show_in_stock = request.args.get('in_stock') == 'true'
    sort_by = request.args.get('sort', 'default')  # default, price_asc, price_desc

    # Check HTML cache for simple category pages (no search/tag/filters)
    from flask import g
    locale = getattr(g, 'locale', 'en')
    is_simple_page = not tag and not search and not show_pre_order and not show_on_sale and not show_new_arrival and not show_in_stock and sort_by == 'default'
    cache_key = f"html_products_{locale}_{category or 'all'}"

    if is_simple_page:
        cached_html = html_cache.get(cache_key)
        if cached_html:
            return cached_html

    # Get products with search filter
    products = get_products(category, search if search else None)

    # Filter by tag if specified
    if tag:
        products = [p for p in products if tag in p.get('tags', [])]

    # Filter by pre-order if specified
    if show_pre_order:
        products = [p for p in products if p.get('is_pre_order', False)]

    # Filter by on-sale if specified
    if show_on_sale:
        products = [p for p in products if p.get('is_on_sale', False)]

    # Filter by new arrival if specified
    if show_new_arrival:
        products = [p for p in products if p.get('is_new_arrival', False)]

    # Filter by in stock if specified
    if show_in_stock:
        products = [p for p in products if p.get('in_stock', True)]

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
                         show_on_sale=show_on_sale,
                         show_new_arrival=show_new_arrival,
                         show_in_stock=show_in_stock,
                         current_sort=sort_by)

    # Cache simple pages
    if is_simple_page:
        html_cache.set(cache_key, html)

    return html

@public_route('/products/<category>/<slug>')
def product_detail(category, slug):
    """Product detail page"""
    product = get_product(category, slug)
    if not product:
        return "Product not found", 404

    # Process codex links first, then convert markdown to HTML
    description_with_codex = process_codex_links(product['description'])
    product['description_html'] = markdown.markdown(description_with_codex)

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

    return render_template('public/product-detail.html',
                         product=product,
                         category_name=category_name,
                         related=related)

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

    # Convert markdown to HTML
    entry['content_html'] = markdown.markdown(entry['content'])

    # Get all entries for navigation
    all_entries = get_codex_entries()

    return render_template('public/codex-entry.html', entry=entry, all_entries=all_entries)

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
    shop_email = os.environ.get('SHOP_EMAIL', smtp_user)

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
        msg_shop['From'] = smtp_user
        msg_shop['To'] = shop_email
        msg_shop['Reply-To'] = user_email
        msg_shop.attach(MIMEText(text_content, 'plain'))
        msg_shop.attach(MIMEText(html_content, 'html'))
        server.send_message(msg_shop)

        # Email 2: Send confirmation to user
        msg_user = MIMEMultipart('alternative')
        msg_user['Subject'] = 'Your Warpmonger Shopping List - We received your inquiry!'
        msg_user['From'] = smtp_user
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
    """Generate dynamic sitemap"""
    from flask import Response

    pages = []

    # Homepage
    pages.append({
        'loc': request.url_root,
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '1.0'
    })

    # Products page
    pages.append({
        'loc': request.url_root + 'products',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'daily',
        'priority': '0.9'
    })

    # All products
    products = get_products()
    for product in products:
        product_path = os.path.join(PRODUCTS_DIR, product['category'], product['slug'], 'product.md')
        if os.path.exists(product_path):
            mtime = os.path.getmtime(product_path)
            lastmod = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        else:
            lastmod = datetime.now().strftime('%Y-%m-%d')

        pages.append({
            'loc': f"{request.url_root}products/{product['category']}/{product['slug']}",
            'lastmod': lastmod,
            'changefreq': 'weekly',
            'priority': '0.8'
        })

    # Blog page
    pages.append({
        'loc': request.url_root + 'blog',
        'lastmod': datetime.now().strftime('%Y-%m-%d'),
        'changefreq': 'weekly',
        'priority': '0.7'
    })

    # All blog posts
    posts = get_blog_posts()
    for post in posts:
        post_path = os.path.join(BLOG_DIR, f"{post['slug']}.md")
        if os.path.exists(post_path):
            mtime = os.path.getmtime(post_path)
            lastmod = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        else:
            lastmod = post.get('date', datetime.now().strftime('%Y-%m-%d'))

        pages.append({
            'loc': f"{request.url_root}blog/{post['slug']}",
            'lastmod': lastmod,
            'changefreq': 'monthly',
            'priority': '0.6'
        })

    # Static pages (policy / info)
    for page_slug in ALLOWED_PAGES:
        page_path = os.path.join(PAGES_DIR, f'{page_slug}.md')
        if os.path.exists(page_path):
            mtime = os.path.getmtime(page_path)
            lastmod = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        else:
            lastmod = datetime.now().strftime('%Y-%m-%d')
        pages.append({
            'loc': f"{request.url_root}page/{page_slug}",
            'lastmod': lastmod,
            'changefreq': 'monthly',
            'priority': '0.4'
        })

    # Generate XML with hreflang alternates
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'

    for page in pages:
        # EN version
        xml += '  <url>\n'
        xml += f'    <loc>{page["loc"]}</loc>\n'
        xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        # Build the zhtw loc by inserting /zhtw after the root
        en_loc = page["loc"]
        zhtw_loc = en_loc.replace(request.url_root, request.url_root + 'zhtw/', 1)
        xml += f'    <xhtml:link rel="alternate" hreflang="en" href="{en_loc}"/>\n'
        xml += f'    <xhtml:link rel="alternate" hreflang="zh-TW" href="{zhtw_loc}"/>\n'
        xml += '  </url>\n'

        # ZH-TW version
        xml += '  <url>\n'
        xml += f'    <loc>{zhtw_loc}</loc>\n'
        xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
        xml += f'    <xhtml:link rel="alternate" hreflang="en" href="{en_loc}"/>\n'
        xml += f'    <xhtml:link rel="alternate" hreflang="zh-TW" href="{zhtw_loc}"/>\n'
        xml += '  </url>\n'

    xml += '</urlset>'

    return Response(xml, mimetype='application/xml')

@app.route('/sitemap-images.xml')
def sitemap_images():
    """Generate image sitemap for better image search indexing"""
    from flask import Response

    products = get_products()

    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">\n'

    for product in products:
        if product.get('images'):
            xml += '  <url>\n'
            xml += f'    <loc>{request.url_root}products/{product["category"]}/{product["slug"]}</loc>\n'

            for image in product['images'][:10]:  # Max 10 images per product
                if not image.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):  # Skip videos
                    image_url = f'{request.url_root}static/images/products/{product["category"]}/{product["slug"]}/{image}'
                    xml += '    <image:image>\n'
                    xml += f'      <image:loc>{image_url}</image:loc>\n'
                    xml += f'      <image:title>{product["title"]}</image:title>\n'
                    xml += f'      <image:caption>{product["title"]} - Premium action figure</image:caption>\n'
                    xml += '    </image:image>\n'

            xml += '  </url>\n'

    xml += '</urlset>'

    return Response(xml, mimetype='application/xml')

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

# ===== Routes - Admin =====

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    # Get client IP (supports reverse proxy)
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if client_ip:
        client_ip = client_ip.split(',')[0].strip()

    if request.method == 'POST':
        # Check if IP is locked out
        if login_limiter.is_locked(client_ip):
            remaining = login_limiter.get_remaining_lockout(client_ip)
            return jsonify({
                'success': False,
                'error': f'Too many failed attempts. Try again in {remaining // 60} minutes.'
            }), 429

        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        users = load_users()

        if username in users and check_password_hash(users[username]['password_hash'], password):
            login_limiter.clear(client_ip)  # Clear on successful login
            session['username'] = username
            return jsonify({'success': True})

        # Record failed attempt
        now_locked = login_limiter.record_failure(client_ip)
        if now_locked:
            return jsonify({
                'success': False,
                'error': 'Too many failed attempts. Locked out for 15 minutes.'
            }), 429

        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401

    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    """Admin logout"""
    session.pop('username', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@login_required
def admin_dashboard():
    """Admin dashboard"""
    return render_template('admin/dashboard.html')

@app.route('/api/admin/clear-cache', methods=['POST'])
@login_required
def api_clear_cache():
    """Clear all caches"""
    cache.invalidate()
    html_cache.invalidate()
    return jsonify({'success': True, 'message': 'Cache cleared'})

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

@app.route('/api/products', methods=['POST'])
@login_required
def api_create_product():
    """Create new product"""
    data = request.get_json()

    category = data.get('category')
    title = data.get('title')

    if not category or not title:
        return jsonify({'error': 'Category and title required'}), 400

    slug = slugify(title)

    # Check if already exists
    if get_product(category, slug):
        return jsonify({'error': 'Product already exists'}), 400

    save_product(category, slug, data)

    return jsonify({'success': True, 'slug': slug, 'category': category})

@app.route('/api/products/<category>/<slug>', methods=['PUT'])
@login_required
def api_update_product(category, slug):
    """Update product"""
    data = request.get_json()

    if not get_product(category, slug):
        return jsonify({'error': 'Product not found'}), 404

    save_product(category, slug, data)

    return jsonify({'success': True})

@app.route('/api/products/<category>/<slug>', methods=['DELETE'])
@login_required
def api_delete_product(category, slug):
    """Delete product"""
    product_path = os.path.join(PRODUCTS_DIR, category, slug)

    if not os.path.exists(product_path):
        return jsonify({'error': 'Product not found'}), 404

    import shutil
    shutil.rmtree(product_path)

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()
    return jsonify({'success': True})

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

@app.route('/api/categories', methods=['POST'])
@login_required
def api_create_category():
    """Create new category"""
    data = request.get_json()

    name = data.get('name')
    if not name:
        return jsonify({'error': 'Name required'}), 400

    slug = slugify(name)

    # Check if already exists
    if get_category(slug):
        return jsonify({'error': 'Category already exists'}), 400

    save_category(slug, data)

    return jsonify({'success': True, 'slug': slug})

@app.route('/api/categories/<slug>', methods=['PUT'])
@login_required
def api_update_category(slug):
    """Update category"""
    data = request.get_json()

    if not get_category(slug):
        return jsonify({'error': 'Category not found'}), 404

    save_category(slug, data)

    return jsonify({'success': True})

@app.route('/api/categories/<slug>', methods=['DELETE'])
@login_required
def api_delete_category(slug):
    """Delete category"""
    if not get_category(slug):
        return jsonify({'error': 'Category not found'}), 404

    # Check if category has products
    products_in_category = get_products(category=slug)
    if products_in_category:
        return jsonify({'error': f'Cannot delete category with {len(products_in_category)} products'}), 400

    delete_category(slug)

    return jsonify({'success': True})

@app.route('/api/categories/<slug>/upload-icon', methods=['POST'])
@login_required
def api_upload_category_icon(slug):
    """Upload category icon"""
    if 'icon' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['icon']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Create category images directory
        images_dir = os.path.join(CATEGORIES_DIR, slug, 'images')
        os.makedirs(images_dir, exist_ok=True)

        # Save file
        filepath = os.path.join(images_dir, filename)
        file.save(filepath)

        # Update category.md with the new icon
        category = get_category(slug)
        if category:
            category['icon'] = filename
            save_category(slug, category)

        # Return relative URL
        icon_url = f"/static/images/categories/{slug}/{filename}"

        return jsonify({
            'success': True,
            'filename': filename,
            'url': icon_url
        })

    return jsonify({'error': 'Invalid file type'}), 400

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

@app.route('/api/blog', methods=['POST'])
@login_required
def api_create_blog_post():
    """Create new blog post"""
    data = request.get_json()

    title = data.get('title')
    if not title:
        return jsonify({'error': 'Title required'}), 400

    slug = slugify(title)

    # Check if already exists
    if get_blog_post(slug):
        return jsonify({'error': 'Post already exists'}), 400

    save_blog_post(slug, data)

    return jsonify({'success': True, 'slug': slug})

@app.route('/api/blog/<slug>', methods=['PUT'])
@login_required
def api_update_blog_post(slug):
    """Update blog post"""
    data = request.get_json()

    if not get_blog_post(slug):
        return jsonify({'error': 'Post not found'}), 404

    save_blog_post(slug, data)

    return jsonify({'success': True})

@app.route('/api/blog/<slug>', methods=['DELETE'])
@login_required
def api_delete_blog_post(slug):
    """Delete blog post"""
    filepath = os.path.join(BLOG_DIR, f"{slug}.md")

    if not os.path.exists(filepath):
        return jsonify({'error': 'Post not found'}), 404

    os.remove(filepath)

    return jsonify({'success': True})

@app.route('/api/blog/upload-image', methods=['POST'])
@login_required
def api_upload_blog_image():
    """Upload image for blog post"""
    if 'image' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Store in static/images/blog/
        images_dir = os.path.join(app.static_folder, 'images', 'blog')
        os.makedirs(images_dir, exist_ok=True)

        # Add timestamp to avoid filename conflicts
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(time.time())}{ext}"

        filepath = os.path.join(images_dir, filename)
        file.save(filepath)

        image_url = f"/static/images/blog/{filename}"
        return jsonify({'success': True, 'url': image_url})

    return jsonify({'error': 'Invalid file type'}), 400

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

@app.route('/api/promotions', methods=['POST'])
@login_required
def api_create_promotion():
    """Create new promotion"""
    data = request.get_json()

    title = data.get('title')
    if not title:
        return jsonify({'error': 'Title required'}), 400

    slug = slugify(title)

    # Check if already exists
    if get_promotion(slug):
        return jsonify({'error': 'Promotion already exists'}), 400

    save_promotion(slug, data)

    return jsonify({'success': True, 'slug': slug})

@app.route('/api/promotions/<slug>', methods=['PUT'])
@login_required
def api_update_promotion(slug):
    """Update promotion"""
    data = request.get_json()

    if not get_promotion(slug):
        return jsonify({'error': 'Promotion not found'}), 404

    save_promotion(slug, data)

    return jsonify({'success': True})

@app.route('/api/promotions/<slug>', methods=['DELETE'])
@login_required
def api_delete_promotion(slug):
    """Delete promotion"""
    import shutil
    promo_dir = os.path.join(PROMOTIONS_DIR, slug)

    if not os.path.exists(promo_dir):
        return jsonify({'error': 'Promotion not found'}), 404

    shutil.rmtree(promo_dir)

    return jsonify({'success': True})

@app.route('/api/promotions/upload-banner', methods=['POST'])
@login_required
def api_upload_promotion_banner():
    """Upload banner image for promotion"""
    if 'image' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    slug = request.form.get('slug')
    if not slug:
        return jsonify({'error': 'Slug required'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        # Get file extension
        ext = file.filename.rsplit('.', 1)[1].lower()

        # Store in static/images/promotions/{slug}/
        images_dir = os.path.join(app.static_folder, 'images', 'promotions', slug)
        os.makedirs(images_dir, exist_ok=True)

        # Remove old banners if exist
        for old_file in os.listdir(images_dir):
            if old_file.startswith('banner.'):
                os.remove(os.path.join(images_dir, old_file))

        # Save as banner.{timestamp}.{ext} to avoid caching
        filename = f'banner.{int(time.time())}.{ext}'
        filepath = os.path.join(images_dir, filename)
        file.save(filepath)

        image_url = f"/static/images/promotions/{slug}/{filename}"
        return jsonify({'success': True, 'url': image_url})

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/promotions/upload-image', methods=['POST'])
@login_required
def api_upload_promotion_image():
    """Upload content image for promotion"""
    if 'image' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Store in static/images/promotions/
        images_dir = os.path.join(app.static_folder, 'images', 'promotions')
        os.makedirs(images_dir, exist_ok=True)

        # Add timestamp to avoid filename conflicts
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{int(time.time())}{ext}"

        filepath = os.path.join(images_dir, filename)
        file.save(filepath)

        image_url = f"/static/images/promotions/{filename}"
        return jsonify({'success': True, 'url': image_url})

    return jsonify({'error': 'Invalid file type'}), 400

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

@app.route('/api/codex', methods=['POST'])
@login_required
def api_create_codex_entry():
    """Create new codex entry"""
    data = request.get_json()

    title = data.get('title')
    if not title:
        return jsonify({'error': 'Title required'}), 400

    slug = slugify(title)

    # Check if already exists
    if get_codex_entry(slug):
        return jsonify({'error': 'Entry already exists'}), 400

    save_codex_entry(slug, data)

    return jsonify({'success': True, 'slug': slug})

@app.route('/api/codex/<slug>', methods=['PUT'])
@login_required
def api_update_codex_entry(slug):
    """Update codex entry"""
    data = request.get_json()

    if not get_codex_entry(slug):
        return jsonify({'error': 'Entry not found'}), 404

    save_codex_entry(slug, data)

    return jsonify({'success': True})

@app.route('/api/codex/<slug>', methods=['DELETE'])
@login_required
def api_delete_codex_entry(slug):
    """Delete codex entry"""
    filepath = os.path.join(CODEX_DIR, f"{slug}.md")

    if not os.path.exists(filepath):
        return jsonify({'error': 'Entry not found'}), 404

    os.remove(filepath)

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()
    return jsonify({'success': True})

# ===== API Routes - Tags =====

@app.route('/api/tags', methods=['GET'])
@login_required
def api_get_tags():
    """Get all tags with their products"""
    tags = get_all_tags()
    products = get_products()

    # Build tag -> products mapping
    tag_products = {}
    for tag in tags:
        tag_name = tag['name']
        tag_products[tag_name] = []
        for product in products:
            if tag_name in product.get('tags', []):
                tag_products[tag_name].append({
                    'slug': product['slug'],
                    'category': product['category'],
                    'title': product['title']
                })

    result = []
    for tag in tags:
        result.append({
            'name': tag['name'],
            'count': tag['count'],
            'products': tag_products[tag['name']]
        })

    return jsonify({'tags': result})

@app.route('/api/tags/<path:tag_name>', methods=['PUT'])
@login_required
def api_rename_tag(tag_name):
    """Rename a tag across all products"""
    data = request.get_json()
    new_name = data.get('new_name', '').strip()

    if not new_name:
        return jsonify({'error': 'New tag name is required'}), 400

    if new_name == tag_name:
        return jsonify({'error': 'New name is the same as old name'}), 400

    products = get_products()
    updated_count = 0

    for product in products:
        if tag_name in product.get('tags', []):
            # Read current tags
            tags_file = os.path.join(PRODUCTS_DIR, product['category'], product['slug'], 'tags.txt')
            if os.path.exists(tags_file):
                with open(tags_file, 'r', encoding='utf-8') as f:
                    tags = [line.strip() for line in f if line.strip()]

                # Replace the tag
                new_tags = [new_name if t == tag_name else t for t in tags]

                # Write back
                with open(tags_file, 'w', encoding='utf-8') as f:
                    for t in new_tags:
                        f.write(f"{t}\n")

                updated_count += 1

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()

    return jsonify({'success': True, 'updated_count': updated_count})

@app.route('/api/tags/<path:tag_name>', methods=['DELETE'])
@login_required
def api_delete_tag(tag_name):
    """Remove a tag from all products"""
    products = get_products()
    updated_count = 0

    for product in products:
        if tag_name in product.get('tags', []):
            # Read current tags
            tags_file = os.path.join(PRODUCTS_DIR, product['category'], product['slug'], 'tags.txt')
            if os.path.exists(tags_file):
                with open(tags_file, 'r', encoding='utf-8') as f:
                    tags = [line.strip() for line in f if line.strip()]

                # Remove the tag
                new_tags = [t for t in tags if t != tag_name]

                # Write back
                with open(tags_file, 'w', encoding='utf-8') as f:
                    for t in new_tags:
                        f.write(f"{t}\n")

                updated_count += 1

    # Invalidate cache
    cache.invalidate()
    html_cache.invalidate()

    return jsonify({'success': True, 'updated_count': updated_count})

@app.route('/api/tags/<path:tag_name>/products', methods=['POST'])
@login_required
def api_add_product_to_tag(tag_name):
    """Add a product to a tag"""
    data = request.get_json()
    category = data.get('category')
    slug = data.get('slug')

    if not category or not slug:
        return jsonify({'error': 'Category and slug are required'}), 400

    tags_file = os.path.join(PRODUCTS_DIR, category, slug, 'tags.txt')

    # Read current tags
    tags = []
    if os.path.exists(tags_file):
        with open(tags_file, 'r', encoding='utf-8') as f:
            tags = [line.strip() for line in f if line.strip()]

    # Add tag if not already present
    if tag_name not in tags:
        tags.append(tag_name)
        with open(tags_file, 'w', encoding='utf-8') as f:
            for t in tags:
                f.write(f"{t}\n")

        # Invalidate cache
        cache.invalidate()
    html_cache.invalidate()

    return jsonify({'success': True})

@app.route('/api/tags/<path:tag_name>/products/<category>/<slug>', methods=['DELETE'])
@login_required
def api_remove_product_from_tag(tag_name, category, slug):
    """Remove a product from a tag"""
    tags_file = os.path.join(PRODUCTS_DIR, category, slug, 'tags.txt')

    if not os.path.exists(tags_file):
        return jsonify({'error': 'Tags file not found'}), 404

    # Read current tags
    with open(tags_file, 'r', encoding='utf-8') as f:
        tags = [line.strip() for line in f if line.strip()]

    # Remove the tag
    if tag_name in tags:
        tags.remove(tag_name)
        with open(tags_file, 'w', encoding='utf-8') as f:
            for t in tags:
                f.write(f"{t}\n")

        # Invalidate cache
        cache.invalidate()
    html_cache.invalidate()

    return jsonify({'success': True})

# ===== API Routes - Images =====

@app.route('/api/upload-image', methods=['POST'])
@login_required
def api_upload_image():
    """Upload product image"""
    if 'image' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['image']
    category = request.form.get('category')
    slug = request.form.get('slug')

    if not category or not slug:
        return jsonify({'error': 'Category and slug required'}), 400

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Create product images directory
        images_dir = os.path.join(PRODUCTS_DIR, category, slug, 'images')
        os.makedirs(images_dir, exist_ok=True)

        # Save original
        filepath = os.path.join(images_dir, filename)
        file.save(filepath)

        # Create thumbnail only for images, not videos
        is_video = filename.lower().endswith(('.mp4', '.mov', '.avi', '.webm'))
        if not is_video:
            thumb_filename = f"thumb_{filename}"
            thumb_path = os.path.join(images_dir, thumb_filename)
            create_thumbnail(filepath, thumb_path)
            thumb_url = f"/static/images/products/{category}/{slug}/{thumb_filename}"
        else:
            thumb_url = None

        # Return relative URL
        image_url = f"/static/images/products/{category}/{slug}/{filename}"

        return jsonify({
            'success': True,
            'filename': filename,
            'url': image_url,
            'thumbnail': thumb_url
        })

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/scan-images', methods=['GET'])
@login_required
def api_scan_images():
    """Scan product images directory and return list of all images/videos"""
    category = request.args.get('category')
    slug = request.args.get('slug')

    if not category or not slug:
        return jsonify({'error': 'Category and slug required'}), 400

    images_dir = os.path.join(PRODUCTS_DIR, category, slug, 'images')

    if not os.path.exists(images_dir):
        return jsonify({'success': True, 'images': []})

    try:
        # Get all image and video files, excluding thumbnails and hidden files
        files = sorted([f for f in os.listdir(images_dir)
                       if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.avi', '.webm'))
                       and not f.startswith('thumb_')
                       and not f.startswith('.')])

        return jsonify({'success': True, 'images': files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ===== Static Files =====

@app.route('/static/images/products/<category>/<slug>/<filename>')
def serve_product_image(category, slug, filename):
    """Serve product images"""
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

@app.route('/api/featured-tags', methods=['GET'])
@login_required
def api_get_featured_tags():
    """Get all featured tags"""
    return jsonify({'featured_tags': get_featured_tags()})

@app.route('/api/featured-tags', methods=['POST'])
@login_required
def api_create_featured_tag():
    """Create a new featured tag"""
    data = request.get_json()
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'error': 'Tag name is required'}), 400

    tags = get_featured_tags()

    # Check if already exists
    if any(t['name'] == name for t in tags):
        return jsonify({'error': 'Featured tag already exists'}), 400

    new_tag = {
        'name': name,
        'icon': data.get('icon', ''),
        'order_weight': data.get('order_weight', 0)
    }
    tags.append(new_tag)
    save_featured_tags(tags)

    return jsonify({'success': True, 'tag': new_tag})

@app.route('/api/featured-tags/<path:tag_name>', methods=['PUT'])
@login_required
def api_update_featured_tag(tag_name):
    """Update a featured tag"""
    data = request.get_json()
    tags = get_featured_tags()

    tag = next((t for t in tags if t['name'] == tag_name), None)
    if not tag:
        return jsonify({'error': 'Featured tag not found'}), 404

    # Update fields
    if 'name' in data:
        tag['name'] = data['name'].strip()
    if 'icon' in data:
        tag['icon'] = data['icon']
    if 'order_weight' in data:
        tag['order_weight'] = data['order_weight']

    save_featured_tags(tags)
    return jsonify({'success': True, 'tag': tag})

@app.route('/api/featured-tags/<path:tag_name>', methods=['DELETE'])
@login_required
def api_delete_featured_tag(tag_name):
    """Delete a featured tag"""
    tags = get_featured_tags()
    tags = [t for t in tags if t['name'] != tag_name]
    save_featured_tags(tags)
    return jsonify({'success': True})

@app.route('/api/featured-tags/<path:tag_name>/icon', methods=['POST'])
@login_required
def api_upload_featured_tag_icon(tag_name):
    """Upload icon for a featured tag"""
    if 'icon' not in request.files:
        return jsonify({'error': 'No icon file provided'}), 400

    file = request.files['icon']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if file:
        # Create safe filename
        ext = file.filename.rsplit('.', 1)[-1].lower()
        if ext not in {'png', 'jpg', 'jpeg', 'webp'}:
            return jsonify({'error': 'Invalid file type'}), 400

        # Use tag name as filename (slugified)
        from werkzeug.utils import secure_filename
        safe_name = secure_filename(tag_name.lower().replace(' ', '-'))
        filename = f"{safe_name}.{ext}"

        # Save file
        filepath = os.path.join(FEATURED_TAGS_ICONS_DIR, filename)
        file.save(filepath)

        # Update tag with icon filename
        tags = get_featured_tags()
        tag = next((t for t in tags if t['name'] == tag_name), None)
        if tag:
            tag['icon'] = filename
            save_featured_tags(tags)

        return jsonify({'success': True, 'icon': filename})

    return jsonify({'error': 'Upload failed'}), 500

# ===== API Routes - Featured Products =====

@app.route('/api/featured-products', methods=['GET'])
@login_required
def api_get_featured_products():
    """Get list of featured product references"""
    return jsonify({'featured_products': get_featured_products_refs()})

@app.route('/api/featured-products', methods=['PUT'])
@login_required
def api_update_featured_products():
    """Update the entire featured products list (for reordering)"""
    data = request.get_json()
    refs = data.get('products', [])
    save_featured_products_refs(refs)
    return jsonify({'success': True})

# ===== Main =====

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5006)
