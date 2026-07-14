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
