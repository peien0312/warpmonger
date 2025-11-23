#!/usr/bin/env python3
"""
One-time migration script to create category structure from existing product folders
"""

import os
import re

# Paths
CONTENT_DIR = os.path.join(os.path.dirname(__file__), 'content')
PRODUCTS_DIR = os.path.join(CONTENT_DIR, 'products')
CATEGORIES_DIR = os.path.join(CONTENT_DIR, 'categories')

# Ensure categories directory exists
os.makedirs(CATEGORIES_DIR, exist_ok=True)

def slugify(text):
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text

def save_category(slug, data):
    """Save category to file"""
    category_path = os.path.join(CATEGORIES_DIR, slug)
    os.makedirs(category_path, exist_ok=True)

    # Create images directory
    images_dir = os.path.join(category_path, 'images')
    os.makedirs(images_dir, exist_ok=True)

    # Create category.md content
    content = f"""---
name: {data['name']}
order_weight: {data['order_weight']}
icon: {data['icon']}
---

{data['description']}"""

    # Save category.md
    category_file = os.path.join(category_path, 'category.md')
    with open(category_file, 'w', encoding='utf-8') as f:
        f.write(content)

def migrate_categories():
    """Create category entries from existing product folders"""
    if not os.path.exists(PRODUCTS_DIR):
        print(f"Products directory not found: {PRODUCTS_DIR}")
        return

    print("Scanning existing product categories...\n")

    # Get all category folders from products directory
    product_categories = []
    for item in os.listdir(PRODUCTS_DIR):
        item_path = os.path.join(PRODUCTS_DIR, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            product_categories.append(item)

    product_categories.sort()

    print(f"Found {len(product_categories)} categories in products directory")
    print("="*60)

    created_count = 0
    skipped_count = 0

    for category_name in product_categories:
        # Generate slug from category name
        slug = slugify(category_name)

        # Check if category already exists
        category_path = os.path.join(CATEGORIES_DIR, slug)
        category_file = os.path.join(category_path, 'category.md')

        if os.path.exists(category_file):
            print(f"⊘ {category_name} -> {slug} (already exists)")
            skipped_count += 1
            continue

        # Create category data
        category_data = {
            'name': category_name,
            'description': '',
            'order_weight': 0,
            'icon': ''
        }

        # Save category
        save_category(slug, category_data)
        print(f"✓ {category_name} -> {slug}")
        created_count += 1

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  Created: {created_count} categories")
    print(f"  Skipped: {skipped_count} categories (already existed)")
    print(f"="*60)
    print(f"\nCategories saved to: {CATEGORIES_DIR}")

if __name__ == '__main__':
    print("Category Migration Script")
    print("="*60)
    migrate_categories()
