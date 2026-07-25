"""Site search matching (posdb._search_match via get_products).

Product names carry stray spaces/newlines from the Excel import, and
customers type full-width chars via Chinese IMEs — search must tolerate
both (the 千子 MK III regression: query without the stored space found
nothing).
"""
import posdb


def _skus(q):
    return {p["_pos_sku"] for p in posdb.get_products(search=q)}


def test_missing_space_still_matches():
    # stored: "千子 MK III型戰術軍團士兵" — query has no space after 千子
    assert "JT0007" in _skus("千子MK III型戰術軍團士兵")


def test_query_spanning_stored_newlines():
    # stored: "千子\nMKIV軍團戰術小隊\n軍團士兵 1"
    assert "JT0008" in _skus("千子 MKIV")
    assert "JT0008" in _skus("千子MKIV軍團戰術小隊")


def test_fullwidth_and_roman_numeral_folding():
    assert "JT0007" in _skus("千子ＭＫ")     # full-width ＭＫ
    assert "JT0007" in _skus("千子MKⅢ")     # Ⅲ (U+2162) → III


def test_tokens_are_anded():
    assert "JT0007" in _skus("千子 士兵")
    assert "JT0007" not in _skus("千子 無此詞")


def test_sku_search_still_works():
    assert "JT0007" in _skus("jt0007")
