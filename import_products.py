#!/usr/bin/env python3
"""
Import products from products.csv
- Updates existing products (matched by SKU)
- Creates new products if SKU doesn't exist
- Preserves existing content/description
- Updates all frontmatter properties
"""

import csv
import os
import sys
import re
from datetime import datetime
from app import (
    PRODUCTS_DIR,
    get_products,
    save_product,
    slugify,
    parse_frontmatter,
    get_product
)


def find_product_by_sku(sku, all_products):
    """Find existing product by SKU"""
    # Convert to string for comparison (SKUs from CSV are strings, from files might be ints)
    sku_str = str(sku).strip()
    for product in all_products:
        product_sku = str(product.get('sku', '')).strip()
        if product_sku and product_sku == sku_str:
            return product
    return None


def parse_preorder_date(date_str):
    """
    Parse various date formats and convert to YYYY-MM-01
    Handles:
    - 2025/10 -> 2025-10-01
    - 2025/09 -> 2025-09-01
    - 25-Nov -> 2025-11-01 (treats as 2025-Nov)
    - 25-Dec -> 2025-12-01 (treats as 2025-Dec)
    """
    if not date_str or not date_str.strip():
        return ''

    date_str = date_str.strip()

    try:
        # Format: 2025/10 or 2025/09 (year/month)
        if '/' in date_str:
            parts = date_str.split('/')
            if len(parts) == 2:
                year, month = parts
                # Add day as 01 for first of month
                return f"{year}-{month.zfill(2)}-01"

        # Format: 25-Nov or 25-Dec (year-month, where 25 = 2025)
        if '-' in date_str:
            parts = date_str.split('-')
            if len(parts) == 2:
                year_part, month_str = parts

                # Month name to number mapping
                months = {
                    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
                    'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
                    'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
                }

                month_lower = month_str.lower()
                if month_lower in months:
                    # Convert 25 to 2025, 26 to 2026, etc.
                    if len(year_part) == 2:
                        year = f"20{year_part}"
                    else:
                        year = year_part

                    month = months[month_lower]
                    return f"{year}-{month}-01"

        # Already in YYYY-MM-DD format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str

        # Already in YYYY-MM format
        if re.match(r'^\d{4}-\d{2}$', date_str):
            return f"{date_str}-01"

        # Chinese format: 2025年12月 or 2025年11月
        chinese_match = re.match(r'^(\d{4})年(\d{1,2})月$', date_str)
        if chinese_match:
            year = chinese_match.group(1)
            month = chinese_match.group(2).zfill(2)
            return f"{year}-{month}-01"

    except Exception as e:
        print(f"Warning: Could not parse date '{date_str}': {e}")

    return date_str  # Return as-is if parsing fails


def import_from_csv(csv_path='products.csv', default_category='Warhammer 40,000'):
    """Import products from CSV file"""

    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found")
        return

    print(f"Reading {csv_path}...")

    # Load all existing products
    all_products = get_products()
    print(f"Found {len(all_products)} existing products")

    # Track statistics
    stats = {
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': 0
    }

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Required fields
                sku = row.get('sku', '').strip()
                english_name = row.get('English_name', '').strip()

                if not sku:
                    print(f"Row {row_num}: Skipping - no SKU")
                    stats['skipped'] += 1
                    continue

                if not english_name:
                    print(f"Row {row_num}: Skipping SKU {sku} - no English name")
                    stats['skipped'] += 1
                    continue

                # Get category from series column in CSV
                # Replace newlines and multiple spaces with single space
                series = row.get('series', '').strip()
                if series:
                    # Replace newlines and normalize whitespace
                    series = ' '.join(series.split())
                csv_category = series if series else default_category

                # Check if product exists
                existing_product = find_product_by_sku(sku, all_products)

                # Determine category and slug
                if existing_product:
                    # Keep existing category to avoid moving products
                    category = existing_product['category']
                    slug = existing_product['slug']
                    action = 'UPDATE'

                    # Preserve existing description
                    product_path = os.path.join(PRODUCTS_DIR, category, slug)
                    product_file = os.path.join(product_path, 'product.md')

                    if os.path.exists(product_file):
                        with open(product_file, 'r', encoding='utf-8') as pf:
                            content = pf.read()
                        _, description = parse_frontmatter(content)
                    else:
                        description = ''
                else:
                    # New products use series as category (slugified)
                    category = slugify(csv_category)
                    slug = slugify(english_name)
                    action = 'CREATE'
                    description = ''

                # Parse CSV data
                is_preorder = row.get('is_preorder', '').strip()
                if is_preorder:
                    # Parse various date formats (2025/10, 25-Nov, etc.)
                    available_date = parse_preorder_date(is_preorder)
                    is_pre_order = True
                else:
                    is_pre_order = False
                    available_date = ''

                # Helper function to normalize text fields (remove newlines)
                def normalize_text(text):
                    """Replace newlines and normalize whitespace in text fields"""
                    if not text:
                        return ''
                    # Replace newlines with spaces and normalize whitespace
                    return ' '.join(str(text).split())

                # Build product data
                product_data = {
                    'title': normalize_text(english_name),
                    'sku': sku,
                    'category': category,
                    'description': description,  # Preserve existing or empty
                    'tags': [],  # Preserve existing tags if updating

                    # Pricing
                    'price': float(row.get('price', 0) or 0),
                    'zhtw_price': float(row.get('zhtw_price', 0) or 0),
                    'cost': float(row.get('cost', 0) or 0),
                    'final_price': float(row.get('final_price', 0) or 0),
                    'cost_tw': float(row.get('cost_tw', 0) or 0),

                    # Product details - normalize to remove newlines
                    'id': normalize_text(row.get('id', '')),
                    'cn_name': normalize_text(row.get('cn_name', '')),
                    'zhtw_name': normalize_text(row.get('zhtw_name', '')),
                    'series': normalize_text(row.get('series', '')),
                    'scale': normalize_text(row.get('scale', '')),
                    'size': normalize_text(row.get('size', '')),
                    'weight': normalize_text(row.get('weight', '')),

                    # Status
                    'in_stock': True,  # Default to in stock
                    'is_pre_order': is_pre_order,
                    'available_date': available_date,
                    'is_on_sale': False,
                    'sale_price': 0,
                    'is_new_arrival': False,

                    # Ordering
                    'order_weight': 0,  # Default to 0 for new products

                    # Images - preserve existing if updating
                    'images': existing_product.get('images', []) if existing_product else []
                }

                # Preserve existing tags and settings if updating
                if existing_product:
                    product_data['tags'] = existing_product.get('tags', [])
                    product_data['in_stock'] = existing_product.get('in_stock', True)
                    product_data['is_on_sale'] = existing_product.get('is_on_sale', False)
                    product_data['sale_price'] = existing_product.get('sale_price', 0)
                    product_data['is_new_arrival'] = existing_product.get('is_new_arrival', False)
                    product_data['order_weight'] = existing_product.get('order_weight', 0)  # Preserve order_weight

                # Save product
                save_product(category, slug, product_data)

                print(f"Row {row_num}: {action} {category}/{slug} - {english_name}")

                if action == 'CREATE':
                    stats['created'] += 1
                else:
                    stats['updated'] += 1

            except Exception as e:
                print(f"Row {row_num}: ERROR - {str(e)}")
                stats['errors'] += 1

    # Print summary
    print("\n" + "="*60)
    print("IMPORT SUMMARY")
    print("="*60)
    print(f"Created:  {stats['created']}")
    print(f"Updated:  {stats['updated']}")
    print(f"Skipped:  {stats['skipped']}")
    print(f"Errors:   {stats['errors']}")
    print(f"Total:    {stats['created'] + stats['updated']}")
    print("="*60)


if __name__ == '__main__':
    # Get CSV path from command line or use default
    csv_file = sys.argv[1] if len(sys.argv) > 1 else 'products.csv'

    # Get default category from command line or use default
    default_cat = sys.argv[2] if len(sys.argv) > 2 else 'Warhammer 40,000'

    print("Product CSV Import Script")
    print("="*60)
    print(f"CSV File: {csv_file}")
    print(f"Default Category: {default_cat}")
    print("="*60)
    print()

    import_from_csv(csv_file, default_cat)
