#!/usr/bin/env python3
"""
Fix case-sensitive folder renames on macOS (requires two-step rename)
"""

import os
import shutil

# Paths
CONTENT_DIR = os.path.join(os.path.dirname(__file__), 'content')
PRODUCTS_DIR = os.path.join(CONTENT_DIR, 'products')

# Folders that need case-insensitive rename
RENAMES = [
    ('TMNT', 'tmnt'),
    ('Tools', 'tools'),
    ('SNK', 'snk'),
    ('Strife', 'strife'),
    ('Infinity', 'infinity'),
]

def rename_folders():
    """Rename folders with two-step process for case-sensitive renames"""
    print("Fixing case-sensitive folder renames...\n")
    print("="*60)

    renamed_count = 0

    for old_name, new_name in RENAMES:
        old_path = os.path.join(PRODUCTS_DIR, old_name)
        new_path = os.path.join(PRODUCTS_DIR, new_name)
        temp_path = os.path.join(PRODUCTS_DIR, f'_temp_{new_name}')

        if not os.path.exists(old_path):
            print(f"⊘ {old_name} -> {new_name} (source doesn't exist)")
            continue

        if old_path.lower() == new_path.lower() and old_name != new_name:
            # Case-insensitive rename needed
            try:
                # Step 1: Rename to temp
                shutil.move(old_path, temp_path)
                # Step 2: Rename to final
                shutil.move(temp_path, new_path)
                print(f"✓ {old_name} -> {new_name} (case-sensitive rename)")
                renamed_count += 1
            except Exception as e:
                print(f"✗ {old_name} -> {new_name} (error: {e})")
                # Try to restore if temp exists
                if os.path.exists(temp_path):
                    shutil.move(temp_path, old_path)
        else:
            print(f"⊘ {old_name} -> {new_name} (already correct or different)")

    print("\n" + "="*60)
    print(f"Summary: Renamed {renamed_count} folders")
    print(f"="*60)

if __name__ == '__main__':
    print("Case-Sensitive Folder Rename Fix")
    print("="*60)
    rename_folders()
    print("\nDone!")
