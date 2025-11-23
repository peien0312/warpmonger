#!/usr/bin/env python3
"""
Import products from old salessite structure
- Reads from /Users/peienwang/salessite/products/
- Merges editor/ and gallery/ folders into single images folder
- Matches with CSV data by SKU for product details
- Creates or updates products in new site
"""

import os
import sys
import csv
import shutil
from pathlib import Path
from app import PRODUCTS_DIR, slugify, save_product, get_products

SALESSITE_PRODUCTS = "/Users/peienwang/salessite/joytoy_media"
CSV_FILE = "products.csv"

def extract_sku_from_dirname(dirname):
    """Extract SKU from directory name like 'product-name_6973130378872'"""
    if '_' in dirname:
        return dirname.split('_')[-1]
    return None

def load_csv_data():
    """Load all CSV data into a dictionary keyed by SKU"""
    csv_data = {}

    if not os.path.exists(CSV_FILE):
        print(f"Warning: {CSV_FILE} not found, will import without CSV data")
        return csv_data

    with open(CSV_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku = row.get('sku', '').strip()
            if sku:
                csv_data[sku] = row

    print(f"Loaded {len(csv_data)} products from CSV")
    return csv_data

def normalize_text(text):
    """Replace newlines and normalize whitespace"""
    if not text:
        return ''
    return ' '.join(str(text).split())

def copy_images(old_product_dir, new_images_dir, slug):
    """
    Copy images and videos from editor/, gallery/ folders and root to new images folder
    Returns list of media filenames
    """
    images = []

    # Ensure target directory exists
    os.makedirs(new_images_dir, exist_ok=True)

    # Copy from editor folder
    editor_dir = os.path.join(old_product_dir, 'editor')
    if os.path.exists(editor_dir):
        for filename in sorted(os.listdir(editor_dir)):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                src = os.path.join(editor_dir, filename)
                dst = os.path.join(new_images_dir, filename)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    images.append(filename)
                    print(f"    Copied: {filename} (editor)")

    # Also check editor_txt folder (alternative naming)
    editor_txt_dir = os.path.join(old_product_dir, 'editor_txt')
    if os.path.exists(editor_txt_dir):
        for filename in sorted(os.listdir(editor_txt_dir)):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                src = os.path.join(editor_txt_dir, filename)
                dst = os.path.join(new_images_dir, filename)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    images.append(filename)
                    print(f"    Copied: {filename} (editor_txt)")

    # Copy from gallery folder
    gallery_dir = os.path.join(old_product_dir, 'gallery')
    if os.path.exists(gallery_dir):
        for filename in sorted(os.listdir(gallery_dir)):
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                src = os.path.join(gallery_dir, filename)
                dst = os.path.join(new_images_dir, filename)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    images.append(filename)
                    print(f"    Copied: {filename} (gallery)")

    # Copy videos from root of product directory
    for filename in os.listdir(old_product_dir):
        if filename.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
            src = os.path.join(old_product_dir, filename)
            dst = os.path.join(new_images_dir, filename)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                images.append(filename)
                print(f"    Copied: {filename} (video)")

    return images

def import_from_salessite():
    """Import all products from salessite"""

    if not os.path.exists(SALESSITE_PRODUCTS):
        print(f"Error: Salessite products directory not found: {SALESSITE_PRODUCTS}")
        return

    # Load CSV data
    csv_data = load_csv_data()

    # Get existing products
    existing_products = get_products()
    existing_by_sku = {str(p.get('sku', '')).strip(): p for p in existing_products if p.get('sku')}

    print(f"Found {len(existing_by_sku)} existing products in database")
    print()

    # Statistics
    stats = {
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0,
        'images_copied': 0
    }

    # Process each product directory
    product_dirs = sorted([d for d in os.listdir(SALESSITE_PRODUCTS)
                          if os.path.isdir(os.path.join(SALESSITE_PRODUCTS, d))
                          and not d.startswith('.')])

    print(f"Processing {len(product_dirs)} products from salessite...")
    print()

    for idx, dirname in enumerate(product_dirs, 1):
        try:
            # Extract SKU from directory name
            sku = extract_sku_from_dirname(dirname)
            if not sku:
                print(f"[{idx}/{len(product_dirs)}] Skipping {dirname} - no SKU found")
                stats['skipped'] += 1
                continue

            # Get product name from directory (before the underscore)
            product_slug = dirname.rsplit('_', 1)[0] if '_' in dirname else dirname

            # Check if we have CSV data for this SKU
            csv_row = csv_data.get(sku)

            # Try to find existing product by SKU first
            existing = existing_by_sku.get(sku)

            # If not found by SKU, try to find by slug (for ZH codes and other mismatches)
            if not existing:
                for product in existing_products:
                    if product.get('slug') == product_slug:
                        existing = product
                        print(f"    Matched by slug: {product_slug}")
                        break

            if existing:
                # Update existing product
                category = existing['category']
                slug = existing['slug']
                action = 'UPDATE'

                # Get existing description
                product_path = os.path.join(PRODUCTS_DIR, category, slug)
                product_file = os.path.join(product_path, 'product.md')
                description = existing.get('description', '')
            else:
                # Create new product
                if csv_row:
                    series = normalize_text(csv_row.get('series', ''))
                    category = series if series else 'Imported'
                    english_name = normalize_text(csv_row.get('English_name', ''))
                    slug = slugify(english_name) if english_name else product_slug
                else:
                    # No CSV data, use directory name
                    category = 'Imported'
                    slug = product_slug
                action = 'CREATE'
                description = ''

            # Prepare product data
            if csv_row:
                # Use CSV data
                product_data = {
                    'title': normalize_text(csv_row.get('English_name', slug)),
                    'sku': sku,
                    'category': category,
                    'description': description,
                    'tags': existing.get('tags', []) if existing else [],

                    # Pricing
                    'price': float(csv_row.get('price', 0) or 0),
                    'zhtw_price': float(csv_row.get('zhtw_price', 0) or 0),
                    'cost': float(csv_row.get('cost', 0) or 0),
                    'final_price': float(csv_row.get('final_price', 0) or 0),
                    'cost_tw': float(csv_row.get('cost_tw', 0) or 0),

                    # Details
                    'id': normalize_text(csv_row.get('id', '')),
                    'cn_name': normalize_text(csv_row.get('cn_name', '')),
                    'zhtw_name': normalize_text(csv_row.get('zhtw_name', '')),
                    'series': normalize_text(csv_row.get('series', '')),
                    'scale': normalize_text(csv_row.get('scale', '')),
                    'size': normalize_text(csv_row.get('size', '')),
                    'weight': normalize_text(csv_row.get('weight', '')),

                    # Status
                    'in_stock': existing.get('in_stock', True) if existing else True,
                    'is_pre_order': existing.get('is_pre_order', False) if existing else False,
                    'available_date': existing.get('available_date', '') if existing else '',
                    'is_on_sale': existing.get('is_on_sale', False) if existing else False,
                    'sale_price': existing.get('sale_price', 0) if existing else 0,
                    'is_new_arrival': existing.get('is_new_arrival', False) if existing else False,

                    'images': []  # Will be populated below
                }
            else:
                # No CSV data, create minimal product
                product_data = {
                    'title': slug.replace('-', ' ').title(),
                    'sku': sku,
                    'category': category,
                    'description': description,
                    'tags': existing.get('tags', []) if existing else [],
                    'price': existing.get('price', 0) if existing else 0,
                    'in_stock': existing.get('in_stock', True) if existing else True,
                    'images': []
                }

            # Copy images from salessite
            old_product_dir = os.path.join(SALESSITE_PRODUCTS, dirname)
            new_images_dir = os.path.join(PRODUCTS_DIR, category, slug, 'images')

            print(f"[{idx}/{len(product_dirs)}] {action} {category}/{slug}")
            newly_copied = copy_images(old_product_dir, new_images_dir, slug)
            stats['images_copied'] += len(newly_copied)

            # Get all images from the directory (not just newly copied ones)
            if os.path.exists(new_images_dir):
                all_images = sorted([f for f in os.listdir(new_images_dir)
                                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.avi', '.webm'))
                                   and not f.startswith('.')])
                product_data['images'] = all_images
            else:
                product_data['images'] = newly_copied

            # Save product
            save_product(category, slug, product_data)

            if action == 'CREATE':
                stats['created'] += 1
            else:
                stats['updated'] += 1

        except Exception as e:
            print(f"[{idx}/{len(product_dirs)}] ERROR processing {dirname}: {e}")
            stats['errors'] += 1

    # Print summary
    print()
    print("="*60)
    print("IMPORT SUMMARY")
    print("="*60)
    print(f"Created:       {stats['created']}")
    print(f"Updated:       {stats['updated']}")
    print(f"Skipped:       {stats['skipped']}")
    print(f"Errors:        {stats['errors']}")
    print(f"Images Copied: {stats['images_copied']}")
    print(f"Total:         {stats['created'] + stats['updated']}")
    print("="*60)

if __name__ == '__main__':
    print("Salessite Products Import Script")
    print("="*60)
    print(f"Source: {SALESSITE_PRODUCTS}")
    print(f"Target: {PRODUCTS_DIR}")
    print("="*60)
    print()

    import_from_salessite()
