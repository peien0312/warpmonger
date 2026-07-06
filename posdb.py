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

KIND_ORDER = "CASE kind WHEN 'cover' THEN 0 WHEN 'gallery' THEN 1 ELSE 2 END"


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


def _availability(row, inv, waiting, today):
    """Availability state per the shop's fulfillment rules (priority order):
      in_stock  現貨            tw - waiting > 0 (preorder flag ignored)
      incoming  約2週內到貨      tw + in_transit + china - waiting > 0
      preorder  預購            is_preorder with a future date, no stock
      orderable 可訂購 約2-3週   not deprecated -> can order from JoyToy
      inquiry   絕版詢價         deprecated, not preorder -> price on inquiry
    A preorder whose date has passed is treated as released (falls through
    to orderable/inquiry)."""
    tw = inv.get("taiwan", 0)
    total = tw + inv.get("in_transit", 0) + inv.get("china", 0)
    if tw - waiting > 0:
        return "in_stock"
    if total - waiting > 0:
        return "incoming"
    preorder_date = str(row["preorder_date"] or "")[:10]
    if row["is_preorder"] and preorder_date > today:
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
        bucket = detail if r["kind"] == "detail" else gallery
        bucket.setdefault(r["product_id"], []).append(name)

    inv = {}  # product_id -> {location: qty}
    for r in cur.execute("""
        SELECT product_id, location, SUM(quantity) AS qty
        FROM inventory GROUP BY product_id, location
    """):
        inv.setdefault(r["product_id"], {})[r["location"]] = r["qty"] or 0

    waiting = {}  # product_id -> qty in 待配貨 on live orders
    for r in cur.execute("""
        SELECT oi.product_id, SUM(oi.quantity) AS qty
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE oi.status = '待配貨' AND (o.is_deleted = 0 OR o.is_deleted IS NULL)
        GROUP BY oi.product_id
    """):
        waiting[r["product_id"]] = r["qty"] or 0

    from datetime import date
    today = date.today().isoformat()

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
                              waiting.get(row["id"], 0), today)
        products.append({
            "slug": row["slug"],
            "category": row["category_slug"],
            "title": _norm(row["en_name"] or row["zhtw_name"] or row["sku"]),
            "price": 0,
            "description": row["description_zhtw"] or row["description"] or "",
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
            "is_on_sale": bool(row["is_on_sale"]),
            "sale_price": row["sale_price_twd"] or 0,
            "is_new_arrival": bool(row["is_new_arrival"]),
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
            "cost_tw": 0,
            "order_weight": row["order_weight"] or 0,
            "group": row["storefront_group"] or "",
            "_pos_sku": row["sku"] or "",   # media folder key
        })
    conn.close()

    products.sort(key=lambda p: (-p["order_weight"], p["title"].lower()))
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
        } for r in conn.execute("SELECT * FROM storefront_categories")]
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


def get_featured_tags():
    tags = _setting_json("featured_tags", [])
    tags.sort(key=lambda t: -t.get("order_weight", 0) if isinstance(t, dict) else 0)
    return tags


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
        })
    return posts


def get_blog_post(slug):
    return next((p for p in get_blog_posts() if p["slug"] == slug), None)


def get_codex_entries():
    entries = []
    for item in _posts("codex"):
        r, extra = item["row"], item["extra"]
        body = r["body"] or ""
        entries.append({
            "slug": r["slug"], "title": r["title"],
            "aliases": extra.get("aliases") or [],
            "content": body,
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


# ----- member order history (web orders live in the POS DB, read-only) -----

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
    for o in orders:
        o["items"] = [dict(r) for r in conn.execute("""
            SELECT wi.quantity, wi.unit_price_twd, wi.availability,
                   p.zhtw_name, p.en_name, p.sku, p.slug, p.category_slug
            FROM web_order_items wi JOIN products p ON p.id = wi.product_id
            WHERE wi.web_order_id = ?
        """, (o["id"],))]
        o["fulfillment"] = []
        for key in ("order_id_now", "order_id_later"):
            if o.get(key):
                row = conn.execute(
                    "SELECT status FROM orders WHERE id = ?", (o[key],)).fetchone()
                if row:
                    o["fulfillment"].append(row["status"])
    conn.close()
    return orders
