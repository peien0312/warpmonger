#!/usr/bin/env python3
"""
Script to update the icon field in all category.md files based on
the actual images found in their respective images/ subdirectories.
"""

import os
import re
from pathlib import Path


def get_category_directories(base_path):
    """Find all category directories containing category.md files."""
    category_dirs = []
    for item in os.listdir(base_path):
        item_path = os.path.join(base_path, item)
        if os.path.isdir(item_path) and not item.startswith('.'):
            category_md = os.path.join(item_path, 'category.md')
            if os.path.exists(category_md):
                category_dirs.append(item_path)
    return category_dirs


def get_icon_from_directory(images_dir):
    """Get the best icon image from a directory.
    Priority: editor images first, then any other image.
    """
    if not os.path.exists(images_dir):
        return None

    # Get all image files
    image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    images = []

    for filename in os.listdir(images_dir):
        if any(filename.lower().endswith(ext) for ext in image_extensions):
            images.append(filename)

    if not images:
        return None

    # Sort images: editor files first, then others
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

    # Return the first image (highest priority)
    return images[0] if images else None


def update_category_md(category_md_path, icon):
    """Update the icon field in category.md frontmatter."""
    with open(category_md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse frontmatter
    frontmatter_match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
    if not frontmatter_match:
        print(f"Warning: No frontmatter found in {category_md_path}")
        return False

    frontmatter = frontmatter_match.group(1)
    body = frontmatter_match.group(2)

    # Update icon field
    icon_value = icon if icon else ''

    if re.search(r'^icon:\s*.*$', frontmatter, re.MULTILINE):
        # Replace existing icon field
        new_frontmatter = re.sub(
            r'^icon:\s*.*$',
            f'icon: {icon_value}',
            frontmatter,
            flags=re.MULTILINE
        )
    else:
        # Add icon field after name
        new_frontmatter = re.sub(
            r'^(name:.*?)$',
            r'\1\nicon: ' + icon_value,
            frontmatter,
            flags=re.MULTILINE
        )

    # Write updated content
    new_content = f"---\n{new_frontmatter}\n---\n{body}"
    with open(category_md_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return True


def main():
    """Main function to update all category icons."""
    base_path = Path(__file__).parent / 'content' / 'categories'

    if not base_path.exists():
        print(f"Error: Categories directory not found at {base_path}")
        return

    print(f"Scanning for categories in: {base_path}")
    category_dirs = get_category_directories(base_path)
    print(f"Found {len(category_dirs)} categories\n")

    updated_count = 0
    no_images_count = 0
    cleared_count = 0

    for category_dir in category_dirs:
        category_name = os.path.basename(category_dir)
        category_md_path = os.path.join(category_dir, 'category.md')
        images_dir = os.path.join(category_dir, 'images')

        # Get icon from directory
        icon = get_icon_from_directory(images_dir)

        if icon:
            # Update category.md with icon
            if update_category_md(category_md_path, icon):
                updated_count += 1
                print(f"✓ Updated {category_name}: icon set to '{icon}'")
            else:
                print(f"✗ Failed to update {category_name}")
        else:
            # No images found, clear the icon field
            if update_category_md(category_md_path, ''):
                cleared_count += 1
                print(f"⊘ Cleared {category_name}: no images found")
            else:
                print(f"✗ Failed to update {category_name}")
            no_images_count += 1

    print("\n" + "="*60)
    print(f"Summary:")
    print(f"  Updated with icon: {updated_count}")
    print(f"  Cleared (no images): {cleared_count}")
    print(f"  Total processed: {len(category_dirs)}")
    print(f"="*60)


if __name__ == '__main__':
    main()
