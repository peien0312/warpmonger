"""Read-only data layer over the warpmonger-pos SQLite database.

The POS is the single source of truth; this module replaces the old
flat-file (markdown) loaders with direct queries so the site is realtime.
The POS DB runs in WAL mode (Litestream), so concurrent reads while the
POS writes are safe. All connections here are opened read-only.

Dict shapes intentionally mirror the old app.py loaders so templates and
routes need no changes. Results are cached in-process and invalidated
whenever the DB file's mtime changes (any POS write bumps it).
"""

import json
import os
import sqlite3
import threading

_CANDIDATE_DBS = [
    os.environ.get("POS_DB", ""),
    os.path.expanduser("~/warpmonger_dashboard/data/warpmonger.db"),  # prod VM
    os.path.join(os.path.dirname(__file__), "..", "warpmonger-pos", "data", "warpmonger.db"),  # dev
]
POS_DB = next((p for p in _CANDIDATE_DBS if p and os.path.exists(p)), _CANDIDATE_DBS[1])
POS_MEDIA = os.environ.get("POS_MEDIA") or os.path.join(os.path.dirname(POS_DB), "..", "media")
POS_MEDIA = os.path.abspath(POS_MEDIA)

_lock = threading.Lock()
_cache = {"stamp": None}

# gallery-family first (cover=first, then gallery by sort_order), editor last.
# 'cover'/'detail' are legacy kinds tolerated until the POS image-kind migration.
KIND_ORDER = ("CASE kind WHEN 'editor' THEN 2 WHEN 'detail' THEN 2 "
              "WHEN 'cover' THEN 0 ELSE 1 END")


def _norm(text):
    """Collapse newlines/whitespace — vendor imports leave embedded newlines
    in names/series, which break layouts and inline-JS string literals."""
    return " ".join(str(text).split()) if text else ""


def _conn():
    conn = sqlite3.connect(f"file:{POS_DB}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def db_mtime():
    """mtime of the DB (incl. WAL) — changes on every POS write."""
    stamp = 0.0
    for suffix in ("", "-wal"):
        try:
            stamp = max(stamp, os.path.getmtime(POS_DB + suffix))
        except OSError:
            pass
    return stamp


def _fresh():
    """Return the cache dict, cleared if the DB changed since last use."""
    stamp = db_mtime()
    with _lock:
        if _cache.get("stamp") != stamp:
            _cache.clear()
            _cache["stamp"] = stamp
        return _cache


def _arrival_display(preorder_date):
    """Customer-facing arrival: vendor release month + 1 (China->Taiwan
    shipping), rendered as e.g. 2026年9月. Once that month is in the past
    (vendor slipped the release) return "" — the badge shows plain 預購
    rather than a stale promise."""
    raw = str(preorder_date or "")[:7]
    try:
        y, m = int(raw[:4]), int(raw[5:7])
    except ValueError:
        return ""
    m += 1
    if m > 12:
        y, m = y + 1, 1
    from datetime import date
    now = date.today()
    if (y, m) < (now.year, now.month):
        return ""
    return f"{y}年{m}月"


def member_price_of(row):
    """會員價: regular_price_twd when set (>0), else 90% of 售價 rounded.
    Sale price caps it — members never pay more than the public price."""
    selling = row["selling_price_twd"] or 0
    if not selling:
        return 0
    member = row["regular_price_twd"] if (row["regular_price_twd"] or 0) > 0 \
        else round(selling * 0.9)
    guest = row["sale_price_twd"] if (row["is_on_sale"] and (row["sale_price_twd"] or 0) > 0) \
        else selling
    return min(member, guest)


def _availability(row, inv, waiting, today):
    """Availability state per the shop's fulfillment rules (priority order):
      in_stock  現貨            tw - waiting_tw > 0 (preorder flag ignored)
      incoming  約2週內到貨      tw + in_transit + china - waiting > 0
      preorder  預購            is_preorder, no stock (date is display-only)
      orderable 可訂購 約2-3週   not deprecated -> can order from JoyToy
      inquiry   絕版詢價         deprecated, not preorder -> price on inquiry
    `waiting` is (all, taiwan_fillable): China-modded 待配貨 items (goods
    with a service child) can never take a Taiwan shelf unit, so only
    taiwan_fillable demand hides 現貨; all demand gates incoming.
    A passed preorder_date does NOT release the product (vendors slip
    dates) — it stays 預購 until stock actually arrives, which flips it
    to incoming/in_stock through the normal inventory flow. The date only
    drives the arrival-month display and is hidden once stale."""
    waiting_all, waiting_tw = waiting
    tw = inv.get("taiwan", 0)
    total = tw + inv.get("in_transit", 0) + inv.get("china", 0)
    if tw - waiting_tw > 0:
        return "in_stock"
    if total - waiting_all > 0:
        return "incoming"
    if row["is_preorder"]:
        return "preorder"
    if not row["is_deprecated"]:
        return "orderable"
    return "inquiry"


def _load_products():
    cache = _fresh()
    if "products" in cache:
        return cache["products"]

    conn = _conn()
    cur = conn.cursor()

    gallery, detail = {}, {}
    for r in cur.execute(f"""
        SELECT product_id, kind, filename FROM product_images
        ORDER BY product_id, {KIND_ORDER}, sort_order
    """):
        name = os.path.basename(r["filename"] or "")
        if not name:
            continue
        # editor (formerly 'detail') -> the rich section; cover/gallery -> gallery
        bucket = detail if r["kind"] in ("detail", "editor") else gallery
        bucket.setdefault(r["product_id"], []).append(name)

    inv = {}  # product_id -> {location: qty}
    for r in cur.execute("""
        SELECT product_id, location, SUM(quantity) AS qty
        FROM inventory GROUP BY product_id, location
    """):
        inv.setdefault(r["product_id"], {})[r["location"]] = r["qty"] or 0

    # product_id -> (all 待配貨 qty, taiwan-fillable qty) on live orders.
    # Items with a service child are China-modded — they never consume the
    # Taiwan shelf, so they don't count toward the tw side, UNLESS their
    # bound batch line is fully received (the modded unit is in Taiwan
    # stock, so the demand reserves the shelf like a plain item). Mirror of
    # the POS app/services/availability.py; keep in sync.
    waiting = {}
    for r in cur.execute("""
        SELECT oi.product_id, SUM(oi.quantity) AS qty,
               SUM(CASE WHEN EXISTS (SELECT 1 FROM order_items c
                        JOIN products cp ON cp.id = c.product_id
                        WHERE c.parent_item_id = oi.id
                          AND cp.product_type = 'service')
                    AND NOT EXISTS (SELECT 1 FROM batch_items b
                        WHERE b.order_item_id = oi.id AND b.quantity > 0
                          AND b.received_qty >= b.quantity)
                   THEN 0 ELSE oi.quantity END) AS qty_tw
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.status = '待配貨' AND (o.is_deleted = 0 OR o.is_deleted IS NULL)
        GROUP BY oi.product_id
    """):
        waiting[r["product_id"]] = (r["qty"] or 0, r["qty_tw"] or 0)

    from datetime import date, datetime as _dt, timedelta
    today = date.today().isoformat()
    # 新品上架 = created within the last 30 days (manual is_new_arrival still overrides)
    new_cutoff = _dt.now() - timedelta(days=30)

    def _is_new(created):
        if not created:
            return False
        try:
            return _dt.fromisoformat(str(created)[:19]) >= new_cutoff
        except ValueError:
            return False

    products = []
    for row in cur.execute("""
        SELECT * FROM products
        WHERE is_published = 1 AND is_deleted = 0
          AND slug IS NOT NULL AND category_slug IS NOT NULL
    """):
        try:
            tags = json.loads(row["tags"] or "[]")
        except Exception:
            tags = []
        avail = _availability(row, inv.get(row["id"], {}),
                              waiting.get(row["id"], (0, 0)), today)
        products.append({
            "slug": row["slug"],
            "category": row["category_slug"],
            "title": _norm(row["en_name"] or row["zhtw_name"] or row["sku"]),
            "price": 0,
            # `description` keeps the old zh-TW-first fallback for list views /
            # meta tags; the route picks _zhtw vs _enus by locale for the body.
            "description": row["description_zhtw"] or row["description"] or "",
            "description_zhtw": row["description_zhtw"] or "",
            "description_enus": row["description_enus"] or "",
            # gallery (cover first) drives cards + the thumbnail strip;
            # detail/editor images render as a long section below the fold.
            # Products with no gallery fall back to their detail images.
            "images": gallery.get(row["id"]) or detail.get(row["id"], []),
            "detail_images": detail.get(row["id"], []) if gallery.get(row["id"]) else [],
            "availability": avail,
            "in_stock": avail == "in_stock",
            "sku": row["barcode"] or "",
            "tags": tags,
            # 預購 badge/filter only when preorder is the *effective* state
            # (rule: in-stock overrides the preorder flag)
            "is_pre_order": avail == "preorder",
            "available_date": str(row["preorder_date"] or "")[:10],
            "available_display": _arrival_display(row["preorder_date"]) if avail == "preorder" else "",
            "is_on_sale": bool(row["is_on_sale"]),
            "sale_price": row["sale_price_twd"] or 0,
            "is_new_arrival": bool(row["is_new_arrival"]) or _is_new(row["created_at"]),
            "created_at": str(row["created_at"] or ""),
            "id": row["sku"] or "",
            "cn_name": _norm(row["cn_name"]),
            "zhtw_name": _norm(row["zhtw_name"]),
            "series": _norm(row["series"]),
            "scale": _norm(row["scale"]),
            "size": _norm(row["size"]),
            "weight": _norm(row["weight"]),
            "zhtw_price": 0,
            "cost": row["cost_cny"] or 0,
            # inquiry items don't show a price — the site renders 詢價 instead
            "final_price": 0 if avail == "inquiry" else (row["selling_price_twd"] or 0),
            "member_price": 0 if avail == "inquiry" else member_price_of(row),
            "cost_tw": 0,
            "order_weight": row["order_weight"] or 0,
            "group": row["storefront_group"] or "",
            "_pos_sku": row["sku"] or "",   # media folder key
        })
    conn.close()

    # order_weight (curation) wins; then buyable items ahead of 詢價/絕版; then title.
    _avail_rank = {"in_stock": 0, "incoming": 0, "preorder": 0, "orderable": 0,
                   "inquiry": 1}
    products.sort(key=lambda p: (-p["order_weight"],
                                 _avail_rank.get(p["availability"], 0),
                                 p["title"].lower()))
    cache["products"] = products
    return products


def _search_match(p, q):
    q = q.lower()
    return any(q in str(p.get(k) or "").lower()
               for k in ("title", "cn_name", "zhtw_name", "id", "sku"))


def get_products(category=None, search=None):
    products = _load_products()
    if category:
        products = [p for p in products if p["category"] == category]
    if search and search.strip():
        products = [p for p in products if _search_match(p, search.strip())]
    return products


def get_product(category, slug):
    # linear scan over the snapshot list — race-free against concurrent
    # cache invalidation (never re-reads the shared cache dict mid-call)
    for p in _load_products():
        if p["category"] == category and p["slug"] == slug:
            return p
    return None


def media_dir_for(category, slug):
    """Filesystem dir holding this product's images (POS media/<SKU>)."""
    p = get_product(category, slug)
    if not p or not p.get("_pos_sku"):
        return None
    return os.path.join(POS_MEDIA, p["_pos_sku"])


# ----- categories -----

def get_categories():
    cache = _fresh()
    if "categories" not in cache:
        conn = _conn()
        cats = [{
            "slug": r["slug"], "name": r["name"], "description": "",
            "order_weight": r["order_weight"] or 0, "icon": r["icon"] or "",
        } for r in conn.execute(
            "SELECT * FROM storefront_categories WHERE COALESCE(is_visible, 1) = 1")]
        conn.close()
        cats.sort(key=lambda c: (-c["order_weight"], c["name"].lower()))
        cache["categories"] = cats
    return cache["categories"]


def get_category(slug):
    return next((c for c in get_categories() if c["slug"] == slug), None)


# ----- settings-backed featured picks -----

def _setting_json(key, default):
    conn = _conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    try:
        return json.loads(row["value"]) if row else default
    except Exception:
        return default


def get_featured_products_refs():
    return _setting_json("featured_products", [])


def get_tag_glossary():
    """EN tag -> zh-TW display label. Tags are stored/filtered in English
    (stable keys); this maps them to Chinese labels for display only."""
    g = _setting_json("tag_glossary", {})
    return g if isinstance(g, dict) else {}


def get_featured_tags():
    tags = _setting_json("featured_tags", [])
    tags.sort(key=lambda t: -t.get("order_weight", 0) if isinstance(t, dict) else 0)
    return tags


def get_faction_tags():
    """Curated allowlist of faction / 軍團 tag names, used to build the
    per-category sub-nav (which of these appear in a given category)."""
    tags = _setting_json("faction_tags", [])
    return tags if isinstance(tags, list) else []


# ----- editorial posts -----

def _posts(ptype):
    cache = _fresh()
    key = f"posts_{ptype}"
    if key not in cache:
        conn = _conn()
        rows = conn.execute("""
            SELECT * FROM storefront_posts
            WHERE type = ? AND is_published = 1
            ORDER BY published_at DESC, slug
        """, (ptype,)).fetchall()
        conn.close()
        out = []
        for r in rows:
            try:
                extra = json.loads(r["extra"] or "{}")
            except Exception:
                extra = {}
            out.append({"row": dict(r), "extra": extra})
        cache[key] = out
    return cache[key]


def get_blog_posts():
    posts = []
    for item in _posts("blog"):
        r, extra = item["row"], item["extra"]
        body = r["body"] or ""
        posts.append({
            "slug": r["slug"], "title": r["title"],
            "date": str(r["published_at"] or "")[:10],
            "author": extra.get("author") or "",
            "excerpt": extra.get("excerpt") or body[:200],
            "content": body, "tags": extra.get("tags") or [],
            "cover": extra.get("cover") or "",
            "cover_caption": extra.get("cover_caption") or "",
            "cover_link": extra.get("cover_link") or "",
        })
    return posts


def get_blog_post(slug):
    return next((p for p in get_blog_posts() if p["slug"] == slug), None)


def get_codex_entries():
    entries = []
    for item in _posts("codex"):
        r, extra = item["row"], item["extra"]
        body = r["body"] or ""
        body_enus = (r["body_enus"] if "body_enus" in r.keys() else "") or ""
        title_zhtw = (r["title_zhtw"] if "title_zhtw" in r.keys() else "") or ""
        entries.append({
            "slug": r["slug"], "title": r["title"],
            "title_zhtw": title_zhtw,      # zh-TW display name (crosslinks: 中文（English）)
            "aliases": extra.get("aliases") or [],
            "content": body,               # zh-TW body (displayed by default)
            "content_enus": body_enus,     # English body (shown on /en)
            "excerpt": body[:200] + "..." if len(body) > 200 else body,
        })
    entries.sort(key=lambda e: e["title"].lower())
    return entries


def get_codex_entry(slug):
    return next((e for e in get_codex_entries() if e["slug"] == slug), None)


def get_promotions():
    promos = []
    for item in _posts("promotion"):
        r, extra = item["row"], item["extra"]
        body = r["body"] or ""
        promos.append({
            "slug": r["slug"], "title": r["title"],
            "date": str(r["published_at"] or "")[:10],
            "excerpt": extra.get("excerpt") or body[:200],
            "content": body,
            "products": extra.get("products") or [],
            "active": bool(extra.get("active")),
            "banner": extra.get("banner") or None,
        })
    return promos


def get_promotion(slug):
    return next((p for p in get_promotions() if p["slug"] == slug), None)


def get_active_promotion():
    return next((p for p in get_promotions() if p["active"] and p["banner"]), None)


def get_page(slug):
    for item in _posts("page"):
        r = item["row"]
        if r["slug"] == slug:
            return {"title": r["title"], "content": r["body"] or ""}
    return None


# ----- coupons (definitions managed in the POS; wallet lives in members.db) -----

def _load_coupons():
    """All coupon definitions, cached. Degrades to [] on a POS deployed before
    the coupons migration (the table may not exist yet)."""
    cache = _fresh()
    if "coupons" in cache:
        return cache["coupons"]
    out = []
    try:
        conn = _conn()
        out = [dict(r) for r in conn.execute("SELECT * FROM coupons")]
        conn.close()
    except sqlite3.OperationalError:
        out = []
    cache["coupons"] = out
    return out


def get_coupons():
    return _load_coupons()


def get_coupon(code):
    """A coupon definition by code (case-insensitive), or None."""
    code = (code or "").strip().upper()
    if not code:
        return None
    for c in _load_coupons():
        if (c.get("code") or "").upper() == code:
            return c
    return None


def get_auto_grant_coupon(kind):
    """First active, within-window coupon whose auto_grant == kind (lowest id),
    or None — the coupon to auto-grant on signup / review reward."""
    from datetime import date
    today = date.today().isoformat()
    best = None
    for c in _load_coupons():
        if (c.get("auto_grant") or "") != kind or not c.get("active"):
            continue
        vf = str(c.get("valid_from") or "")[:10]
        vu = str(c.get("valid_until") or "")[:10]
        if (vf and today < vf) or (vu and today > vu):
            continue
        if best is None or (c.get("id") or 0) < (best.get("id") or 0):
            best = c
    return best


# ----- member order history (web orders live in the POS DB, read-only) -----

# raw internal Order.status -> customer-friendly label; missing keys
# (棄單/呆帳/待補件) are hidden from customers entirely.
_FRIENDLY_STATUS = {
    "待配貨": "備貨中", "中國待發": "備貨中", "集運中": "運送中",
    "台灣庫存": "備貨完成，待出貨", "已出貨": "已出貨",
    "已結帳": "已完成", "已退貨": "已退貨",
}


def _enrich_orders(conn, orders):
    """Attach items, customer-friendly fulfillment status, pickup codes,
    amount due, and return requests."""
    for o in orders:
        o["items"] = [dict(r) for r in conn.execute("""
            SELECT wi.quantity, wi.unit_price_twd, wi.availability,
                   p.zhtw_name, p.en_name, p.sku, p.slug, p.category_slug
            FROM web_order_items wi JOIN products p ON p.id = wi.product_id
            WHERE wi.web_order_id = ?
        """, (o["id"],))]
        o["fulfillment"] = []
        o["shipping_codes"] = []
        o["returns"] = []
        # all internal orders converted from this web order (現貨/調貨/預購批,
        # incl. 拆單 copies); pre-migration POS lacks web_order_id -> fallback
        # to the legacy two link columns
        related = []
        try:
            related = [dict(r) for r in conn.execute(
                "SELECT * FROM orders WHERE web_order_id = ? "
                "AND (is_deleted IS NULL OR is_deleted = 0) ORDER BY id",
                (o["id"],))]
        except Exception:
            pass
        if not related:
            for key in ("order_id_now", "order_id_later"):
                if o.get(key):
                    r = conn.execute("SELECT * FROM orders WHERE id = ?", (o[key],)).fetchone()
                    if r:
                        related.append(dict(r))
        for row in related:   # robust to schema differences (shipping_carrier vs _type)
            label = _FRIENDLY_STATUS.get(row.get("status"))
            if label and label not in o["fulfillment"]:
                o["fulfillment"].append(label)
            if row.get("shipping_code"):
                o["shipping_codes"].append(
                    {"code": row["shipping_code"],
                     "type": row.get("shipping_carrier") or row.get("shipping_type") or ""})
        # amount due now — mirrors the POS _charge_now_twd: 現貨/調貨 portion,
        # but the whole priced order once a preorder is actively 待付款, and
        # only the remainder once part of the order was collected (paid_twd)
        # coupon/paid fields (may be absent on a pre-migration POS -> 0/'')
        o["coupon_discount_twd"] = o.get("coupon_discount_twd") or 0
        o["coupon_code"] = o.get("coupon_code") or ""
        o["paid_twd"] = o.get("paid_twd") or 0
        if o["paid_twd"] > 0:
            grand = max(0, sum((it["unit_price_twd"] or 0) * it["quantity"]
                               for it in o["items"])
                        + (o.get("shipping_fee_twd") or 0)
                        - (o.get("discount_twd") or 0)
                        - o["coupon_discount_twd"])
            o["amount_due"] = max(0, grand - o["paid_twd"])
        else:
            _now = ("in_stock", "incoming", "orderable")
            now_total = sum((it["unit_price_twd"] or 0) * it["quantity"]
                            for it in o["items"] if it["availability"] in _now)
            if now_total <= 0 and o.get("payment_status") == "待付款":
                now_total = sum((it["unit_price_twd"] or 0) * it["quantity"]
                                for it in o["items"] if it["availability"] != "inquiry")
            o["amount_due"] = (max(0, now_total + (o.get("shipping_fee_twd") or 0)
                                   - (o.get("discount_twd") or 0)
                                   - o["coupon_discount_twd"]) if now_total > 0 else 0)

    order_nos = [o["order_no"] for o in orders]
    if order_nos:
        try:
            ph = ",".join("?" * len(order_nos))
            rets = [dict(r) for r in conn.execute(
                f"SELECT * FROM web_returns WHERE order_no IN ({ph}) ORDER BY id DESC",
                order_nos)]
            for rr in rets:
                rr["items"] = [dict(r) for r in conn.execute("""
                    SELECT wri.quantity, wri.unit_price_twd,
                           p.zhtw_name, p.en_name, p.slug, p.category_slug
                    FROM web_return_items wri JOIN products p ON p.id = wri.product_id
                    WHERE wri.web_return_id = ?
                """, (rr["id"],))]
            by_order = {}
            for rr in rets:
                by_order.setdefault(rr["order_no"], []).append(rr)
            for o in orders:
                o["returns"] = by_order.get(o["order_no"], [])
        except Exception as e:
            print(f"load returns failed: {e}")
    return orders


def get_member_orders(email, phone):
    """Web orders matching a member's email or phone, newest first, with
    items and the fulfillment status of any converted internal orders."""
    clauses, params = [], []
    if email:
        clauses.append("email = ?")
        params.append(email)
    if phone:
        clauses.append("phone = ?")
        params.append(phone)
    if not clauses:
        return []

    conn = _conn()
    orders = [dict(r) for r in conn.execute(
        f"SELECT * FROM web_orders WHERE {' OR '.join(clauses)} ORDER BY id DESC LIMIT 50",
        params)]
    _enrich_orders(conn, orders)
    conn.close()
    return orders


def get_web_order(order_no):
    """A single web order by its order_no — for guest access via magic link
    or the 訂單查詢 lookup. Returns a dict (same shape as get_member_orders
    entries) or None."""
    if not order_no:
        return None
    conn = _conn()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM web_orders WHERE order_no = ? LIMIT 1", (order_no,))]
    _enrich_orders(conn, rows)
    conn.close()
    return rows[0] if rows else None
