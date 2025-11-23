#!/usr/bin/env python3
"""
Check which products are missing images
Scans all products and reports those without images
"""

import os
from pathlib import Path
from app import PRODUCTS_DIR, get_products

def check_product_images():
    """Check all products for missing images"""

    print("Scanning products for missing images...")
    print("=" * 70)
    print()

    # Get all products
    products = get_products()

    # Statistics
    stats = {
        'total': 0,
        'with_images': 0,
        'without_images': 0,
        'empty_folder': 0,
        'no_folder': 0
    }

    missing_products = []

    for product in products:
        stats['total'] += 1

        category = product['category']
        slug = product['slug']
        images_dir = os.path.join(PRODUCTS_DIR, category, slug, 'images')

        # Check if images directory exists
        if not os.path.exists(images_dir):
            stats['without_images'] += 1
            stats['no_folder'] += 1
            missing_products.append({
                'category': category,
                'slug': slug,
                'title': product.get('title', slug),
                'sku': product.get('sku', 'N/A'),
                'status': 'No images folder'
            })
        else:
            # Check if folder has any images
            image_files = [f for f in os.listdir(images_dir)
                          if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.mp4', '.mov', '.avi', '.webm'))
                          and not f.startswith('thumb_')
                          and not f.startswith('.')]

            if len(image_files) == 0:
                stats['without_images'] += 1
                stats['empty_folder'] += 1
                missing_products.append({
                    'category': category,
                    'slug': slug,
                    'title': product.get('title', slug),
                    'sku': product.get('sku', 'N/A'),
                    'status': 'Empty images folder'
                })
            else:
                stats['with_images'] += 1

    # Print results
    if missing_products:
        print("PRODUCTS WITHOUT IMAGES:")
        print("-" * 70)
        print()

        # Group by category
        by_category = {}
        for product in missing_products:
            cat = product['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(product)

        for category in sorted(by_category.keys()):
            print(f"\n{category} ({len(by_category[category])} products)")
            print("-" * 70)
            for product in by_category[category]:
                print(f"  • {product['title']}")
                print(f"    Slug: {product['slug']}")
                print(f"    SKU:  {product['sku']}")
                print(f"    Status: {product['status']}")
                print()
    else:
        print("✓ All products have images!")
        print()

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total products:        {stats['total']}")
    print(f"With images:           {stats['with_images']} ({stats['with_images']/stats['total']*100:.1f}%)")
    print(f"Without images:        {stats['without_images']} ({stats['without_images']/stats['total']*100:.1f}%)")
    print(f"  - No folder:         {stats['no_folder']}")
    print(f"  - Empty folder:      {stats['empty_folder']}")
    print("=" * 70)

    # Save to file
    if missing_products:
        output_file = 'missing_images.txt'
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("PRODUCTS WITHOUT IMAGES\n")
            f.write("=" * 70 + "\n\n")

            for category in sorted(by_category.keys()):
                f.write(f"\n{category} ({len(by_category[category])} products)\n")
                f.write("-" * 70 + "\n")
                for product in by_category[category]:
                    f.write(f"  • {product['title']}\n")
                    f.write(f"    Slug: {product['slug']}\n")
                    f.write(f"    SKU:  {product['sku']}\n")
                    f.write(f"    Status: {product['status']}\n")
                    f.write(f"    Path: content/products/{category}/{product['slug']}/\n")
                    f.write("\n")

            f.write("\n")
            f.write("=" * 70 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 70 + "\n")
            f.write(f"Total products:        {stats['total']}\n")
            f.write(f"With images:           {stats['with_images']} ({stats['with_images']/stats['total']*100:.1f}%)\n")
            f.write(f"Without images:        {stats['without_images']} ({stats['without_images']/stats['total']*100:.1f}%)\n")
            f.write(f"  - No folder:         {stats['no_folder']}\n")
            f.write(f"  - Empty folder:      {stats['empty_folder']}\n")
            f.write("=" * 70 + "\n")

            # Add list of slugs
            f.write("\n")
            f.write("=" * 70 + "\n")
            f.write("SLUGS (for easy copying)\n")
            f.write("=" * 70 + "\n")
            for product in missing_products:
                f.write(f"{product['slug']}\n")

        print()
        print(f"✓ Report saved to: {output_file}")

if __name__ == '__main__':
    check_product_images()
