#!/usr/bin/env python3
"""
Fix categories that have newline characters in their names
Moves products from broken category names to normalized names
"""

import os
import shutil
from app import PRODUCTS_DIR, get_products

def normalize_category_name(name):
    """Normalize category name by replacing newlines with spaces"""
    return ' '.join(name.split())

def fix_categories():
    """Find and fix categories with newlines in their names"""

    if not os.path.exists(PRODUCTS_DIR):
        print(f"Products directory not found: {PRODUCTS_DIR}")
        return

    categories = [d for d in os.listdir(PRODUCTS_DIR)
                  if os.path.isdir(os.path.join(PRODUCTS_DIR, d)) and not d.startswith('.')]

    print(f"Found {len(categories)} categories")
    print()

    # Find categories with newlines
    broken_categories = [cat for cat in categories if '\n' in cat]

    if not broken_categories:
        print("No broken categories found!")
        return

    print(f"Found {len(broken_categories)} categories with newlines:")
    for cat in broken_categories:
        print(f"  - {repr(cat)}")
    print()

    # Fix each broken category
    for old_name in broken_categories:
        new_name = normalize_category_name(old_name)
        old_path = os.path.join(PRODUCTS_DIR, old_name)
        new_path = os.path.join(PRODUCTS_DIR, new_name)

        print(f"Fixing: {repr(old_name)} -> {repr(new_name)}")

        # If target already exists, merge the directories
        if os.path.exists(new_path):
            print(f"  Merging with existing category: {new_name}")
            # Move all products from old to new
            for product_slug in os.listdir(old_path):
                if product_slug.startswith('.'):
                    continue
                src = os.path.join(old_path, product_slug)
                dst = os.path.join(new_path, product_slug)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        print(f"    Skipping duplicate: {product_slug}")
                    else:
                        shutil.move(src, dst)
                        print(f"    Moved: {product_slug}")
            # Remove old directory
            shutil.rmtree(old_path)
            print(f"  Removed old directory")
        else:
            # Simply rename
            shutil.move(old_path, new_path)
            print(f"  Renamed")

        print()

    print("✅ Categories fixed!")
    print()

    # Show final category list
    categories = sorted([d for d in os.listdir(PRODUCTS_DIR)
                        if os.path.isdir(os.path.join(PRODUCTS_DIR, d)) and not d.startswith('.')])
    print(f"Final categories ({len(categories)}):")
    for cat in categories:
        count = len([f for f in os.listdir(os.path.join(PRODUCTS_DIR, cat))
                     if os.path.isdir(os.path.join(PRODUCTS_DIR, cat, f)) and not f.startswith('.')])
        print(f"  - {cat}: {count} products")

if __name__ == '__main__':
    print("Category Cleanup Script")
    print("="*60)
    print()
    fix_categories()
