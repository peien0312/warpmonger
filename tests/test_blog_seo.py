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


def test_image_sitemap_renders(client):
    r = client.get("/sitemap-images.xml")
    assert r.status_code == 200
    assert b"<urlset" in r.data
