#!/usr/bin/env python3
import csv
import os
import glob
import re

# Parse the CSV file
csv_products = {}  # id -> is_pre_order

with open('merch1.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    header = next(reader)  # skip header
    for row in reader:
        if len(row) >= 2:
            product_id = row[0].strip()
            product_name = row[1].strip()
            is_pre_order = '預購' in product_name
            csv_products[product_id] = is_pre_order
            if is_pre_order:
                print(f"CSV Pre-order found: {product_id} - {product_name[:50]}...")

print(f"\nFound {len(csv_products)} products in CSV")
preorder_count_csv = sum(1 for v in csv_products.values() if v)
print(f"Pre-order products in CSV: {preorder_count_csv}")

# Find all product.md files
product_files = glob.glob('content/products/**/product.md', recursive=True)
print(f"Found {len(product_files)} product.md files\n")

updated_count = 0
pre_order_true_count = 0
pre_order_false_count = 0
matched_products = []

for filepath in product_files:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract the id field - now properly handles empty id
    id_match = re.search(r'^id:\s*(.*)$', content, re.MULTILINE)
    if not id_match:
        continue

    product_id = id_match.group(1).strip()
    if not product_id:
        # Empty id field - skip this product
        continue

    # Only update products that are in the CSV, skip others
    if product_id not in csv_products:
        continue

    matched_products.append(product_id)

    # Determine new values
    new_in_stock = True  # Products in CSV are in stock
    new_is_pre_order = csv_products[product_id]  # True if contains 預購, False otherwise

    # Update in_stock field
    new_content = re.sub(
        r'^(in_stock:\s*)(true|false)',
        f'\\g<1>{"true" if new_in_stock else "false"}',
        content,
        flags=re.MULTILINE | re.IGNORECASE
    )

    # Update is_pre_order field
    new_content = re.sub(
        r'^(is_pre_order:\s*)(true|false)',
        f'\\g<1>{"true" if new_is_pre_order else "false"}',
        new_content,
        flags=re.MULTILINE | re.IGNORECASE
    )

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        updated_count += 1

        if new_is_pre_order:
            pre_order_true_count += 1
            print(f"Set PRE-ORDER: {product_id}")
        else:
            pre_order_false_count += 1

print(f"\n=== Summary ===")
print(f"Total products updated: {updated_count}")
print(f"Products set to is_pre_order=true: {pre_order_true_count}")
print(f"Products set to is_pre_order=false: {pre_order_false_count}")
print(f"Matched products from CSV: {len(matched_products)}")

# Check for pre-order products in CSV that weren't found in product files
csv_preorder_ids = [pid for pid, is_preorder in csv_products.items() if is_preorder]
missing_preorders = [pid for pid in csv_preorder_ids if pid not in matched_products]
print(f"\nPre-order products in CSV not found in product files: {len(missing_preorders)}")
if missing_preorders:
    for pid in missing_preorders[:10]:  # Show first 10
        print(f"  - {pid}")
    if len(missing_preorders) > 10:
        print(f"  ... and {len(missing_preorders) - 10} more")
