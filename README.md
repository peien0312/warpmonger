# Toy Seller Site

A simple file-based content management system for managing product catalogs and blog posts.

## Features

- **Product Catalog**: Organize products by categories with images, descriptions, and tags
- **Blog**: Write and publish blog posts in Markdown
- **Admin Dashboard**: User-friendly interface for non-technical staff
- **File-Based Storage**: No database required - all content stored as files
- **Image Management**: Upload and manage product images with automatic thumbnail generation
- **Tag-Based Search**: Filter products by tags
- **Responsive Design**: Works on desktop and mobile devices

## Quick Start

### 1. Set up virtual environment

```bash
cd /Users/peienwang/toy-seller-site
python3 -m venv venv
source venv/bin/activate  # On Mac/Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create .env file

```bash
cp .env.example .env
# Edit .env and set a secure SECRET_KEY
```

### 4. Run the application

```bash
python3 app.py
```

The site will be available at: http://localhost:5001

## Default Login

- **Username**: admin
- **Password**: admin123

**IMPORTANT**: Change the default password after first login!

## Usage

### Admin Dashboard

Access the admin dashboard at: http://localhost:5001/admin

**Managing Products:**

1. Click "+ New Product" in the sidebar
2. Fill in product details:
   - Product name (required)
   - Category (creates new category if doesn't exist)
   - Price
   - SKU (optional)
   - Description (supports Markdown)
   - Tags (one per line)
   - Upload images (drag & drop or click to browse)
3. Click "Save Product"

**Managing Blog Posts:**

1. Click "+ New Post" in the sidebar
2. Fill in post details:
   - Title (required)
   - Date
   - Author
   - Excerpt (for preview)
   - Content (supports Markdown)
   - Tags (comma-separated)
3. Click "Save Post"

### Public Site

View the public site at: http://localhost:5001

**Pages:**
- `/` - Homepage with featured products and recent blog posts
- `/products` - Product catalog with category filtering
- `/products/<category>/<slug>` - Individual product pages
- `/blog` - Blog listing
- `/blog/<slug>` - Individual blog posts

## Content Structure

All content is stored in the `/content` directory:

```
content/
├── products/
│   └── [Category]/
│       └── [Product-Slug]/
│           ├── product.md       # Product details with frontmatter
│           ├── tags.txt         # One tag per line
│           └── images/
│               ├── image1.jpg
│               └── thumb_image1.jpg
└── blog/
    └── YYYY-MM-DD-post-title.md
```

### Product Frontmatter Format

```markdown
---
title: Red Fire Truck
price: 29.99
sku: TOY-001
in_stock: true
images: ["fire-truck.jpg", "fire-truck-2.jpg"]
---

Product description goes here in Markdown format.

## Features
- Feature 1
- Feature 2
```

### Blog Post Frontmatter Format

```markdown
---
title: New Toy Collection
date: 2025-01-15
author: John Doe
excerpt: Check out our latest toys!
tags: ["news", "toys", "collection"]
---

Blog post content goes here in Markdown format.
```

## Customization

### Changing Default User

Edit `data/users.json`:

```json
{
  "your-username": {
    "password_hash": "use-password-hash-here",
    "role": "admin"
  }
}
```

Generate password hash in Python:

```python
from werkzeug.security import generate_password_hash
print(generate_password_hash('your-password'))
```

### Styling

- Admin styles: `static/css/admin.css`
- Public site styles: `static/css/public.css`

### Logo and Branding

Edit the templates:
- `templates/public/base.html` - Change "Toy Seller" to your brand name
- `templates/admin/dashboard.html` - Update admin header

## Deployment

### Production Setup

1. **Install production WSGI server:**

```bash
pip install gunicorn
```

2. **Run with Gunicorn:**

```bash
gunicorn -w 4 -b 0.0.0.0:5001 app:app
```

3. **Set up Nginx as reverse proxy** (recommended)

4. **Set secure SECRET_KEY in .env**

5. **Enable HTTPS with SSL certificate**

### Backup

Simply backup the entire project folder, especially:
- `/content` - All products and blog posts
- `/data` - User accounts
- `/static/images` - Uploaded images (if not using symlinks)

## Security Notes

- Change default admin password immediately
- Set a strong SECRET_KEY in production
- Use HTTPS in production
- Regularly backup your content
- Review uploaded images for security

## File Size Limits

- Maximum file upload: 16MB (configurable in `app.py`)
- Supported image formats: PNG, JPG, JPEG, WebP

## Browser Support

- Chrome (latest)
- Firefox (latest)
- Safari (latest)
- Edge (latest)

## Troubleshooting

**Images not displaying:**
- Check file permissions on `/content/products/` and subdirectories
- Verify images were uploaded successfully
- Check browser console for 404 errors

**Admin dashboard not loading:**
- Clear browser cache
- Check if you're logged in (visit `/admin/login`)
- Check browser console for JavaScript errors

**Cannot save products:**
- Ensure `/content/products/` directory has write permissions
- Check that category name doesn't contain special characters
- Verify all required fields are filled

## Support

For issues or questions, refer to the Flask documentation:
- Flask: https://flask.palletsprojects.com/
- Python Markdown: https://python-markdown.github.io/

## License

This project is for personal/commercial use.
