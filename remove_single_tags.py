#!/usr/bin/env python3
"""
Script to remove tags that only appear once across all products
"""
import os
from app import get_all_tags, get_products, PRODUCTS_DIR, cache

def remove_single_occurrence_tags():
    """Remove all tags that appear only once"""
    # Get all tags with their counts
    all_tags = get_all_tags()

    # Find tags that appear only once
    single_tags = [tag['name'] for tag in all_tags if tag['count'] == 1]

    if not single_tags:
        print("No tags with single occurrence found.")
        return

    print(f"Found {len(single_tags)} tags that appear only once:")
    for tag in single_tags:
        print(f"  - {tag}")

    print("\nRemoving these tags from products...")

    # Get all products
    products = get_products()
    removed_count = 0

    for product in products:
        tags_file = os.path.join(PRODUCTS_DIR, product['category'], product['slug'], 'tags.txt')

        if not os.path.exists(tags_file):
            continue

        # Read current tags
        with open(tags_file, 'r', encoding='utf-8') as f:
            current_tags = [line.strip() for line in f if line.strip()]

        # Remove single-occurrence tags
        new_tags = [t for t in current_tags if t not in single_tags]

        # Only write if something changed
        if len(new_tags) != len(current_tags):
            with open(tags_file, 'w', encoding='utf-8') as f:
                for t in new_tags:
                    f.write(f"{t}\n")
            removed_count += 1
            print(f"  Updated: {product['category']}/{product['slug']}")

    print(f"\nDone! Removed tags from {removed_count} products.")
    print("Invalidating cache...")
    cache.invalidate()
    print("Cache invalidated.")

if __name__ == '__main__':
    remove_single_occurrence_tags()
