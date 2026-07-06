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
