# Salessite Products Import Guide

Import products from your old salessite structure at `/Users/peienwang/salessite/products/` including all images.

## What It Does

The import script:
- ✅ Reads products from old salessite directory structure
- ✅ Extracts SKU from directory names (e.g., `product-name_6973130378872`)
- ✅ Merges `editor/` and `gallery/` images into single `images/` folder
- ✅ Copies video files (.mp4, .mov, .avi, .webm) from product root
- ✅ Matches with CSV data by SKU for complete product details
- ✅ Updates existing products or creates new ones
- ✅ Preserves existing descriptions and tags

## Directory Structure

**Old Salessite:**
```
/Users/peienwang/salessite/products/
├── product-name_6973130378872/
│   ├── editor/
│   │   ├── editor_1.jpg
│   │   ├── editor_2.jpg
│   │   └── ...
│   ├── gallery/
│   │   ├── gallery_1.jpg
│   │   ├── gallery_2.jpg
│   │   └── ...
│   └── video_001.mp4 (optional)
```

**New Site (after import):**
```
content/products/
├── Category/
│   └── product-name/
│       ├── product.md
│       ├── tags.txt
│       └── images/
│           ├── editor_1.jpg
│           ├── editor_2.jpg
│           ├── gallery_1.jpg
│           ├── gallery_2.jpg
│           └── video_001.mp4
```

## Usage

### Basic Import

```bash
# Activate virtual environment
source venv/bin/activate

# Run the import
python3 import_from_salessite.py
```

The script will:
1. Load CSV data from `products.csv` (if available)
2. Process all 426 products from salessite
3. Match by SKU with existing products
4. Copy all images from `editor/` and `gallery/` folders
5. Create or update products with complete data

## How SKU Matching Works

1. **Extract SKU** from directory name: `product-name_6973130378872` → SKU: `6973130378872`
2. **Check existing products** in database by SKU
3. **Check CSV data** for product details by SKU

### If Product Exists (Update)
- Keeps existing category and slug
- Preserves existing description
- Updates all fields from CSV
- Adds any new images from salessite

### If Product is New (Create)
- Uses `series` from CSV as category
- Creates slug from English name
- Copies all images
- Sets all fields from CSV

### If No CSV Data
- Creates product with SKU and basic info
- Category: "Imported"
- Uses directory name as product name
- Still copies all images

## What Gets Imported

### From CSV (if available)
- ✅ All product details (title, names, specs)
- ✅ Pricing and cost data
- ✅ Series, scale, size, weight

### From Salessite
- ✅ All images from `editor/` folder
- ✅ All images from `gallery/` folder
- ✅ All video files from product root (.mp4, .mov, .avi, .webm)
- ✅ SKU from directory name

### Preserved from Existing
- ✅ Product descriptions
- ✅ Tags
- ✅ Category (for existing products)
- ✅ Status flags

## Example Output

```
Salessite Products Import Script
============================================================
Source: /Users/peienwang/salessite/products
Target: /Users/peienwang/toy-seller-site/content/products
============================================================

Loaded 442 products from CSV
Found 442 existing products in database

Processing 426 products from salessite...

[1/426] UPDATE Warhammer 40,000/adepta-sororitas-abbess-sanctorum-morvenn-vahl
    Copied: editor_1.jpg (editor)
    Copied: editor_2.jpg (editor)
    Copied: gallery_1.jpg (gallery)
    Copied: gallery_2.jpg (gallery)
[2/426] UPDATE Warhammer 40,000/adepta-sororitas-battle-sister-sister-jurel
    Copied: editor_1.jpg (editor)
...

============================================================
IMPORT SUMMARY
============================================================
Created:       0
Updated:       426
Skipped:       0
Errors:        0
Images Copied: 3847
Total:         426
============================================================
```

## After Import

1. **Check products in dashboard** - Verify images loaded correctly
2. **Add descriptions** - Use dashboard to add product descriptions
3. **Run regular CSV import** - Keep data synced with `import_products.py`

## Notes

- Images and videos are copied (not moved) - originals remain in salessite
- Duplicate files are skipped (won't overwrite existing)
- Both `editor_*.jpg` and `gallery_*.jpg` files are combined
- Video files are also imported and can be played directly on product pages
- Files maintain their original filenames for reference
- Videos display with a play button thumbnail in the image gallery

## Troubleshooting

### "Salessite products directory not found"
**Solution**: Check that `/Users/peienwang/salessite/products/` exists

### "No images copied"
**Solution**: Verify `editor/` and `gallery/` folders exist in product directories

### "SKU not found in CSV"
**Solution**: Product will still import with basic info, but won't have detailed specs
