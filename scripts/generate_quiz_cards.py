#!/usr/bin/env python3
"""Generate the quiz share-card OG images (static/images/quiz/*.png).

Dev-only. Run with the repo venv:
    source venv/bin/activate
    python3 scripts/generate_quiz_cards.py

Renders 17 PNGs at 1200x630 (the OG-image standard): one per quiz result
key plus default.png. Pure text + geometry in the shop's stained-glass
identity — NO character artwork (Games Workshop IP).

Fonts (Noto Serif TC + Cinzel, both OFL) are NOT bundled: download them into
QUIZ_FONT_DIR (default: the session scratchpad) before running. See the
FONTS notes below. Fonts are never committed.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

# --- (key -> character, legion) --------------------------------------------
# KEEP IN SYNC with QUIZ_RESULTS in app.py. 16 results; character names are
# the large line, legion the sub-line. (Copied, not imported, so this dev
# script has no Flask/app.py import dependency.)
RESULTS = {
    'ICRD': ('羅伯特·基里曼', '極限戰士'),
    'ICRS': ('貝利薩留·考爾', '機械神教'),
    'ICFD': ('羅格·多恩', '帝國之拳'),
    'ICFS': ('萊恩·艾爾莊森', '暗黑天使'),
    'IHFD': ('聖吉爾斯', '血天使'),
    'IHFS': ('賈曼·汗', '白疤'),
    'IHRD': ('里曼·魯斯', '太空野狼'),
    'IHRS': ('康斯坦丁·瓦爾多', '帝皇禁軍'),
    'XCRD': ('佩圖拉博', '鋼鐵勇士'),
    'XCRS': ('阿爾法留斯', '阿爾法軍團'),
    'XCFD': ('莫塔里安', '死亡守衛'),
    'XCFS': ('馬格努斯', '千子'),
    'XHFD': ('安格隆', '吞世者'),
    'XHFS': ('康拉德·科茲', '午夜領主'),
    'XHRD': ('歐克大老大', '歐克'),
    'XHRS': ('荷魯斯', '荷魯斯之子'),
}

# --- brand palette (see CLAUDE.md design identity) -------------------------
WALNUT      = (30, 23, 18)      # #1E1712  background
CARD        = (52, 42, 33)      # #342A21  panel
LEAD        = (23, 16, 11)      # #17100B  darkest
AMBER       = (217, 164, 65)    # #D9A441  candle amber
PARCHMENT   = (230, 218, 196)   # #E6DAC4  parchment
GLASS_BLUE  = (143, 163, 184)   # #8FA3B8  glass blue

W, H = 1200, 630
CX = W // 2

_SCRATCH = os.environ.get(
    "SCRATCHPAD_DIR",
    "/private/tmp/claude-501/-Users-peienwang-toy-seller-site/"
    "5ca62f26-7006-4054-9827-7c5edcbc8c29/scratchpad")
FONT_DIR = os.environ.get("QUIZ_FONT_DIR", os.path.join(_SCRATCH, "quiz-fonts"))
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "static", "images", "quiz")

NOTO_PATH = os.path.join(FONT_DIR, "NotoSerifTC.ttf")
CINZEL_PATH = os.path.join(FONT_DIR, "Cinzel.ttf")
_HAS_CINZEL = os.path.exists(CINZEL_PATH)


def _font(path, size, weight):
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass   # static font — ignore
    return f


def noto(size, weight=400):
    return _font(NOTO_PATH, size, weight)


def latin(size, weight=600):
    """Cinzel for latin display text; falls back to Noto Serif TC."""
    return _font(CINZEL_PATH if _HAS_CINZEL else NOTO_PATH, size, weight)


def fit_font(text, max_w, start, min_size, weight=700):
    """Largest Noto size (<= start, >= min_size) whose text fits max_w wide."""
    size = start
    while size > min_size:
        if noto(size, weight).getlength(text) <= max_w:
            break
        size -= 2
    return noto(size, weight)


def draw_centered(draw, y, text, font, fill):
    draw.text((CX, y), text, font=font, fill=fill, anchor="mm")


def draw_stack(draw, center_y, items):
    """Vertically stack centered lines, measuring each line's ink height so
    spacing is uniform regardless of font size, then center the whole block
    on center_y. items: list of (text, font, fill, gap_after_px)."""
    metrics = []
    total = 0
    for i, (text, font, fill, gap) in enumerate(items):
        b = font.getbbox(text)
        h = b[3] - b[1]
        metrics.append((b[1], h))
        total += h + (gap if i < len(items) - 1 else 0)
    y = center_y - total / 2
    for (text, font, fill, gap), (ink_top, h) in zip(items, metrics):
        draw.text((CX, y - ink_top), text, font=font, fill=fill, anchor="ma")
        y += h + gap


def draw_tracked_centered(draw, y, segments, fill):
    """Draw a horizontally-centered line of (text, font, tracking) segments;
    tracking is extra px between characters (manual, since raqm may be off)."""
    total = 0
    for text, font, track in segments:
        for ch in text:
            total += font.getlength(ch) + track
        total -= track   # no trailing gap after the segment's last char
    x = CX - total / 2
    for text, font, track in segments:
        for ch in text:
            draw.text((x, y), ch, font=font, fill=fill, anchor="lm")
            x += font.getlength(ch) + track


def draw_frame(draw):
    """Card panel + double rule (amber outer 3px, glass-blue inner 2px)
    + small amber corner diamonds."""
    m = 34
    draw.rectangle([m, m, W - m, H - m], fill=CARD)
    # outer amber rule
    a = m + 20
    draw.rectangle([a, a, W - a, H - a], outline=AMBER, width=3)
    # inner glass-blue rule
    b = a + 9
    draw.rectangle([b, b, W - b, H - b], outline=GLASS_BLUE, width=2)
    # corner diamonds on the amber rule
    d = 11
    for cx, cy in [(a, a), (W - a, a), (a, H - a), (W - a, H - a)]:
        draw.polygon([(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)],
                     fill=AMBER, outline=WALNUT)


def render_card(character, legion):
    img = Image.new("RGB", (W, H), WALNUT)
    d = ImageDraw.Draw(img)
    draw_frame(d)

    # masthead (tracked, glass blue)
    draw_tracked_centered(d, 118, [
        ("ABBEY'S TOYS", latin(30, 600), 4),
        ("  ·  原體測驗", noto(30, 500), 6),
    ], GLASS_BLUE)

    # character name — very large amber, shrink-to-fit within ~1000px.
    # 我是 / name / legion are stacked and centered as one block so the gaps
    # stay even whether the name is 3 or 8 characters.
    name_font = fit_font(character, max_w=1000, start=150, min_size=92, weight=700)
    draw_stack(d, 312, [
        ("我是", noto(38, 400), PARCHMENT, 26),
        (character, name_font, AMBER, 30),
        (legion, noto(54, 500), PARCHMENT, 0),
    ])

    # thin amber divider
    d.line([(CX - 150, 484), (CX + 150, 484)], fill=AMBER, width=2)

    draw_tracked_centered(d, 520, [
        ("你是哪位原體？　", noto(30, 400), 3),
        ("abbeystoys.com/quiz", latin(30, 600), 3),
    ], GLASS_BLUE)
    return img


def render_default():
    img = Image.new("RGB", (W, H), WALNUT)
    d = ImageDraw.Draw(img)
    draw_frame(d)

    draw_tracked_centered(d, 150, [
        ("ABBEY'S TOYS", latin(32, 600), 5),
        ("  ·  原體測驗", noto(32, 500), 6),
    ], GLASS_BLUE)

    draw_centered(d, 300, "你是哪位原體？", fit_font("你是哪位原體？", 980, 118, 80, 700), AMBER)
    draw_centered(d, 410, "16 題原體人格測驗", noto(46, 500), PARCHMENT)

    d.line([(CX - 150, 470), (CX + 150, 470)], fill=AMBER, width=2)
    draw_tracked_centered(d, 528, [
        ("abbeystoys.com/quiz", latin(30, 600), 3),
    ], GLASS_BLUE)
    return img


def main():
    if not os.path.exists(NOTO_PATH):
        sys.exit(f"missing font: {NOTO_PATH}\n"
                 "Download Noto Serif TC (OFL) into QUIZ_FONT_DIR first, e.g.:\n"
                 "  curl -sL -o \"$QUIZ_FONT_DIR/NotoSerifTC.ttf\" "
                 "https://github.com/google/fonts/raw/main/ofl/notoseriftc/"
                 "'NotoSerifTC[wght].ttf'")
    os.makedirs(OUT_DIR, exist_ok=True)
    if not _HAS_CINZEL:
        print("note: Cinzel not found — using Noto Serif TC for latin text too.")

    for key, (character, legion) in RESULTS.items():
        render_card(character, legion).save(os.path.join(OUT_DIR, f"{key}.png"))
        print(f"  {key}.png  ({character} · {legion})")
    render_default().save(os.path.join(OUT_DIR, "default.png"))
    print("  default.png")
    print(f"done — {len(RESULTS) + 1} cards in {OUT_DIR}")


if __name__ == "__main__":
    main()
