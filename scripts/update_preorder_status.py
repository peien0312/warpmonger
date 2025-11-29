#!/usr/bin/env python3

"""
Script to update pre-order status for products.
If today's date is greater than the available_date, sets is_pre_order to false.
"""

import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
PRODUCTS_DIR = SCRIPT_DIR.parent / "content" / "products"


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


def update_preorder_status(file_path: Path, dry_run: bool = False) -> bool:
    """
    Update is_pre_order to false if available_date has passed.
    Returns True if file was updated.
    """
    content = file_path.read_text()
    frontmatter = parse_frontmatter(content)

    if not frontmatter:
        print(f"⚠️  Could not parse: {file_path}")
        return False

    # Skip if not a pre-order
    if not frontmatter.get("is_pre_order"):
        return False

    # Skip if no available_date
    available_date_str = frontmatter.get("available_date")
    if not available_date_str:
        print(f"⚠️  Pre-order without available_date: {file_path}")
        return False

    # Parse date (YYYY-MM-DD format)
    available_date = date.fromisoformat(str(available_date_str))
    today = date.today()

    if today >= available_date:
        relative_path = file_path.relative_to(PRODUCTS_DIR)
        print(f"✓ Updating: {relative_path}")
        print(f"  Available date: {available_date_str} (past)")

        if not dry_run:
            new_content = re.sub(
                r"^(is_pre_order:)\s*true\s*$",
                r"\1 false",
                content,
                flags=re.MULTILINE,
            )
            file_path.write_text(new_content)

        return True

    return False


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Update pre-order status for products whose available_date has passed."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    args = parser.parse_args()

    today = date.today()

    if args.dry_run:
        print("DRY RUN MODE - No files will be modified\n")

    print(f"Checking products as of {today}...\n")

    # Find all product.md files
    product_files = list(PRODUCTS_DIR.glob("**/product.md"))

    updated = 0
    total_preorders = 0

    for file_path in product_files:
        content = file_path.read_text()
        frontmatter = parse_frontmatter(content)
        if frontmatter and frontmatter.get("is_pre_order"):
            total_preorders += 1

        if update_preorder_status(file_path, dry_run=args.dry_run):
            updated += 1

    print(f"\nSummary:")
    print(f"  Total products: {len(product_files)}")
    print(f"  Pre-orders found: {total_preorders}")
    print(f"  Updated: {updated}")

    if args.dry_run and updated > 0:
        print(f"\nRun without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
