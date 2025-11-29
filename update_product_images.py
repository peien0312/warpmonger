#!/usr/bin/env python3
"""
Script to update the images field in all product.md files based on
the actual images found in their respective images/ subdirectories.
"""

import os
import re
from pathlib import Path


def get_product_directories(base_path):
    """Find all product directories containing product.md files."""
    product_dirs = []
    for root, dirs, files in os.walk(base_path):
        if 'product.md' in files:
            product_dirs.append(root)
    return product_dirs


def get_images_from_directory(images_dir):
    """Get sorted list of image filenames from a directory."""
    if not os.path.exists(images_dir):
        return []

    # Get all image files
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    images = []

    for filename in os.listdir(images_dir):
        # Skip thumbnails
        if filename.startswith('thumb_'):
            continue
        if any(filename.lower().endswith(ext) for ext in image_extensions):
            images.append(filename)

    # Sort images: editor files first, then gallery files, then others
    def sort_key(filename):
        if filename.startswith('editor_'):
            try:
                num = int(re.search(r'editor_(\d+)', filename).group(1))
                return (0, num)
            except:
                return (0, float('inf'))
        elif filename.startswith('gallery_'):
            try:
                num = int(re.search(r'gallery_(\d+)', filename).group(1))
                return (1, num)
            except:
                return (1, float('inf'))
        else:
            return (2, filename)

    images.sort(key=sort_key)
    return images


def update_product_md(product_md_path, images):
    """Update the images field in product.md frontmatter."""
    with open(product_md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not frontmatter_match:
        print(f"Warning: No frontmatter found in {product_md_path}")
        return False

    frontmatter = frontmatter_match.group(1)
    body = frontmatter_match.group(2)

    # Format images array
    if images:
        images_str = '[' + ', '.join(f'"{img}"' for img in images) + ']'
    else:
        images_str = '[]'

    # Update images field
    if re.search(r'^images:\s*\[.*?\]', frontmatter, re.MULTILINE):
        # Replace existing images field
        new_frontmatter = re.sub(
            r'^images:\s*\[.*?\]',
            f'images: {images_str}',
            frontmatter,
            flags=re.MULTILINE
        )
    else:
        print(f"Warning: No images field found in {product_md_path}")
        return False

    # Write updated content
    new_content = f"---\n{new_frontmatter}\n---\n{body}"
    with open(product_md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def main():
    """Main function to update all product images."""
    base_path = Path(__file__).parent / 'content' / 'products'

    if not base_path.exists():
        print(f"Error: Products directory not found at {base_path}")
        return

    print(f"Scanning for products in: {base_path}")
    product_dirs = get_product_directories(base_path)
    print(f"Found {len(product_dirs)} products")

    updated_count = 0
    skipped_count = 0
    no_images_count = 0

    for product_dir in product_dirs:
        product_md_path = os.path.join(product_dir, 'product.md')
        images_dir = os.path.join(product_dir, 'images')

        # Get images from directory
        images = get_images_from_directory(images_dir)

        if not images:
            no_images_count += 1
            print(f"No images found: {product_dir}")
            continue

        # Update product.md
        if update_product_md(product_md_path, images):
            updated_count += 1
            print(f"✓ Updated {product_dir}: {len(images)} images")
        else:
            skipped_count += 1

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  Updated: {updated_count}")
    print(f"  No images found: {no_images_count}")
    print(f"  Skipped (errors): {skipped_count}")
    print(f"  Total processed: {len(product_dirs)}")


if __name__ == '__main__':
    main()
