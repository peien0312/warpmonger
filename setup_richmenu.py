#!/usr/bin/env python3
"""Create/replace the OA rich menus (圖文選單) — run on the VM from the site dir:

    venv/bin/python setup_richmenu.py                  # create menus, set guest default
    venv/bin/python setup_richmenu.py --link-existing  # also switch already-bound members
    venv/bin/python setup_richmenu.py --regen-mock     # rebuild the placeholder images

Two menus, resolved at runtime by NAME (no IDs stored anywhere):
  abbeys-guest   default for everyone — push toward binding
  abbeys-member  linked per-user once bound (webhook / LINE Login hook)

Images live at static/richmenu/guest.png + member.png (2500x1686, 3x2 grid).
The committed ones are typed-label mockups — replace the PNGs with real
designs and re-run this script (menu areas/actions stay the same, so keep
the same 3x2 cell layout).
"""
import argparse
import os
import sys

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import linepush   # noqa: E402

SITE = "https://abbeystoys.com"
W, H = 2500, 1686
COLS, ROWS = 3, 2
IMG_DIR = os.path.join(os.path.dirname(__file__), "static", "richmenu")

# (label, sublabel, action) per cell, left→right then top→bottom.
# Keep cell POSITIONS in sync with the menu images.
GUEST_CELLS = [
    ("逛新品", "最新到貨商品",
     {"type": "message", "text": "新品到貨"}),
    ("商品查詢", "輸入名稱找商品",
     {"type": "message", "text": "商品查詢"}),
    ("綁定會員", "領取綁定禮折價券",
     {"type": "uri", "uri": f"{SITE}/account"}),
    ("查訂單", "訂單記錄與狀態",
     {"type": "uri", "uri": f"{SITE}/account"}),
    ("聯絡老闆", "直接留言詢問",
     {"type": "message", "text": "我想詢問"}),
    ("前往官網", "阿北玩具堂",
     {"type": "uri", "uri": SITE}),
]

MEMBER_CELLS = [
    ("查訂單", "訂單記錄與狀態",
     {"type": "uri", "uri": f"{SITE}/account"}),
    ("商品查詢", "輸入名稱找商品",
     {"type": "message", "text": "商品查詢"}),
    ("新品到貨", "最新到貨商品",
     {"type": "message", "text": "新品到貨"}),
    ("我的優惠券", "可用折價券",
     {"type": "uri", "uri": f"{SITE}/account"}),
    ("聯絡老闆", "直接留言詢問",
     {"type": "message", "text": "我想詢問"}),
    ("前往官網", "阿北玩具堂",
     {"type": "uri", "uri": SITE}),
]

MENUS = [
    (linepush.MENU_GUEST, "選單", GUEST_CELLS, "guest.png",
     ("#8B4513", "#A0522D")),   # warm browns (site brand-ish)
    (linepush.MENU_MEMBER, "會員選單", MEMBER_CELLS, "member.png",
     ("#1B4332", "#2D6A4F")),   # greens so 會員 menu is visibly different
]


def _cell_rect(i):
    cw, ch = W // COLS, H // ROWS
    col, row = i % COLS, i // COLS
    # last column/row absorbs the integer-division remainder
    w = W - cw * (COLS - 1) if col == COLS - 1 else cw
    h = H - ch * (ROWS - 1) if row == ROWS - 1 else ch
    return col * cw, row * ch, w, h


def _find_cjk_font():
    for path in (
        "/System/Library/Fonts/PingFang.ttc",                       # macOS
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",   # debian
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ):
        if os.path.exists(path):
            return path
    return None


def make_mock(path, cells, colors):
    """Placeholder menu image: colored 3x2 grid with typed labels."""
    from PIL import Image, ImageDraw, ImageFont
    font_path = _find_cjk_font()
    if font_path:
        f_big = ImageFont.truetype(font_path, 150)
        f_small = ImageFont.truetype(font_path, 64)
    else:  # CJK will tofu with the default font; mocks get replaced anyway
        f_big = f_small = ImageFont.load_default()
    img = Image.new("RGB", (W, H), colors[0])
    d = ImageDraw.Draw(img)
    for i, (label, sub, _action) in enumerate(cells):
        x, y, w, h = _cell_rect(i)
        d.rectangle([x, y, x + w - 1, y + h - 1],
                    fill=colors[i % 2], outline="#FFFFFF", width=6)
        d.text((x + w / 2, y + h / 2 - 50), label, font=f_big,
               fill="#FFFFFF", anchor="mm")
        d.text((x + w / 2, y + h / 2 + 90), sub, font=f_small,
               fill="#E8E0D8", anchor="mm")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG")
    print(f"  mock image -> {path}")


def menu_spec(name, chat_bar, cells):
    return {
        "size": {"width": W, "height": H},
        "selected": True,  # menu opens expanded
        "name": name,
        "chatBarText": chat_bar,
        "areas": [{
            "bounds": dict(zip(("x", "y", "width", "height"), _cell_rect(i))),
            "action": action,
        } for i, (_l, _s, action) in enumerate(cells)],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--regen-mock", action="store_true",
                    help="rebuild placeholder images even if they exist")
    ap.add_argument("--mock-only", action="store_true",
                    help="only (re)build images; no LINE API calls")
    ap.add_argument("--link-existing", action="store_true",
                    help="switch every already-bound member to the member menu")
    args = ap.parse_args()

    for _name, _bar, cells, fname, colors in MENUS:
        path = os.path.join(IMG_DIR, fname)
        if args.regen_mock or not os.path.exists(path):
            make_mock(path, cells, colors)
    if args.mock_only:
        return

    if not linepush.enabled():
        sys.exit("LINE_CHANNEL_ACCESS_TOKEN/SECRET not set — check .env")

    existing = {m.get("name"): m["richMenuId"] for m in linepush.richmenu_list()}
    ids = {}
    for name, chat_bar, cells, fname, _colors in MENUS:
        if name in existing:
            print(f"deleting old {name} ({existing[name]})")
            linepush.richmenu_delete(existing[name])
        rid = linepush.richmenu_create(menu_spec(name, chat_bar, cells))
        with open(os.path.join(IMG_DIR, fname), "rb") as fh:
            linepush.richmenu_upload_image(rid, fh.read())
        ids[name] = rid
        print(f"created {name} -> {rid}")

    linepush.richmenu_set_default(ids[linepush.MENU_GUEST])
    print(f"default menu = {linepush.MENU_GUEST}")

    if args.link_existing:
        import memberdb
        uids = memberdb.all_line_user_ids()
        ok = 0
        linepush._menu_ids.update(ids)
        for uid in uids:
            ok += bool(linepush.richmenu_link_user(uid))
        print(f"member menu linked for {ok}/{len(uids)} bound members")


if __name__ == "__main__":
    main()
