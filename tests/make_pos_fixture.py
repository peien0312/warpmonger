"""Build a schema-complete POS fixture DB for the site's test suite.

MUST run under the POS venv (../warpmonger-pos/venv) — it imports the POS
app so the schema always matches the real source of truth:
    ../warpmonger-pos/venv/bin/python tests/make_pos_fixture.py /path/out.db
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

out = sys.argv[1]
POS = Path(__file__).resolve().parents[2] / "warpmonger-pos"
sys.path.insert(0, str(POS))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{out}"

from app.database import init_db, async_session  # noqa: E402
from app import models  # noqa: E402


async def main():
    await init_db()
    async with async_session() as db:
        db.add(models.Settings(key="exchange_rate", value="4.45"))
        db.add(models.Settings(key="featured_products",
                               value='["warhammer-40k/stock-item"]'))
        db.add(models.Settings(key="featured_tags", value='[]'))
        db.add(models.Settings(key="tag_glossary",
                               value='{"ultramarines": "極限戰士"}'))
        db.add(models.Settings(key="faction_tags", value='["ultramarines"]'))
        db.add(models.StorefrontCategory(slug="warhammer-40k", name="戰鎚 40K",
                                         order_weight=10, is_visible=True))
        prods = {}
        for sku, name, price, kw in [
            ("JT0001", "現貨測試品", 1500, dict(slug="stock-item")),
            ("JT0002", "會員價測試品", 800, dict(slug="member-item", regular_price_twd=700)),
            ("JT0003", "特價測試品", 1000, dict(slug="sale-item", is_on_sale=True, sale_price_twd=850)),
            ("JT0004", "絕版測試品", 2000, dict(slug="inquiry-item", is_deprecated=True)),
            ("JT0005", "預購測試品", 3000, dict(slug="preorder-item", is_preorder=True,
                                            preorder_date=datetime.now() + timedelta(days=30))),
        ]:
            p = models.Product(sku=sku, zhtw_name=name, en_name=name,
                               cost_cny=100, selling_price_twd=price,
                               category_slug="warhammer-40k", is_published=True,
                               tags='["ultramarines"]',
                               description_zhtw="測試說明", **kw)
            db.add(p)
            prods[sku] = p
        await db.flush()
        db.add(models.Inventory(product_id=prods["JT0001"].id,
                                location="taiwan", quantity=5))
        db.add(models.Inventory(product_id=prods["JT0003"].id,
                                location="china", quantity=2))
        db.add(models.StorefrontPost(type="blog", slug="hello", title="Hello",
                                     title_zhtw="首篇", body="內文",
                                     is_published=True,
                                     published_at=datetime.now()))
        db.add(models.StorefrontPost(type="codex", slug="ultramarines",
                                     title="Ultramarines", title_zhtw="極限戰士",
                                     body="lore", is_published=True))
        db.add(models.Coupon(code="TESTC", kind="fixed", amount_twd=50,
                             active=True))
        await db.commit()

asyncio.run(main())
print("fixture written:", out)
