"""Every parameterless public GET route must respond without a server error,
plus the seeded detail pages."""
import pytest

from app import app as flask_app


def _static_get_rules():
    rules = []
    for rule in flask_app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.arguments:
            continue
        if rule.rule.startswith("/static") or rule.rule.startswith("/admin"):
            continue
        rules.append(rule.rule)
    return sorted(set(rules))


@pytest.mark.parametrize("path", _static_get_rules())
def test_public_get(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code < 500, f"GET {path} -> {r.status_code}"


DETAIL_PATHS = [
    "/products?category=warhammer-40k",
    "/products/warhammer-40k/stock-item",
    "/products/warhammer-40k/sale-item",
    "/products/warhammer-40k/preorder-item",
    "/products/warhammer-40k/stale-preorder-item",
    "/blog/hello",
    "/codex/ultramarines",
]


@pytest.mark.parametrize("path", DETAIL_PATHS)
def test_detail_pages(client, path):
    r = client.get(path, follow_redirects=True)
    assert r.status_code == 200, f"GET {path} -> {r.status_code}"


def test_single_h1_on_key_pages(client):
    for path in ("/", "/quiz", "/products/warhammer-40k/stock-item"):
        html = client.get(path, follow_redirects=True).get_data(as_text=True)
        assert html.count("<h1") == 1, f"{path}: {html.count('<h1')} h1 tags"


def test_product_title_lengths(client):
    import re
    for path in DETAIL_PATHS[:4]:
        html = client.get(path, follow_redirects=True).get_data(as_text=True)
        m = re.search(r"<title>([^<]*)</title>", html)
        assert m and len(m.group(1)) <= 65, f"{path}: title {len(m.group(1))} chars"
