"""Member data owned by the site (NOT the POS database).

The POS SQLite keeps its single-writer rule — members, wishlists and
arrival-notification subscriptions live in the site's own data/members.db,
where this Flask app is the only writer. Linking to POS customers happens
by phone at checkout time.
"""
import os
import json
import sqlite3

DB_PATH = os.environ.get(
    "MEMBERS_DB",
    os.path.join(os.path.dirname(__file__), "data", "members.db"),
)


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            google_sub TEXT UNIQUE NOT NULL,
            email TEXT,
            name TEXT,
            picture TEXT,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            sku TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(member_id, sku)
        );
        CREATE TABLE IF NOT EXISTS notify_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            sku TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notified_at TIMESTAMP,
            UNIQUE(member_id, sku)
        );
    """)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS member_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            label TEXT,
            recipient_name TEXT,
            recipient_phone TEXT,
            delivery TEXT,
            store_code TEXT,
            store_name TEXT,
            address TEXT,
            is_default BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS member_identities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            provider TEXT NOT NULL,
            subject TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, subject)
        );
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            result_key TEXT,
            character TEXT,
            legion TEXT,
            scores TEXT,
            member_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS product_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            sku TEXT NOT NULL,
            category TEXT,
            slug TEXT,
            product_name TEXT,
            rating INTEGER NOT NULL,
            title TEXT,
            body TEXT,
            photos TEXT,
            verified_purchase INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            author_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            UNIQUE(member_id, sku)
        );
        CREATE INDEX IF NOT EXISTS idx_reviews_sku_status
            ON product_reviews(sku, status);
        CREATE INDEX IF NOT EXISTS idx_reviews_status
            ON product_reviews(status);
        CREATE TABLE IF NOT EXISTS member_coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL REFERENCES members(id),
            code TEXT NOT NULL,                     -- UPPER, matches POS coupons.code
            source TEXT NOT NULL DEFAULT 'manual',  -- signup|review|manual|checkout
            source_ref TEXT NOT NULL DEFAULT '',    -- review: review_id; checkout: uuid4
            status TEXT NOT NULL DEFAULT 'granted', -- granted|used|revoked
            order_no TEXT,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_at TIMESTAMP,
            UNIQUE(member_id, code, source, source_ref)
        );
        CREATE INDEX IF NOT EXISTS idx_member_coupons_member
            ON member_coupons(member_id);
        CREATE INDEX IF NOT EXISTS idx_member_coupons_order
            ON member_coupons(order_no);
    """)
    # backfill identities from the legacy google_sub column
    # ("line:<uid>" rows were LINE logins, everything else Google)
    for mid, sub in conn.execute("SELECT id, google_sub FROM members").fetchall():
        if not sub:
            continue
        provider, subject = ("line", sub[5:]) if sub.startswith("line:") else ("google", sub)
        conn.execute(
            "INSERT OR IGNORE INTO member_identities (member_id, provider, subject) VALUES (?, ?, ?)",
            (mid, provider, subject))
    for stmt in (
        "ALTER TABLE members ADD COLUMN line_id TEXT",
        "ALTER TABLE members ADD COLUMN default_delivery TEXT",
        "ALTER TABLE members ADD COLUMN default_store_code TEXT",
        "ALTER TABLE members ADD COLUMN default_store_name TEXT",
        "ALTER TABLE members ADD COLUMN default_address TEXT",
        "ALTER TABLE members ADD COLUMN line_user_id TEXT",
        "ALTER TABLE members ADD COLUMN bind_code TEXT",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    # wishlist restock-notify marker. Adding the column and backfilling every
    # existing row happen in the SAME try block: the ALTER only succeeds when
    # the column is new, so the backfill runs exactly once, at creation. This
    # arms only *future* restocks (no mass blast on first cron run); the daily
    # job re-arms rows by clearing the marker when a product isn't in stock.
    try:
        conn.execute("ALTER TABLE wishlist ADD COLUMN restock_notified_at TIMESTAMP")
        conn.execute("UPDATE wishlist SET restock_notified_at = CURRENT_TIMESTAMP")
    except Exception:
        pass
    # migrate legacy single default_delivery into the address book (once)
    for m in conn.execute("""
        SELECT id, name, phone, default_delivery, default_store_code,
               default_store_name, default_address FROM members
        WHERE default_delivery IS NOT NULL
          AND id NOT IN (SELECT DISTINCT member_id FROM member_addresses)
    """).fetchall():
        conn.execute("""
            INSERT INTO member_addresses
                (member_id, label, recipient_name, recipient_phone, delivery,
                 store_code, store_name, address, is_default)
            VALUES (?, '預設', ?, ?, ?, ?, ?, ?, 1)
        """, (m["id"], m["name"], m["phone"], m["default_delivery"],
              m["default_store_code"], m["default_store_name"], m["default_address"]))
    conn.commit()
    conn.close()


def upsert_member(google_sub, email, name, picture):
    conn = _conn()
    conn.execute("""
        INSERT INTO members (google_sub, email, name, picture)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(google_sub) DO UPDATE SET
            email=excluded.email, picture=excluded.picture,
            name=COALESCE(members.name, excluded.name)
    """, (google_sub, email, name, picture))
    conn.commit()
    row = conn.execute(
        "SELECT * FROM members WHERE google_sub = ?", (google_sub,)).fetchone()
    conn.close()
    return dict(row)


def get_member(member_id):
    conn = _conn()
    row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_member_phone(member_id, phone):
    conn = _conn()
    conn.execute("UPDATE members SET phone = ? WHERE id = ?", (phone, member_id))
    conn.commit()
    conn.close()


# ----- wishlist -----

def wishlist_skus(member_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT sku FROM wishlist WHERE member_id = ? ORDER BY id DESC",
        (member_id,)).fetchall()
    conn.close()
    return [r["sku"] for r in rows]


def wishlist_toggle(member_id, sku):
    conn = _conn()
    cur = conn.execute(
        "DELETE FROM wishlist WHERE member_id = ? AND sku = ?", (member_id, sku))
    added = cur.rowcount == 0
    if added:
        conn.execute(
            "INSERT OR IGNORE INTO wishlist (member_id, sku) VALUES (?, ?)",
            (member_id, sku))
    conn.commit()
    conn.close()
    return added


# ----- arrival notifications -----

def notify_skus(member_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT sku FROM notify_requests WHERE member_id = ? AND notified_at IS NULL",
        (member_id,)).fetchall()
    conn.close()
    return [r["sku"] for r in rows]


def notify_toggle(member_id, sku):
    conn = _conn()
    cur = conn.execute(
        "DELETE FROM notify_requests WHERE member_id = ? AND sku = ? AND notified_at IS NULL",
        (member_id, sku))
    added = cur.rowcount == 0
    if added:
        conn.execute(
            "INSERT OR IGNORE INTO notify_requests (member_id, sku) VALUES (?, ?)",
            (member_id, sku))
    conn.commit()
    conn.close()
    return added


def pending_notifications():
    """[(request_id, member_id, email, name, sku, line_user_id)] awaiting
    arrival — 到貨通知 subscriptions not yet sent, for members reachable by
    email or LINE. member_id lets the cron dedupe against wishlist restocks."""
    conn = _conn()
    rows = conn.execute("""
        SELECT n.id, n.member_id, m.email, m.name, n.sku, m.line_user_id
        FROM notify_requests n JOIN members m ON m.id = n.member_id
        WHERE n.notified_at IS NULL
          AND (m.email IS NOT NULL OR m.line_user_id IS NOT NULL)
    """).fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def mark_notified(request_id):
    conn = _conn()
    conn.execute(
        "UPDATE notify_requests SET notified_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request_id,))
    conn.commit()
    conn.close()


# ----- wishlist restock notifications -----

def pending_wishlist_restocks():
    """[(row_id, member_id, email, name, sku, line_user_id)] for wishlist rows
    whose restock marker is cleared (armed), for members reachable by email or
    LINE. The daily cron sends when the product is in stock, then re-arms."""
    conn = _conn()
    rows = conn.execute("""
        SELECT w.id, w.member_id, m.email, m.name, w.sku, m.line_user_id
        FROM wishlist w JOIN members m ON m.id = w.member_id
        WHERE w.restock_notified_at IS NULL
          AND (m.email IS NOT NULL OR m.line_user_id IS NOT NULL)
    """).fetchall()
    conn.close()
    return [tuple(r) for r in rows]


def mark_wishlist_notified(row_id):
    conn = _conn()
    conn.execute(
        "UPDATE wishlist SET restock_notified_at = CURRENT_TIMESTAMP WHERE id = ?",
        (row_id,))
    conn.commit()
    conn.close()


def notified_wishlist_rows():
    """[(row_id, sku)] for wishlist rows whose marker is set — candidates the
    cron re-arms when their product is no longer in stock."""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, sku FROM wishlist WHERE restock_notified_at IS NOT NULL"
    ).fetchall()
    conn.close()
    return [(r["id"], r["sku"]) for r in rows]


def rearm_wishlist_rows(row_ids):
    """Clear the restock marker on the given rows so a future restock notifies
    again. No-op on an empty list."""
    row_ids = list(row_ids or [])
    if not row_ids:
        return
    conn = _conn()
    conn.executemany(
        "UPDATE wishlist SET restock_notified_at = NULL WHERE id = ?",
        [(rid,) for rid in row_ids])
    conn.commit()
    conn.close()


def update_profile(member_id, fields):
    """Update editable profile fields (whitelisted)."""
    allowed = ("name", "phone", "line_id", "default_delivery",
               "default_store_code", "default_store_name", "default_address")
    sets, params = [], []
    for key in allowed:
        if key in fields:
            sets.append(f"{key} = ?")
            params.append((fields[key] or "").strip() or None)
    if not sets:
        return
    params.append(member_id)
    conn = _conn()
    conn.execute(f"UPDATE members SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()


# ----- LINE binding (via 官方帳號 webhook + binding code) -----

def get_bind_code(member_id):
    """Return (or mint) the member's LINE binding code."""
    import secrets
    conn = _conn()
    row = conn.execute("SELECT bind_code FROM members WHERE id = ?", (member_id,)).fetchone()
    code = row["bind_code"] if row else None
    if not code:
        code = "AB" + secrets.token_hex(3).upper()
        conn.execute("UPDATE members SET bind_code = ? WHERE id = ?", (code, member_id))
        conn.commit()
    conn.close()
    return code


def bind_line_user(code, line_user_id):
    """Link a LINE user to the member holding this code. Returns member or None."""
    conn = _conn()
    row = conn.execute(
        "SELECT id FROM members WHERE bind_code = ?", (code.strip().upper(),)).fetchone()
    if not row:
        conn.close()
        return None
    conn.execute("UPDATE members SET line_user_id = ? WHERE id = ?",
                 (line_user_id, row["id"]))
    conn.commit()
    member = conn.execute("SELECT * FROM members WHERE id = ?", (row["id"],)).fetchone()
    conn.close()
    return dict(member)


def unbind_line(member_id):
    conn = _conn()
    conn.execute("UPDATE members SET line_user_id = NULL WHERE id = ?", (member_id,))
    conn.commit()
    conn.close()


def set_line_user(member_id, line_user_id):
    conn = _conn()
    conn.execute("UPDATE members SET line_user_id = ? WHERE id = ?",
                 (line_user_id, member_id))
    conn.commit()
    conn.close()


# ----- multi-provider identities + account merge -----

def _apply_profile(conn, member_id, email, name, picture):
    conn.execute("""
        UPDATE members SET
            email = COALESCE(email, ?),
            name = COALESCE(name, ?),
            picture = COALESCE(picture, ?)
        WHERE id = ?
    """, (email, name, picture, member_id))


def record_quiz_result(result_key, character, legion, scores, member_id=None):
    """Persist a completed 原體 quiz result for later analysis (site-owned DB)."""
    conn = _conn()
    conn.execute(
        "INSERT INTO quiz_results(result_key, character, legion, scores, member_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (result_key, character, legion,
         json.dumps(scores, ensure_ascii=False) if scores is not None else None,
         member_id))
    conn.commit()
    conn.close()


def find_or_create_by_identity(provider, subject, email, name, picture):
    """Login path: return the member owning this identity, creating one if new."""
    conn = _conn()
    row = conn.execute("""
        SELECT member_id FROM member_identities WHERE provider = ? AND subject = ?
    """, (provider, subject)).fetchone()
    if row:
        member_id = row["member_id"]
        _apply_profile(conn, member_id, email, name, picture)
    else:
        legacy_key = ("line:" + subject) if provider == "line" else subject
        cur = conn.execute("""
            INSERT INTO members (google_sub, email, name, picture)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(google_sub) DO UPDATE SET
                email = COALESCE(members.email, excluded.email),
                name = COALESCE(members.name, excluded.name),
                picture = COALESCE(members.picture, excluded.picture)
        """, (legacy_key, email, name, picture))
        member_id = conn.execute(
            "SELECT id FROM members WHERE google_sub = ?", (legacy_key,)).fetchone()["id"]
        conn.execute(
            "INSERT OR IGNORE INTO member_identities (member_id, provider, subject) VALUES (?, ?, ?)",
            (member_id, provider, subject))
    conn.commit()
    member = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    conn.close()
    m = dict(member)
    m["_is_new"] = row is None   # first time this identity is seen -> sign_up
    return m


def identities_for(member_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT provider, subject FROM member_identities WHERE member_id = ?",
        (member_id,)).fetchall()
    conn.close()
    return {r["provider"]: r["subject"] for r in rows}


def merge_members(keep_id, drop_id):
    """Fold drop_id's data into keep_id and delete the duplicate."""
    if keep_id == drop_id:
        return
    conn = _conn()
    conn.execute("UPDATE member_identities SET member_id = ? WHERE member_id = ?",
                 (keep_id, drop_id))
    # move wishlist / notify subscriptions / coupon wallet, ignoring duplicates
    for table in ("wishlist", "notify_requests", "member_coupons"):
        conn.execute(f"""
            UPDATE OR IGNORE {table} SET member_id = ? WHERE member_id = ?
        """, (keep_id, drop_id))
        conn.execute(f"DELETE FROM {table} WHERE member_id = ?", (drop_id,))
    # coalesce profile fields (keep's values win)
    drop = conn.execute("SELECT * FROM members WHERE id = ?", (drop_id,)).fetchone()
    if drop:
        conn.execute("""
            UPDATE members SET
                email = COALESCE(email, ?), phone = COALESCE(phone, ?),
                name = COALESCE(name, ?), picture = COALESCE(picture, ?),
                line_id = COALESCE(line_id, ?), line_user_id = COALESCE(line_user_id, ?),
                default_delivery = COALESCE(default_delivery, ?),
                default_store_code = COALESCE(default_store_code, ?),
                default_store_name = COALESCE(default_store_name, ?),
                default_address = COALESCE(default_address, ?)
            WHERE id = ?
        """, (drop["email"], drop["phone"], drop["name"], drop["picture"],
              drop["line_id"], drop["line_user_id"], drop["default_delivery"],
              drop["default_store_code"], drop["default_store_name"],
              drop["default_address"], keep_id))
    conn.execute("DELETE FROM members WHERE id = ?", (drop_id,))
    conn.commit()
    conn.close()


def link_identity(member_id, provider, subject, email, name, picture):
    """Attach a provider identity to an existing member. If that identity
    already belongs to another member, merge that account into this one.
    Returns 'linked' or 'merged'."""
    conn = _conn()
    row = conn.execute(
        "SELECT member_id FROM member_identities WHERE provider = ? AND subject = ?",
        (provider, subject)).fetchone()
    conn.close()
    if row and row["member_id"] != member_id:
        merge_members(member_id, row["member_id"])
        return "merged"
    conn = _conn()
    conn.execute(
        "INSERT OR IGNORE INTO member_identities (member_id, provider, subject) VALUES (?, ?, ?)",
        (member_id, provider, subject))
    _apply_profile(conn, member_id, email, name, picture)
    conn.commit()
    conn.close()
    return "linked"


# ----- address book (收件資料) -----

def list_addresses(member_id):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM member_addresses WHERE member_id = ? "
        "ORDER BY is_default DESC, id DESC", (member_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_address(member_id, fields, addr_id=None):
    vals = {k: (fields.get(k) or "").strip() or None for k in
            ("label", "recipient_name", "recipient_phone", "delivery",
             "store_code", "store_name", "address")}
    if vals["delivery"] not in ("711", "fami", "post", "meet"):
        return None
    conn = _conn()
    if addr_id:
        owned = conn.execute(
            "SELECT id FROM member_addresses WHERE id = ? AND member_id = ?",
            (addr_id, member_id)).fetchone()
        if not owned:
            conn.close()
            return None
        conn.execute("""
            UPDATE member_addresses SET label=?, recipient_name=?, recipient_phone=?,
                delivery=?, store_code=?, store_name=?, address=?
            WHERE id = ?
        """, (*[vals[k] for k in ("label", "recipient_name", "recipient_phone",
                                  "delivery", "store_code", "store_name", "address")],
              addr_id))
    else:
        first = conn.execute(
            "SELECT COUNT(*) FROM member_addresses WHERE member_id = ?",
            (member_id,)).fetchone()[0] == 0
        cur = conn.execute("""
            INSERT INTO member_addresses
                (member_id, label, recipient_name, recipient_phone, delivery,
                 store_code, store_name, address, is_default)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (member_id, *[vals[k] for k in ("label", "recipient_name",
              "recipient_phone", "delivery", "store_code", "store_name", "address")],
              1 if first else 0))
        addr_id = cur.lastrowid
    conn.commit()
    conn.close()
    return addr_id


def delete_address(member_id, addr_id):
    conn = _conn()
    conn.execute("DELETE FROM member_addresses WHERE id = ? AND member_id = ?",
                 (addr_id, member_id))
    conn.commit()
    conn.close()


def set_default_address(member_id, addr_id):
    conn = _conn()
    conn.execute("UPDATE member_addresses SET is_default = 0 WHERE member_id = ?",
                 (member_id,))
    conn.execute("UPDATE member_addresses SET is_default = 1 "
                 "WHERE id = ? AND member_id = ?", (addr_id, member_id))
    conn.commit()
    conn.close()


def find_matching_address(member_id, fields):
    """True if an equivalent entry already exists (avoid auto-save dupes)."""
    conn = _conn()
    row = conn.execute("""
        SELECT id FROM member_addresses
        WHERE member_id = ? AND delivery = ?
          AND COALESCE(store_code, '') = COALESCE(?, '')
          AND COALESCE(address, '') = COALESCE(?, '')
          AND COALESCE(recipient_name, '') = COALESCE(?, '')
    """, (member_id, fields.get("delivery"),
          fields.get("store_code") or "", fields.get("address") or "",
          fields.get("recipient_name") or "")).fetchone()
    conn.close()
    return bool(row)


# ----- product reviews (商品評價) -----

def _review_row(r):
    """Normalize a product_reviews row: decode photos JSON to a list."""
    d = dict(r)
    try:
        d["photos"] = json.loads(d.get("photos") or "[]")
    except Exception:
        d["photos"] = []
    return d


def get_review(member_id, sku):
    """A member's own review for a product (any status), or None."""
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM product_reviews WHERE member_id = ? AND sku = ?",
        (member_id, sku)).fetchone()
    conn.close()
    return _review_row(row) if row else None


def get_review_by_id(review_id):
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM product_reviews WHERE id = ?", (review_id,)).fetchone()
    conn.close()
    return _review_row(row) if row else None


def save_review(member_id, sku, fields, status="pending"):
    """Insert or update a member's review for a product. Any submit resets the
    review to `status` (default 'pending') so edits get re-moderated; a
    verified-purchase review may be saved 'approved' to publish instantly.
    Returns the saved review id.

    `fields` keys: category, slug, product_name, rating (1-5), title, body,
    photos (list of stored filenames), verified_purchase (bool), author_name.
    """
    if status not in ("pending", "approved"):
        status = "pending"
    try:
        rating = int(fields.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        return None
    photos = json.dumps(fields.get("photos") or [])
    vals = (
        fields.get("category"), fields.get("slug"), fields.get("product_name"),
        rating, (fields.get("title") or None), (fields.get("body") or None),
        photos, 1 if fields.get("verified_purchase") else 0,
        status, fields.get("author_name"),
    )
    conn = _conn()
    conn.execute("""
        INSERT INTO product_reviews
            (member_id, sku, category, slug, product_name, rating, title, body,
             photos, verified_purchase, status, author_name,
             created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(member_id, sku) DO UPDATE SET
            category=excluded.category, slug=excluded.slug,
            product_name=excluded.product_name, rating=excluded.rating,
            title=excluded.title, body=excluded.body, photos=excluded.photos,
            verified_purchase=excluded.verified_purchase,
            author_name=excluded.author_name,
            status=excluded.status, updated_at=CURRENT_TIMESTAMP, reviewed_at=NULL
    """, (member_id, sku, *vals))
    conn.commit()
    row = conn.execute(
        "SELECT id FROM product_reviews WHERE member_id = ? AND sku = ?",
        (member_id, sku)).fetchone()
    conn.close()
    return row["id"] if row else None


def approved_reviews(sku):
    """Approved reviews for a product, newest first (verified purchases first)."""
    conn = _conn()
    rows = conn.execute("""
        SELECT * FROM product_reviews
        WHERE sku = ? AND status = 'approved'
        ORDER BY verified_purchase DESC, id DESC
    """, (sku,)).fetchall()
    conn.close()
    return [_review_row(r) for r in rows]


def review_stats(sku):
    """Aggregate rating for a product: {count, average} over approved reviews."""
    conn = _conn()
    row = conn.execute("""
        SELECT COUNT(*) AS count, AVG(rating) AS average
        FROM product_reviews WHERE sku = ? AND status = 'approved'
    """, (sku,)).fetchone()
    conn.close()
    count = row["count"] or 0
    avg = round(row["average"], 1) if row["average"] is not None else None
    return {"count": count, "average": avg}


def review_stats_bulk(skus):
    """{sku: {count, average}} for many products (approved only)."""
    skus = [s for s in (skus or []) if s]
    if not skus:
        return {}
    conn = _conn()
    ph = ",".join("?" * len(skus))
    rows = conn.execute(f"""
        SELECT sku, COUNT(*) AS count, AVG(rating) AS average
        FROM product_reviews WHERE status = 'approved' AND sku IN ({ph})
        GROUP BY sku
    """, skus).fetchall()
    conn.close()
    return {r["sku"]: {"count": r["count"],
                       "average": round(r["average"], 1) if r["average"] is not None else None}
            for r in rows}


def pending_reviews(limit=100):
    """Reviews awaiting moderation, oldest first (FIFO queue)."""
    conn = _conn()
    rows = conn.execute("""
        SELECT pr.*, m.email AS member_email, m.name AS member_name
        FROM product_reviews pr JOIN members m ON m.id = pr.member_id
        WHERE pr.status = 'pending'
        ORDER BY pr.id ASC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [_review_row(r) for r in rows]


def reviews_by_status(status=None, limit=200):
    """Reviews for moderation history, newest first. status=None returns all
    statuses; otherwise filter to 'pending'|'approved'|'rejected'."""
    conn = _conn()
    if status:
        rows = conn.execute("""
            SELECT pr.*, m.email AS member_email, m.name AS member_name
            FROM product_reviews pr JOIN members m ON m.id = pr.member_id
            WHERE pr.status = ? ORDER BY pr.id DESC LIMIT ?
        """, (status, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT pr.*, m.email AS member_email, m.name AS member_name
            FROM product_reviews pr JOIN members m ON m.id = pr.member_id
            ORDER BY pr.id DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [_review_row(r) for r in rows]


def set_review_status(review_id, status):
    """Moderator action: 'approved' or 'rejected'. Returns the updated review."""
    if status not in ("approved", "rejected", "pending"):
        return None
    conn = _conn()
    cur = conn.execute("""
        UPDATE product_reviews SET status = ?, reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, review_id))
    conn.commit()
    changed = cur.rowcount
    row = conn.execute(
        "SELECT * FROM product_reviews WHERE id = ?", (review_id,)).fetchone()
    conn.close()
    if not changed or not row:
        return None
    return _review_row(row)


# ----- coupon wallet (definitions live in the POS; redemptions owned here) -----
# State machine: granted -> used(order_no) at checkout; used -> granted on
# cancel-release; granted -> revoked on review rejection. Exactly-once for
# signup/review grants is the UNIQUE(member_id, code, source, source_ref)
# constraint (source_ref = '' for signup/manual, review_id for reviews).
# Checkout-entered codes INSERT directly as 'used' with a uuid4 source_ref;
# the per-member limit is enforced by COUNT inside claim_coupon, not UNIQUE.

def grant_coupon(member_id, code, source, source_ref=''):
    """Add a granted wallet coupon. Returns the new row id, or None when it
    already exists (idempotent via the UNIQUE constraint)."""
    code = (code or '').strip().upper()
    if not code:
        return None
    conn = _conn()
    cur = conn.execute("""
        INSERT OR IGNORE INTO member_coupons
            (member_id, code, source, source_ref, status)
        VALUES (?, ?, ?, ?, 'granted')
    """, (member_id, code, source, source_ref or ''))
    conn.commit()
    rid = cur.lastrowid if cur.rowcount else None
    conn.close()
    return rid


def list_coupons(member_id):
    """All of a member's wallet rows (any status), newest first."""
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM member_coupons WHERE member_id = ? ORDER BY id DESC",
        (member_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_used_coupons(member_id, code):
    """How many times this member has already spent `code` (per-member limit)."""
    conn = _conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM member_coupons "
        "WHERE member_id = ? AND code = ? AND status = 'used'",
        (member_id, (code or '').strip().upper())).fetchone()[0]
    conn.close()
    return n


def count_granted_coupons(member_id, code):
    """How many unspent wallet grants of `code` this member holds."""
    conn = _conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM member_coupons "
        "WHERE member_id = ? AND code = ? AND status = 'granted'",
        (member_id, (code or '').strip().upper())).fetchone()[0]
    conn.close()
    return n


def claim_coupon(member_id, code, per_member_limit, allow_new_claim=True):
    """Atomically claim one use of `code` at checkout. An earned wallet grant
    is always spendable — one use per granted row; the grant side already
    limits how many a member earns. With no granted row left, a fresh
    checkout-sourced claim is allowed only for typed campaign codes
    (`allow_new_claim`), gated by the per-member limit. Returns the claimed
    row id, or None."""
    import uuid
    code = (code or '').strip().upper()
    if not code:
        return None
    limit = per_member_limit if (per_member_limit or 0) > 0 else 1
    conn = _conn()
    conn.isolation_level = None   # manual BEGIN IMMEDIATE / COMMIT
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM member_coupons "
            "WHERE member_id = ? AND code = ? AND status = 'granted' "
            "ORDER BY id LIMIT 1", (member_id, code)).fetchone()
        if row:
            claim_id = row["id"]
            conn.execute(
                "UPDATE member_coupons SET status = 'used', "
                "used_at = CURRENT_TIMESTAMP WHERE id = ?", (claim_id,))
        else:
            if not allow_new_claim:
                conn.execute("ROLLBACK")
                return None
            used = conn.execute(
                "SELECT COUNT(*) FROM member_coupons "
                "WHERE member_id = ? AND code = ? AND status = 'used'",
                (member_id, code)).fetchone()[0]
            if used >= limit:
                conn.execute("ROLLBACK")
                return None
            cur = conn.execute(
                "INSERT INTO member_coupons "
                "(member_id, code, source, source_ref, status, used_at) "
                "VALUES (?, ?, 'checkout', ?, 'used', CURRENT_TIMESTAMP)",
                (member_id, code, uuid.uuid4().hex))
            claim_id = cur.lastrowid
        conn.execute("COMMIT")
        return claim_id
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def finalize_claim(claim_id, order_no):
    """Attach the order number to a just-claimed row (after the POS accepts)."""
    conn = _conn()
    conn.execute("UPDATE member_coupons SET order_no = ? WHERE id = ?",
                 (order_no, claim_id))
    conn.commit()
    conn.close()


def unclaim(claim_id):
    """Reverse a claim (POS rejected the order): delete a checkout-entered row,
    or revert a wallet grant back to 'granted' so it stays usable."""
    conn = _conn()
    row = conn.execute("SELECT source FROM member_coupons WHERE id = ?",
                       (claim_id,)).fetchone()
    if row:
        if row["source"] == 'checkout':
            conn.execute("DELETE FROM member_coupons WHERE id = ?", (claim_id,))
        else:
            conn.execute("UPDATE member_coupons SET status = 'granted', "
                         "used_at = NULL, order_no = NULL WHERE id = ?", (claim_id,))
    conn.commit()
    conn.close()


def release_coupon_by_order(order_no):
    """Order cancelled: return its spent coupon rows to the wallet. Idempotent
    (only touches rows still 'used'). Checkout-entered rows are deleted; wallet
    grants revert to 'granted'. Returns the number of rows released."""
    if not order_no:
        return 0
    conn = _conn()
    rows = conn.execute(
        "SELECT id, source FROM member_coupons "
        "WHERE order_no = ? AND status = 'used'", (order_no,)).fetchall()
    n = 0
    for r in rows:
        if r["source"] == 'checkout':
            conn.execute("DELETE FROM member_coupons WHERE id = ?", (r["id"],))
        else:
            conn.execute("UPDATE member_coupons SET status = 'granted', "
                         "used_at = NULL, order_no = NULL WHERE id = ?", (r["id"],))
        n += 1
    conn.commit()
    conn.close()
    return n


def revoke_review_coupon(review_id):
    """Review rejected: revoke its unused reward grant (spent ones stand)."""
    conn = _conn()
    conn.execute(
        "UPDATE member_coupons SET status = 'revoked' "
        "WHERE source = 'review' AND source_ref = ? AND status = 'granted'",
        (str(review_id),))
    conn.commit()
    conn.close()
