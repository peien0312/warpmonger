#!/usr/bin/env python3

"""
Script to sync pre-order status from merch1.csv.
If product name contains '預購', set is_pre_order to true, otherwise false.
"""

import csv
import re
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
PRODUCTS_DIR = SCRIPT_DIR.parent / "content" / "products"
CSV_FILE = SCRIPT_DIR.parent / "merch1.csv"


def parse_frontmatter(content: str) -> Optional[dict]:
    """Parse YAML frontmatter from markdown file."""
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None

    frontmatter = {}
    for line in match.group(1).split("\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        # Parse booleans
        if value == "true":
            value = True
        elif value == "false":
            value = False

        frontmatter[key] = value

    return frontmatter


def load_csv_preorder_status() -> dict:
    """Load CSV and return dict of SKU -> is_pre_order status."""
    preorder_map = {}

    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku = row.get("主商品貨號", "").strip()
            name = row.get("商品名稱", "")

            if not sku:
                continue

            # Check if name contains 預購
            is_preorder = "預購" in name
            preorder_map[sku] = is_preorder

    return preorder_map


def update_preorder_in_file(file_path: Path, should_be_preorder: bool, dry_run: bool = False) -> Optional[str]:
    """
    Update is_pre_order in file.
    Returns action taken: 'set_true', 'set_false', or None if no change needed.
    """
    content = file_path.read_text()
    frontmatter = parse_frontmatter(content)

    if not frontmatter:
        return None

    current_preorder = frontmatter.get("is_pre_order", False)

    if current_preorder == should_be_preorder:
        return None  # No change needed

    action = "set_true" if should_be_preorder else "set_false"

    if not dry_run:
        if should_be_preorder:
            new_content = re.sub(
                r"^(is_pre_order:)\s*false\s*$",
                r"\1 true",
                content,
                flags=re.MULTILINE,
            )
        else:
            new_content = re.sub(
                r"^(is_pre_order:)\s*true\s*$",
                r"\1 false",
                content,
                flags=re.MULTILINE,
            )
        file_path.write_text(new_content)

    return action


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync pre-order status from merch1.csv based on '預購' in product name."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    args = parser.parse_args()

    if args.dry_run:
        print("DRY RUN MODE - No files will be modified\n")

    # Load CSV data
    print(f"Loading {CSV_FILE}...")
    preorder_map = load_csv_preorder_status()
    print(f"Found {len(preorder_map)} products in CSV")
    print(f"Pre-orders in CSV: {sum(1 for v in preorder_map.values() if v)}\n")

    # Find all product.md files and build SKU -> file mapping
    product_files = list(PRODUCTS_DIR.glob("**/product.md"))
    sku_to_file = {}

    for file_path in product_files:
        content = file_path.read_text()
        frontmatter = parse_frontmatter(content)
        if frontmatter and frontmatter.get("id"):
            sku_to_file[frontmatter["id"]] = file_path

    print(f"Found {len(product_files)} product files")
    print(f"Products with SKU: {len(sku_to_file)}\n")

    # Process updates
    set_to_true = 0
    set_to_false = 0
    not_found = 0
    no_change = 0

    for sku, should_be_preorder in preorder_map.items():
        if sku not in sku_to_file:
            not_found += 1
            continue

        file_path = sku_to_file[sku]
        action = update_preorder_in_file(file_path, should_be_preorder, dry_run=args.dry_run)

        if action == "set_true":
            relative_path = file_path.relative_to(PRODUCTS_DIR)
            print(f"✓ Setting pre-order TRUE: {relative_path} ({sku})")
            set_to_true += 1
        elif action == "set_false":
            relative_path = file_path.relative_to(PRODUCTS_DIR)
            print(f"✓ Setting pre-order FALSE: {relative_path} ({sku})")
            set_to_false += 1
        else:
            no_change += 1

    print(f"\nSummary:")
    print(f"  Products in CSV: {len(preorder_map)}")
    print(f"  SKUs not found in products: {not_found}")
    print(f"  No change needed: {no_change}")
    print(f"  Set to pre-order (true): {set_to_true}")
    print(f"  Set to released (false): {set_to_false}")

    if args.dry_run and (set_to_true > 0 or set_to_false > 0):
        print(f"\nRun without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
