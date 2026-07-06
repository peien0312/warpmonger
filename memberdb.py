"""Member data owned by the site (NOT the POS database).

The POS SQLite keeps its single-writer rule — members, wishlists and
arrival-notification subscriptions live in the site's own data/members.db,
where this Flask app is the only writer. Linking to POS customers happens
by phone at checkout time.
"""
import os
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
    """[(request_id, member_email, member_name, sku)] awaiting arrival."""
    conn = _conn()
    rows = conn.execute("""
        SELECT n.id, m.email, m.name, n.sku, m.line_user_id
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
    return dict(member)


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
    # move wishlist / notify subscriptions, ignoring duplicates
    for table in ("wishlist", "notify_requests"):
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
    if vals["delivery"] not in ("711", "fami", "post"):
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
