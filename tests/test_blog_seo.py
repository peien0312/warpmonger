"""Blog SEO: filtered listing variants must canonicalize onto /blog so the
posts themselves rank in search, not the parameterized listings."""
import re


def _canonical(html):
    m = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return m and m.group(1)


def test_blog_tag_and_search_variants_canonicalize(client):
    for url in ("/blog?tag=%E5%B8%9D%E5%9C%8B", "/blog?q=corn", "/blog"):
        html = client.get(url).get_data(as_text=True)
        assert _canonical(html) == "http://localhost/blog", url


def test_blog_post_stays_self_canonical(client):
    html = client.get("/blog/hello").get_data(as_text=True)
    assert _canonical(html) == "http://localhost/blog/hello"


def test_structured_data_is_valid_json(client):
    """Every JSON-LD block must parse — the fixture post body contains CRLF,
    quotes, a backslash and a tab (GSC rejected a post over a raw \\r)."""
    import json
    for url in ("/blog/hello", "/products/warhammer-40k/stock-item", "/"):
        r = client.get(url)
        assert r.status_code == 200, url
        blocks = re.findall(
            r'<script type="application/ld\+json">(.*?)</script>',
            r.get_data(as_text=True), re.S)
        assert blocks, url
        for b in blocks:
            json.loads(b)


def test_image_sitemap_renders(client):
    r = client.get("/sitemap-images.xml")
    assert r.status_code == 200
    assert b"<urlset" in r.data


def test_products_tag_canonical_matches_link_encoding(client):
    """Canonical must use the same %20 encoding as the Jinja |urlencode links
    and the sitemap — the old urlencode() +/%2F style split every tag page
    into two URL variants in GSC."""
    html = client.get("/products?tag=Dark+Angels&sort=price_low").get_data(as_text=True)
    assert _canonical(html) == "http://localhost/products?tag=Dark%20Angels"
    html = client.get("/products?tag=1/25+Scale").get_data(as_text=True)
    assert _canonical(html) == "http://localhost/products?tag=1/25%20Scale"


def test_login_is_noindex_and_next_variants_collapse(client):
    html = client.get("/login?next=/products/warhammer-40k/stock-item").get_data(as_text=True)
    assert '<meta name="robots" content="noindex">' in html
    assert _canonical(html) == "http://localhost/login"


def test_sitemap_lists_no_redirecting_urls(client):
    xml = client.get("/sitemap.xml").get_data(as_text=True)
    assert "/page/" not in xml  # legacy /page/<slug> URLs 301 to the real routes
    for path in ("/guide", "/returns", "/terms"):
        assert f"http://localhost{path}</loc>" in xml


def test_robots_disallows_auth(client):
    txt = client.get("/robots.txt").get_data(as_text=True)
    assert "Disallow: /auth/" in txt.split("User-agent:")[1]  # under User-agent: *
