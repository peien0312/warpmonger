#!/usr/bin/env python3
"""
Generate thumbnails for all product images.
Thumbnails are 300px wide and saved with 'thumb_' prefix.
"""

import os
from PIL import Image
from pathlib import Path

PRODUCTS_DIR = Path('content/products')
THUMB_WIDTH = 300
THUMB_QUALITY = 85

def generate_thumbnail(image_path):
    """Generate a thumbnail for a single image."""
    path = Path(image_path)
    # Always save as .jpg for consistency
    thumb_name = f"thumb_{path.stem}.jpg"
    thumb_path = path.parent / thumb_name

    # Skip if thumbnail already exists and is newer than original
    if thumb_path.exists():
        if thumb_path.stat().st_mtime >= path.stat().st_mtime:
            return False  # Already up to date

    try:
        with Image.open(path) as img:
            # Convert to RGB if needed (handles P, RGBA, LA modes)
            if img.mode in ('P', 'RGBA', 'LA'):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Skip if already small enough
            if img.width <= THUMB_WIDTH:
                # Just copy/optimize
                img.save(thumb_path, 'JPEG', quality=THUMB_QUALITY, optimize=True)
            else:
                # Calculate new height maintaining aspect ratio
                ratio = THUMB_WIDTH / img.width
                new_height = int(img.height * ratio)

                # Resize with high quality
                thumb = img.resize((THUMB_WIDTH, new_height), Image.Resampling.LANCZOS)
                thumb.save(thumb_path, 'JPEG', quality=THUMB_QUALITY, optimize=True)

            return True
    except Exception as e:
        print(f"  Error processing {path}: {e}")
        return False

def main():
    total = 0
    generated = 0
    skipped = 0
    errors = 0

    print("Generating thumbnails...")
    print(f"Target width: {THUMB_WIDTH}px, Quality: {THUMB_QUALITY}")
    print("-" * 50)

    # Find all product image directories
    for category_dir in PRODUCTS_DIR.iterdir():
        if not category_dir.is_dir():
            continue

        for product_dir in category_dir.iterdir():
            if not product_dir.is_dir():
                continue

            images_dir = product_dir / 'images'
            if not images_dir.exists():
                continue

            # Process each image
            for image_file in images_dir.iterdir():
                if image_file.name.startswith('thumb_'):
                    continue  # Skip existing thumbnails

                if image_file.suffix.lower() not in ['.jpg', '.jpeg', '.png', '.webp']:
                    continue

                total += 1
                result = generate_thumbnail(image_file)

                if result is True:
                    generated += 1
                elif result is False:
                    skipped += 1
                else:
                    errors += 1

    print("-" * 50)
    print(f"Total images: {total}")
    print(f"Generated: {generated}")
    print(f"Skipped (up to date): {skipped}")
    print(f"Errors: {errors}")

    # Calculate space savings
    if generated > 0:
        print("\nCalculating space savings...")
        original_size = 0
        thumb_size = 0

        for thumb_file in PRODUCTS_DIR.rglob('thumb_*'):
            if thumb_file.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                original_name = thumb_file.name.replace('thumb_', '')
                original_file = thumb_file.parent / original_name
                if original_file.exists():
                    original_size += original_file.stat().st_size
                    thumb_size += thumb_file.stat().st_size

        if original_size > 0:
            savings = (1 - thumb_size / original_size) * 100
            print(f"Original size: {original_size / 1024 / 1024:.1f} MB")
            print(f"Thumbnail size: {thumb_size / 1024 / 1024:.1f} MB")
            print(f"Space savings: {savings:.1f}%")

if __name__ == '__main__':
    main()
