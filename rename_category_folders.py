#!/usr/bin/env python3
"""
One-time migration script to rename product category folders to match category slugs
"""

import os
import shutil
import re

# Paths
CONTENT_DIR = os.path.join(os.path.dirname(__file__), 'content')
PRODUCTS_DIR = os.path.join(CONTENT_DIR, 'products')
CATEGORIES_DIR = os.path.join(CONTENT_DIR, 'categories')

def slugify(text):
    """Convert text to URL-friendly slug"""
    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text

def parse_frontmatter(content):
    """Parse frontmatter from markdown content"""
    if not content.startswith('---'):
        return {}, content

    parts = content.split('---', 2)
    if len(parts) < 3:
        return {}, content

    frontmatter = {}
    for line in parts[1].strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            frontmatter[key.strip()] = value.strip()

    return frontmatter, parts[2].strip()

def get_category_mapping():
    """Get mapping of original category names to slugs"""
    mapping = {}

    if not os.path.exists(CATEGORIES_DIR):
        print(f"Categories directory not found: {CATEGORIES_DIR}")
        return mapping

    for category_slug in os.listdir(CATEGORIES_DIR):
        category_path = os.path.join(CATEGORIES_DIR, category_slug)
        if not os.path.isdir(category_path) or category_slug.startswith('.'):
            continue

        category_file = os.path.join(category_path, 'category.md')
        if not os.path.exists(category_file):
            continue

        with open(category_file, 'r', encoding='utf-8') as f:
            content = f.read()

        frontmatter, _ = parse_frontmatter(content)
        original_name = frontmatter.get('name', category_slug)

        mapping[original_name] = category_slug

    return mapping

def rename_category_folders():
    """Rename product category folders to match slugs"""
    if not os.path.exists(PRODUCTS_DIR):
        print(f"Products directory not found: {PRODUCTS_DIR}")
        return

    print("Building category mapping...\n")
    category_mapping = get_category_mapping()

    if not category_mapping:
        print("No categories found!")
        return

    print(f"Found {len(category_mapping)} categories")
    print("="*60)

    renamed_count = 0
    skipped_count = 0

    for original_name, slug in category_mapping.items():
        old_path = os.path.join(PRODUCTS_DIR, original_name)
        new_path = os.path.join(PRODUCTS_DIR, slug)

        # Skip if folder doesn't exist
        if not os.path.exists(old_path):
            print(f"⊘ {original_name} -> {slug} (folder doesn't exist)")
            skipped_count += 1
            continue

        # Skip if already renamed
        if old_path == new_path:
            print(f"⊘ {original_name} -> {slug} (already correct)")
            skipped_count += 1
            continue

        # Check if target already exists
        if os.path.exists(new_path):
            print(f"⚠ {original_name} -> {slug} (target already exists, skipping)")
            skipped_count += 1
            continue

        # Rename the folder
        try:
            shutil.move(old_path, new_path)
            print(f"✓ {original_name} -> {slug}")
            renamed_count += 1
        except Exception as e:
            print(f"✗ {original_name} -> {slug} (error: {e})")

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  Renamed: {renamed_count} folders")
    print(f"  Skipped: {skipped_count} folders")
    print(f"="*60)

if __name__ == '__main__':
    print("Category Folder Renaming Script")
    print("="*60)
    print("This will rename product category folders to match category slugs")
    print("="*60)

    response = input("\nProceed with renaming? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        rename_category_folders()
        print("\nDone!")
    else:
        print("Cancelled.")
