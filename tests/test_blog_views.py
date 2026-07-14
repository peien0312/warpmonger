"""Blog view tracking: rows land in members.db with a classified source,
bots and same-session refreshes are not counted (POS reads these for
/storefront/blog-stats)."""
import memberdb


def _views(slug="hello"):
    conn = memberdb._conn()
    rows = conn.execute(
        "SELECT * FROM blog_views WHERE post_slug = ? ORDER BY id",
        (slug,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


UA = {"User-Agent": "Mozilla/5.0 (test)"}


def test_view_recorded_with_referrer_classified(client):
    before = len(_views())
    r = client.get("/blog/hello", headers={
        **UA, "Referer": "https://www.google.com.tw/search?q=abbeystoys"})
    assert r.status_code == 200
    rows = _views()
    assert len(rows) == before + 1
    assert rows[-1]["ref_source"] == "google"


def test_same_session_refresh_not_double_counted(client):
    client.get("/blog/hello", headers=UA)
    n = len(_views())
    client.get("/blog/hello", headers=UA)  # same session cookie jar
    assert len(_views()) == n


def test_internal_referrer_keeps_path(client):
    client.get("/blog/hello", headers={
        **UA, "Referer": "https://abbeystoys.com/blog"})
    row = _views()[-1]
    assert row["ref_source"] == "site"
    assert row["ref_detail"] == "/blog"


def test_utm_source_wins_over_referrer(client):
    client.get("/blog/hello?utm_source=newsletter", headers={
        **UA, "Referer": "https://www.google.com/"})
    assert _views()[-1]["ref_source"] == "utm:newsletter"


def test_no_referrer_is_direct(client):
    client.get("/blog/hello", headers=UA)
    assert _views()[-1]["ref_source"] == "direct"


def test_bots_not_counted(client):
    before = len(_views())
    client.get("/blog/hello", headers={
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"})
    client.get("/blog/hello", headers={
        "User-Agent": "facebookexternalhit/1.1"})
    client.get("/blog/hello", headers={"User-Agent": ""})  # blank UA
    assert len(_views()) == before
