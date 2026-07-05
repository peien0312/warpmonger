#!/usr/bin/env python3
"""
Import products from the warpmonger-pos SQLite database (single source of truth).

Replaces the old import_from_salessite.py / products.csv flow:
  - product data comes from the POS `products` table
  - images come from POS `product_images` rows (synced from Shopee exports
    by warpmonger-pos/scripts/sync_shopee_images.py) with files cached under
    warpmonger-pos/media/<SKU>/
  - Taiwan stock level comes from POS `inventory`

Behavior mirrors import_products.py:
  - match existing site products by `id` frontmatter (the POS SKU, e.g. JT01291)
  - existing products keep their category, slug, description body, tags,
    USD price, sale/new-arrival flags and order_weight
  - new products: category = slugified series (inferred from the product
    name when series is empty), slug = slugified English name
  - products with no Shopee images AND no existing site page are skipped
    (they are not listed anywhere, nothing to show)

Usage:
  venv/bin/python import_from_pos.py --db ../warpmonger-pos/data/warpmonger.db \
      --media-dir ../warpmonger-pos/media [--dry-run]
"""

import argparse
import os
import re
import shutil
import sqlite3
from pathlib import Path

from app import (
    PRODUCTS_DIR,
    CATEGORIES_DIR,
    get_products,
    save_product,
    slugify,
    create_thumbnail,
)

BASE = Path(__file__).resolve().parent
DEFAULT_DB = BASE.parent / "warpmonger-pos" / "data" / "warpmonger.db"
DEFAULT_MEDIA = BASE.parent / "warpmonger-pos" / "media"

# POS `series` free text is inconsistent ('Warhammer 40,000', 'Warhammer40,000',
# 'Warhammer 40k', with stray newlines...). Canonical key = lowercased
# alphanumeric-only text -> (site category slug, display name).
SERIES_ALIASES = {
    "warhammer40000": ("warhammer-40000", "Warhammer 40,000"),
    "warhammer40k": ("warhammer-40000", "Warhammer 40,000"),
    "warhammerthehorusheresy": ("warhammer-the-horus-heresy", 'Warhammer "The Horus Heresy"'),
    "warhammerageofsigmar": ("warhammer-age-of-sigmar", "Warhammer Age of Sigmar"),
    "starcrafttabletopminiaturesgame": ("starcraft", "StarCraft"),
    "darksource": ("dark-source", "Dark Source"),
    "darksourcejianghu": ("dark-source-jianghu", "Dark Source-JiangHu"),
    "battleforthestars": ("battle-for-the-stars", "Battle For the Stars"),
    "hardcorecoldplay": ("hardcore-coldplay", "Hardcore Coldplay"),
    "levelnine": ("level-nine", "LEVEL NINE"),
    "tools": ("tools", "Tools"),
    # display cases / racks / accessories all live under Tools on the site
    "joytoy": ("tools", "Tools"),
    "鋼鐵鑄造": ("tools", "Tools"),
    "custom": ("custom", "Custom & Handmade"),
    "other": ("other", "Other"),
}


def canon_key(series_label):
    return re.sub(r"[^0-9a-z一-鿿]", "", series_label.lower())


def category_for(series_label):
    """-> (category_slug, category_display_name)"""
    key = canon_key(series_label)
    if key in SERIES_ALIASES:
        return SERIES_ALIASES[key]
    return slugify(series_label) or "other", series_label


# keyword fallbacks for products whose POS `series` is empty
SERIES_HINTS = [
    (("戰鎚40", "战锤40", "40K", "40,000"), "Warhammer 40,000"),
    (("戰鎚30", "战锤30", "30K", "Horus"), 'Warhammer "The Horus Heresy"'),
    (("席格瑪", "Sigmar",), "Warhammer Age of Sigmar"),
    (("星海", "StarCraft", "星際"), "StarCraft Tabletop Miniatures Game"),
    (("中華英雄", "江湖",), "Dark Source-JiangHu"),
    (("暗源", "Dark Source"), "Dark Source"),
    (("忍者龜", "TMNT"), "TMNT"),
    (("拳皇", "SNK", "KOF"), "SNK"),
]


def norm(text):
    """collapse whitespace/newlines like import_products.py normalize_text;
    old POS form posts stored literal 'None' strings — treat as empty"""
    if not text:
        return ""
    out = " ".join(str(text).split())
    return "" if out.lower() in ("none", "null", "nan") else out


def infer_series(row):
    series = norm(row["series"])
    if series and series.lower() not in ("none", "null"):
        return series
    haystack = " ".join(
        norm(row[k]) for k in ("zhtw_name", "cn_name", "en_name") if row[k]
    )
    for needles, label in SERIES_HINTS:
        if any(n.lower() in haystack.lower() for n in needles):
            return label
    return "Other"


def ensure_category(series_label, slug, dry_run):
    cat_dir = Path(CATEGORIES_DIR) / slug
    cat_file = cat_dir / "category.md"
    if cat_file.exists():
        return False
    if not dry_run:
        cat_dir.mkdir(parents=True, exist_ok=True)
        cat_file.write_text(
            f"---\nname: {series_label}\norder_weight: 0\nicon: \n---\n\n",
            encoding="utf-8",
        )
    return True


def pos_rows(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    try:
        rate = float(cur.execute(
            "SELECT value FROM settings WHERE key='exchange_rate'"
        ).fetchone()[0])
    except Exception:
        rate = 4.45

    products = cur.execute("""
        SELECT p.*, COALESCE(inv.qty, 0) AS tw_qty
        FROM products p
        LEFT JOIN (
            SELECT product_id, SUM(quantity - reserved) AS qty
            FROM inventory WHERE location = 'taiwan' GROUP BY product_id
        ) inv ON inv.product_id = p.id
        WHERE p.is_deleted = 0 AND p.sku IS NOT NULL
    """).fetchall()

    images = {}
    for r in cur.execute("""
        SELECT product_id, kind, sort_order, filename FROM product_images
        ORDER BY product_id,
                 CASE kind WHEN 'cover' THEN 0 WHEN 'gallery' THEN 1 ELSE 2 END,
                 sort_order
    """):
        images.setdefault(r["product_id"], []).append(r["filename"])
    conn.close()
    return products, images, rate


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--media-dir", default=str(DEFAULT_MEDIA))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    media_dir = Path(args.media_dir)
    products, images, rate = pos_rows(args.db)
    print(f"POS: {len(products)} products, "
          f"{sum(len(v) for v in images.values())} image refs, rate={rate}")

    existing = {str(p.get("id", "")).strip(): p for p in get_products() if p.get("id")}
    stats = {"created": 0, "updated": 0, "skipped": 0, "new_categories": [],
             "no_image_new": []}

    for row in products:
        sku = norm(row["sku"])
        img_files = images.get(row["id"], [])
        prior = existing.get(sku)

        if not img_files and not prior:
            stats["skipped"] += 1
            stats["no_image_new"].append(sku)
            continue

        series = infer_series(row)
        cat_slug, cat_name = category_for(series)
        if prior:
            category, slug = prior["category"], prior["slug"]
        else:
            title_src = norm(row["en_name"]) or sku
            category, slug = cat_slug, slugify(title_src) or slugify(sku)
            if ensure_category(cat_name, category, args.dry_run):
                if category not in stats["new_categories"]:
                    stats["new_categories"].append(category)

        # --- copy images from POS media cache into the product folder ---
        image_names = []
        if img_files:
            images_dir = Path(PRODUCTS_DIR) / category / slug / "images"
            for rel in img_files:  # rel like "media/<SKU>/<hash>.jpg" or abs path
                src = Path(rel)
                if not src.is_absolute():
                    src = media_dir.parent / rel
                if not src.exists():
                    # filename column may be relative to the media dir itself
                    alt = media_dir / Path(rel).relative_to("media") \
                        if str(rel).startswith("media/") else media_dir / rel
                    src = alt if alt.exists() else src
                if not src.exists():
                    continue
                if not args.dry_run:
                    images_dir.mkdir(parents=True, exist_ok=True)
                    dest = images_dir / src.name
                    if not dest.exists():
                        shutil.copy2(src, dest)
                image_names.append(src.name)
            if image_names and not args.dry_run:
                first = images_dir / image_names[0]
                thumb = images_dir / f"thumb_{first.stem}.jpg"
                if not thumb.exists():
                    create_thumbnail(str(first), str(thumb))
        elif prior:
            image_names = prior.get("images", [])

        cost_cny = float(row["cost_cny"] or 0)
        preorder_date = ""
        if row["preorder_date"]:
            preorder_date = str(row["preorder_date"])[:10]

        data = {
            "title": norm(row["en_name"]) or norm(row["zhtw_name"]) or sku,
            "sku": norm(row["barcode"]) or (prior.get("sku", "") if prior else ""),
            "id": sku,
            "cn_name": norm(row["cn_name"]),
            "zhtw_name": norm(row["zhtw_name"]),
            "series": cat_name if cat_name not in ("Other",) else norm(row["series"]),
            "scale": norm(row["scale"]),
            "size": norm(row["size"]),
            "weight": norm(row["weight"]),
            "cost": cost_cny,
            "cost_tw": round(cost_cny * rate),
            "final_price": float(row["selling_price_twd"] or 0),
            "in_stock": (row["tw_qty"] or 0) > 0,
            "is_pre_order": bool(row["is_preorder"]),
            "available_date": preorder_date,
            "images": image_names,
            "description": (prior.get("description") if prior else None)
                           or row["description"] or "",
            # preserved site-only fields
            "price": prior.get("price", 0) if prior else 0,
            "zhtw_price": prior.get("zhtw_price", 0) if prior else 0,
            "is_on_sale": prior.get("is_on_sale", False) if prior else False,
            "sale_price": prior.get("sale_price", 0) if prior else 0,
            "is_new_arrival": prior.get("is_new_arrival", False) if prior else False,
            "order_weight": prior.get("order_weight", 0) if prior else 0,
            "group": prior.get("group", "") if prior else "",
            "tags": prior.get("tags", []) if prior else [],
        }

        if not args.dry_run:
            save_product(category, slug, data)
        stats["created" if not prior else "updated"] += 1

    print("=" * 60)
    print(f"created: {stats['created']}  updated: {stats['updated']}  "
          f"skipped (no images, not on site): {stats['skipped']}")
    if stats["new_categories"]:
        print(f"new categories: {', '.join(stats['new_categories'])}")
    if stats["no_image_new"]:
        print(f"skipped SKUs (first 20): {', '.join(stats['no_image_new'][:20])}")
    if args.dry_run:
        print("dry run — nothing written.")


if __name__ == "__main__":
    main()
