# Product CSV Import Guide

This guide explains how to import products from your `products.csv` file into the Toy Seller website.

## Features

The import script intelligently handles product data:

- ✅ **Updates existing products** (matched by SKU) - no duplicates created
- ✅ **Preserves existing content** - doesn't overwrite product descriptions
- ✅ **Preserves existing images** - keeps uploaded product images
- ✅ **Preserves existing tags** - maintains manually added tags
- ✅ **Creates new products** - for SKUs that don't exist yet
- ✅ **Auto-calculates profit** - based on cost and final_price
- ✅ **Handles pre-orders** - converts date format from CSV

## Usage

### Basic Usage

```bash
# Activate virtual environment first
source venv/bin/activate  # On Mac/Linux
# or
venv\Scripts\activate  # On Windows

# Run the import
python3 import_products.py
```

This will:
- Read `products.csv` from the current directory
- Use "Warhammer 40,000" as the default category for new products
- Show progress for each product
- Display a summary when complete

### Advanced Usage

```bash
# Specify a different CSV file
python3 import_products.py my-products.csv

# Specify both CSV file and default category
python3 import_products.py products.csv "JOYTOY Figures"
```

## CSV Format

The script expects these columns (same as your products.csv):

```csv
sku,id,cn_name,zhtw_name,English_name,series,scale,size,weight,zhtw_price,price,cost,final_price,is_preorder,cost_tw
```

### Required Fields
- `sku` - Product SKU (used to match existing products)
- `English_name` - Product title

### Optional Fields
All other fields are optional. Missing fields will default to 0 or empty.

### Date Formats (is_preorder column)
The script handles multiple date formats (all default to 1st of month):
- `2025/10` → Converted to `2025-10-01`
- `2025/09` → Converted to `2025-09-01`
- `25-Nov` → Converted to `2025-11-01` (25 = year 2025)
- `25-Dec` → Converted to `2025-12-01` (25 = year 2025)
- `2025-11` → Converted to `2025-11-01`
- `2025-11-23` → Kept as-is

## How It Works

### For Existing Products (matched by SKU)

1. Script finds the existing product by SKU
2. Reads the current `product.md` file
3. **Preserves the existing description/content**
4. Updates all properties from CSV
5. **Preserves existing images, tags, status flags, and category**
6. Saves the updated product
7. **Note**: Existing products stay in their current category (not moved)

### For New Products

1. Creates a new product folder
2. Uses the **series field** from CSV as the product category
3. Uses the English name to generate a URL slug
4. Sets all properties from CSV
5. Creates empty description (you'll add content later)
6. If series is empty, uses the default category parameter

## Example Output

```
Product CSV Import Script
============================================================
CSV File: products.csv
Default Category: Warhammer 40,000
============================================================

Reading products.csv...
Found 3 existing products

Row 2: UPDATE Warhammer 40,000/death-guard-deathshroud-terminator-champion-with-manreaper-and-plaguespurter-gauntlets - Death Guard Deathshroud Terminator Champion with Manreaper and Plaguespurter Gauntlets
Row 3: CREATE Warhammer 40,000/model-assemblybasic-tool-kit - MODEL ASSEMBLYBASIC TOOL KIT
Row 4: CREATE Warhammer 40,000/individual-soldier-hangar-display-case-armor-white-a - Individual Soldier Hangar Display Case - Armor White A

============================================================
IMPORT SUMMARY
============================================================
Created:  2
Updated:  1
Skipped:  0
Errors:   0
Total:    3
============================================================
```

## What Gets Updated

When updating an existing product, these fields are **updated from CSV**:
- All pricing fields (price, cost, final_price, etc.)
- Product details (id, names, series, scale, size, weight)
- Pre-order status and dates

These fields are **preserved** from existing product:
- Description/content
- Images
- Tags
- Stock status (in_stock)
- Sale status (is_on_sale, sale_price)
- New arrival flag

## Tips

1. **Backup first**: Make a backup of your `content/products/` folder before importing
2. **Test with one row**: Try importing just a few rows first to verify
3. **Check the summary**: Review the import summary to ensure expected results
4. **Update content later**: Use the dashboard to add/edit product descriptions and images

## Troubleshooting

### "Row X: Skipping - no SKU"
**Solution**: Ensure every product row has a SKU value

### "Row X: Skipping SKU 123 - no English name"
**Solution**: Ensure every product has an English_name value

### "Row X: ERROR - ..."
**Solution**: Check the error message for details. Common issues:
- Invalid number format in price fields
- Special characters in product names
- File permissions

## CSV Data Cleaning Tips

Before importing, ensure your CSV:
- Has no completely empty rows
- Has valid numbers for all price/cost fields
- Has no special characters that might break file paths
- Uses supported date formats for pre-orders:
  - Year/Month with slash: `2025/10`, `2025/09`
  - Year-Month abbrev: `25-Nov` (means 2025-Nov), `25-Dec` (means 2025-Dec)
  - Year-Month numeric: `2025-11`, `2025-12`
  - ISO format: `2025-11-23`
