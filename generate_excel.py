#!/usr/bin/env python3
"""Generate LINE Shopping Excel from product.md files"""

import os
import re
import shutil
import xlrd
import yaml
from xlutils.copy import copy
from pathlib import Path
from datetime import datetime

# Configuration
PRODUCTS_DIR = "content/products"
OUTPUT_DIR = "line_shopping_output"
BATCH_SIZE = 100
TEMPLATE_FILE = "excelTemplate.xls"

# Fixed values
CATEGORY_ID = "10023697"
SHIPPING_TEMPLATE = "635212"
STOCK_QTY = 24

# Description template
DESC_TEMPLATE = """下單須知
集貨時間：每週二集貨，預設為海運（約10天到貨）。
急件選擇：若需快速到貨，可告知需要空運（約5天到貨），請透過LINE官方帳號聯繫。
多件優惠：購買多件有折扣，歡迎透過LINE官方帳號詢問詳情！
預購商品：商品名稱標示「預購」為預購商品，免訂金，透過LINE官方帳號告知即可。我們會在商品發售前提醒通知下單。
大型商品：大型商品將直接從海外寄送。
現貨出貨：標示「現貨」的商品，下單後當天出貨。
========================================
{title}
{scale}
========================================

歡迎光臨本店！
感謝您選擇我們的商品！我們致力於提供優質的產品與貼心的服務，讓您購物無憂！
所有商品皆為正品，經過嚴格檢驗，品質保證！

下單前請確認商品規格、尺寸、顏色等資訊，避免誤購。
收到商品後請檢查完整性，如有問題請於7天內聯繫我們處理。

如有急用，可透過官方帳號討論其它運送方式
有任何疑問，歡迎透過「聊聊」聯繫我們！我們會盡快回覆，解答您的問題！

感謝您的支持，祝您購物愉快！"""


def parse_frontmatter(content):
    """Parse YAML frontmatter from markdown content"""
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return {}
    return {}


def get_preorder_prefix(available_date):
    """Generate preorder prefix like [預購/X月到貨]"""
    if not available_date:
        return "[預購]"

    try:
        if isinstance(available_date, str):
            # Try parsing various date formats
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%Y-%m"]:
                try:
                    dt = datetime.strptime(available_date, fmt)
                    break
                except ValueError:
                    continue
            else:
                return "[預購]"
        elif isinstance(available_date, datetime):
            dt = available_date
        else:
            return "[預購]"

        # Month + 1 (Dec becomes Jan)
        next_month = dt.month + 1
        if next_month > 12:
            next_month = 1
        return f"[預購/{next_month}月到貨]"
    except Exception:
        return "[預購]"


def find_all_products():
    """Find all product.md files"""
    products = []
    for root, dirs, files in os.walk(PRODUCTS_DIR):
        if "product.md" in files:
            products.append(os.path.join(root, "product.md"))
    return products


def process_product(product_path, images_output_dir=None):
    """Process a single product.md file and return row data"""
    with open(product_path, "r", encoding="utf-8") as f:
        content = f.read()

    fm = parse_frontmatter(content)
    if not fm:
        print(f"Warning: Could not parse frontmatter for {product_path}")
        return None

    product_dir = os.path.dirname(product_path)

    # Get required fields
    product_id = fm.get("id", "")
    zhtw_name = fm.get("zhtw_name", fm.get("title", ""))
    title = fm.get("title", "")
    scale = fm.get("scale", "")
    final_price = fm.get("final_price", 0)
    is_pre_order = fm.get("is_pre_order", False)
    available_date = fm.get("available_date", "")
    images = fm.get("images", [])

    # Build product name with preorder prefix if needed
    if is_pre_order:
        prefix = get_preorder_prefix(available_date)
        product_name = f"{prefix}{zhtw_name}"
    else:
        product_name = zhtw_name

    # Check for gallery_1.jpg (exact match), fallback to first image
    has_gallery = "gallery_1.jpg" in images

    if has_gallery:
        src_filename = "gallery_1.jpg"
    elif images:
        src_filename = images[0]
    else:
        src_filename = None

    # Determine output filename and copy image
    main_image = ""
    if src_filename:
        ext = os.path.splitext(src_filename)[1]
        dst_filename = f"{product_id}{ext}"
        main_image = dst_filename

        if images_output_dir:
            src_image = os.path.join(product_dir, "images", src_filename)
            if os.path.exists(src_image):
                os.makedirs(images_output_dir, exist_ok=True)
                dst_image = os.path.join(images_output_dir, dst_filename)
                shutil.copy2(src_image, dst_image)

    # Build description
    description = DESC_TEMPLATE.format(title=title, scale=scale)

    return {
        "Version": "",
        "商品名稱": product_name,
        "標準類別 ID": CATEGORY_ID,
        "商店分類 ID": "",
        "詳細商品資訊": description,
        "主要圖片檔案名稱": main_image,
        "附加圖片檔案名稱": "",
        "賣家商品代碼": product_id,
        "主要商品敘述": "",
        "新增商品選項": "N",
        "價格": int(final_price) if final_price else 0,
        "庫存數量": STOCK_QTY,
        "選項名稱": "",
        "選項\n值/價格/庫存/管理代碼": "",
        "折扣設定價格": "",
        "折扣設定單位": "",
        "運費範本代碼": SHIPPING_TEMPLATE,
    }


def main():
    print("Finding all products...")
    product_files = find_all_products()
    print(f"Found {len(product_files)} products")

    # Create output directory
    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)
    os.makedirs(OUTPUT_DIR)

    # Calculate number of batches
    num_batches = (len(product_files) + BATCH_SIZE - 1) // BATCH_SIZE
    print(f"Will create {num_batches} batches of up to {BATCH_SIZE} products each")

    columns = [
        "Version", "商品名稱", "標準類別 ID", "商店分類 ID", "詳細商品資訊",
        "主要圖片檔案名稱", "附加圖片檔案名稱", "賣家商品代碼", "主要商品敘述",
        "新增商品選項", "價格", "庫存數量", "選項名稱", "選項\n值/價格/庫存/管理代碼",
        "折扣設定價格", "折扣設定單位", "運費範本代碼"
    ]

    total_processed = 0
    for batch_num in range(num_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = min(start_idx + BATCH_SIZE, len(product_files))
        batch_files = product_files[start_idx:end_idx]

        # Create batch folder
        batch_folder = os.path.join(OUTPUT_DIR, f"batch_{batch_num + 1:02d}")
        images_folder = os.path.join(batch_folder, "images")
        os.makedirs(images_folder, exist_ok=True)

        # Process products in this batch
        rows = []
        for pf in batch_files:
            row = process_product(pf, images_folder)
            if row:
                rows.append(row)
                total_processed += 1

        # Copy template and edit (preserves formatting)
        excel_path = os.path.join(batch_folder, f"products_batch_{batch_num + 1:02d}.xls")

        # Open template and copy it
        template_wb = xlrd.open_workbook(TEMPLATE_FILE, formatting_info=True)
        workbook = copy(template_wb)
        sheet = workbook.get_sheet(0)  # '範本' sheet

        # Clear instruction rows (rows 1-3 in template, 0-indexed: 1,2,3)
        # Keep header row 0, start data from row 1

        # Write data rows (starting from row 1, overwriting instruction rows)
        for row_idx, row in enumerate(rows, start=1):
            for col_idx, col_name in enumerate(columns):
                value = row.get(col_name, '')
                sheet.write(row_idx, col_idx, value)

        workbook.save(excel_path)

        print(f"Batch {batch_num + 1}: {len(rows)} products -> {batch_folder}/")

    print(f"\nTotal processed: {total_processed} products in {num_batches} batches")
    print(f"Output directory: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
