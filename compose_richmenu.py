#!/usr/bin/env python3
"""Compose the rich-menu images from per-cell icon art (run locally on the Mac).

    venv/bin/python compose_richmenu.py [--icons-src DIR]

Reads cleaned icons from static/richmenu/icons/<name>.png. With --icons-src,
first cleans raw AI-generated icons from DIR (patches the bottom-right
AI 生成 watermark with sampled background color) into that folder.

Outputs static/richmenu/guest.png + member.png (2500x1686, 3x2 grid, label
band per cell — brown band = guest menu, green = member). After composing:
commit, deploy, then on the VM run  setup_richmenu.py --link-existing.
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

W, H = 2500, 1686
COLS, ROWS = 3, 2
BAND_H = 200
ROOT = os.path.dirname(os.path.abspath(__file__))
ICON_DIR = os.path.join(ROOT, "static", "richmenu", "icons")
OUT_DIR = os.path.join(ROOT, "static", "richmenu")

ICON_NAMES = ["阿北開講", "新品上架", "優惠券", "商品查詢", "前往官網", "訂單查詢"]

# (label, sublabel or None, icon name) — POSITIONS must match setup_richmenu
GUEST_LAYOUT = [
    ("逛新品", "最新上架．含預購", "新品上架"),
    ("商品查詢", "輸入名稱找商品", "商品查詢"),
    ("綁定會員", "領取綁定禮折價券", "優惠券"),
    ("查訂單", None, "訂單查詢"),
    ("阿北開講", "最新文章與開箱", "阿北開講"),
    ("前往官網", None, "前往官網"),
]
MEMBER_LAYOUT = [
    ("查訂單", None, "訂單查詢"),
    ("商品查詢", "輸入名稱找商品", "商品查詢"),
    ("最新上架", "新品與預購資訊", "新品上架"),
    ("我的優惠券", None, "優惠券"),
    ("阿北開講", "最新文章與開箱", "阿北開講"),
    ("前往官網", None, "前往官網"),
]


def _cell_rect(i):
    cw, ch = W // COLS, H // ROWS
    col, row = i % COLS, i // COLS
    w = W - cw * (COLS - 1) if col == COLS - 1 else cw
    h = H - ch * (ROWS - 1) if row == ROWS - 1 else ch
    return col * cw, row * ch, w, h


def _font(size):
    for path in ("/System/Library/Fonts/STHeiti Medium.ttc",
                 "/System/Library/Fonts/PingFang.ttc",
                 "/System/Library/Fonts/Hiragino Sans GB.ttc",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def clean_icon(src_path, out_path):
    """Patch the AI 生成 watermark (bottom-right badge + bottom-edge text)
    with background color sampled away from the art, then downscale."""
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    bg = im.getpixel((int(w * 0.08), int(h * 0.92)))
    d = ImageDraw.Draw(im)
    d.rectangle([int(w * 0.70), int(h * 0.82), w, h], fill=bg)   # badge
    d.rectangle([0, int(h * 0.955), w, h], fill=bg)              # edge text
    im = im.resize((1000, 1000), Image.LANCZOS)
    im.save(out_path, "PNG")
    print(f"  cleaned {os.path.basename(src_path)} -> {out_path}")


def _cover(im, w, h):
    iw, ih = im.size
    scale = max(w / iw, h / ih)
    im = im.resize((round(iw * scale), round(ih * scale)), Image.LANCZOS)
    x = (im.width - w) // 2
    y = (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def compose(layout, accent, out_path):
    canvas = Image.new("RGB", (W, H), "#0e131c")
    f_label = _font(92)
    f_sub = _font(44)
    for i, (label, sub, icon) in enumerate(layout):
        x, y, w, h = _cell_rect(i)
        art = Image.open(os.path.join(ICON_DIR, icon + ".png"))
        canvas.paste(_cover(art, w, h), (x, y))
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([0, h - BAND_H, w, h], fill=accent + (225,))
        canvas.paste(Image.alpha_composite(
            canvas.crop((x, y, x + w, y + h)).convert("RGBA"), overlay
        ).convert("RGB"), (x, y))
        d = ImageDraw.Draw(canvas)
        cy = y + h - BAND_H // 2
        if sub:
            d.text((x + w / 2, cy - 32), label, font=f_label,
                   fill="#FFFFFF", anchor="mm")
            d.text((x + w / 2, cy + 58), sub, font=f_sub,
                   fill="#E8E0D8", anchor="mm")
        else:
            d.text((x + w / 2, cy), label, font=f_label,
                   fill="#FFFFFF", anchor="mm")
        # thin separators between cells
        d.rectangle([x, y, x + w - 1, y + h - 1], outline="#0e131c", width=3)
    canvas.save(out_path, "PNG", optimize=True)
    kb = os.path.getsize(out_path) // 1024
    print(f"  composed -> {out_path} ({kb} KB)")
    if kb > 990:  # LINE rich-menu image limit is 1 MB
        canvas.save(out_path.replace(".png", ".jpg"), "JPEG", quality=88)
        print("  WARNING: over 1MB — wrote a JPEG fallback; adjust uploader")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--icons-src", help="dir of raw (watermarked) icon jpgs")
    args = ap.parse_args()
    os.makedirs(ICON_DIR, exist_ok=True)
    if args.icons_src:
        for name in ICON_NAMES:
            src = os.path.join(args.icons_src, name + ".jpg")
            clean_icon(src, os.path.join(ICON_DIR, name + ".png"))
    compose(GUEST_LAYOUT, (0x8B, 0x45, 0x13),
            os.path.join(OUT_DIR, "guest.png"))
    compose(MEMBER_LAYOUT, (0x1B, 0x43, 0x32),
            os.path.join(OUT_DIR, "member.png"))


if __name__ == "__main__":
    main()
