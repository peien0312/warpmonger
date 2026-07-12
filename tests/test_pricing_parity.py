"""The site mirrors POS money/availability rules — pin the mirror."""
import posdb


def _product(slug):
    return posdb.get_product("warhammer-40k", slug)


def test_member_price_uses_regular_when_set():
    p = _product("member-item")
    assert p["member_price"] == 700


def test_member_price_falls_back_to_90pct():
    p = _product("stock-item")
    assert p["member_price"] == 1350          # round(1500 * 0.9)


def test_sale_price_caps_member_price():
    p = _product("sale-item")
    assert p["member_price"] <= 850


def test_availability_states():
    cases = {"stock-item": "in_stock", "sale-item": "incoming",
             "preorder-item": "preorder", "inquiry-item": "inquiry",
             "member-item": "orderable"}
    for slug, want in cases.items():
        p = _product(slug)
        got = p["availability"]
        assert got == want, f"{slug}: {got} != {want}"
