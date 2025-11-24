import os
import json
import re
from datetime import datetime
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import markdown
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

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
CATEGORIES_DIR = os.path.join(CONTENT_DIR, 'categories')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'images')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'mp4', 'mov', 'avi', 'webm'}

# Ensure directories exist
os.makedirs(PRODUCTS_DIR, exist_ok=True)
os.makedirs(BLOG_DIR, exist_ok=True)
os.makedirs(CATEGORIES_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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

    return True

def delete_category(slug):
    """Delete category"""
    import shutil
    category_path = os.path.join(CATEGORIES_DIR, slug)

    if os.path.exists(category_path):
        shutil.rmtree(category_path)
        return True
    return False

def get_products(category=None, search=None):
    """Get all products or products in a category, optionally filtered by search query"""
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
                'order_weight': frontmatter.get('order_weight', 0)
            }

            # Apply search filter if provided
            if search:
                search_lower = search.lower()
                title_match = search_lower in product['title'].lower()
                cn_name_match = search_lower in product['cn_name'].lower() if product['cn_name'] else False
                zhtw_name_match = search_lower in product['zhtw_name'].lower() if product['zhtw_name'] else False

                if not (title_match or cn_name_match or zhtw_name_match):
                    continue

            products.append(product)

    # Sort products: first by order_weight (descending), then by title (ascending)
    products.sort(key=lambda p: (-p['order_weight'], p['title'].lower()))

    return products

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
        'order_weight': frontmatter.get('order_weight', 0)
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
        'order_weight': data.get('order_weight', 0)
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

# ===== Routes - Public =====

@app.route('/')
def home():
    """Homepage"""
    all_products = get_products()
    products = all_products[:8]  # Featured products

    # Get special sections
    new_arrivals = [p for p in all_products if p.get('is_new_arrival', False)][:4]
    on_sale = [p for p in all_products if p.get('is_on_sale', False)][:4]

    posts = get_blog_posts()[:3]  # Recent posts
    categories = get_categories()
    return render_template('public/home.html',
                         products=products,
                         new_arrivals=new_arrivals,
                         on_sale=on_sale,
                         posts=posts,
                         categories=categories)

@app.route('/products')
def products_page():
    """Product catalog page"""
    category = request.args.get('category')
    tag = request.args.get('tag')
    search = request.args.get('search', '').strip()
    show_pre_order = request.args.get('pre_order') == 'true'
    show_on_sale = request.args.get('on_sale') == 'true'
    show_new_arrival = request.args.get('new_arrival') == 'true'

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

    categories = get_categories()

    # Get category name for display
    current_category_name = None
    if category:
        cat_obj = get_category(category)
        if cat_obj:
            current_category_name = cat_obj['name']

    return render_template('public/products.html',
                         products=products,
                         categories=categories,
                         current_category=category,
                         current_category_name=current_category_name,
                         current_search=search,
                         show_pre_order=show_pre_order,
                         show_on_sale=show_on_sale,
                         show_new_arrival=show_new_arrival)

@app.route('/products/<category>/<slug>')
def product_detail(category, slug):
    """Product detail page"""
    product = get_product(category, slug)
    if not product:
        return "Product not found", 404

    # Convert markdown to HTML
    product['description_html'] = markdown.markdown(product['description'])

    # Get category name for display
    cat_obj = get_category(category)
    category_name = cat_obj['name'] if cat_obj else category

    # Get related products (same category)
    related = [p for p in get_products(category) if p['slug'] != slug][:4]

    return render_template('public/product-detail.html',
                         product=product,
                         category_name=category_name,
                         related=related)

@app.route('/blog')
def blog_page():
    """Blog listing page"""
    posts = get_blog_posts()
    return render_template('public/blog.html', posts=posts)

@app.route('/blog/<slug>')
def blog_post_page(slug):
    """Blog post detail page"""
    post = get_blog_post(slug)
    if not post:
        return "Post not found", 404

    # Convert markdown to HTML
    post['content_html'] = markdown.markdown(post['content'])

    return render_template('public/blog-post.html', post=post)

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

    # Generate XML
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for page in pages:
        xml += '  <url>\n'
        xml += f'    <loc>{page["loc"]}</loc>\n'
        xml += f'    <lastmod>{page["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{page["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{page["priority"]}</priority>\n'
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
"""

    return Response(txt, mimetype='text/plain')

# ===== Routes - Admin =====

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Admin login page"""
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')

        users = load_users()

        if username in users and check_password_hash(users[username]['password_hash'], password):
            session['username'] = username
            return jsonify({'success': True})

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

# ===== Main =====

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5006)
