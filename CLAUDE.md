# Claude Instructions for Abbey's Toys (toy-seller-site)

## What this is

The B2C storefront **ABBEY'S TOYS 阿北玩具堂** at **https://abbeystoys.com**
(zh-TW only; legal entity 阿北的店, 統編 60079547). Flask + Jinja2, served by
gunicorn behind Caddy on the same GCP VM as the POS.

**This site has no database and no admin of its own.** It reads the
warpmonger-pos SQLite DB directly and renders it. All content management
happens in the POS.

## The sibling repo (the admin / source of truth)

- Local: `../warpmonger-pos` — FastAPI POS, admin UI, the DB, the media files.
- Products, prices, stock, images, categories, blog/codex/promotions/pages,
  featured picks: ALL edited in the POS (its 網站商店 section + product forms).
- This repo only owns: templates, CSS, routes, the cart/email flow, `posdb.py`.

## The cross-repo contract (change with care, in both repos together)

`posdb.py` is a read-only layer over the POS SQLite (WAL; safe concurrent
reads). It depends on this POS schema:

- `products` storefront columns: `slug`, `category_slug`, `tags` (JSON),
  `order_weight`, `is_on_sale`, `sale_price_twd`, `is_new_arrival`,
  `storefront_group`, `is_published` — plus the base columns
  (names/prices/preorder) and `description_zhtw` as the site description.
- `product_images` (kind cover|gallery|detail, sort_order, filename
  `media/<SKU>/<file>`) — images live on disk in the POS repo's `media/` dir,
  served by this app at `/static/images/products/<cat>/<slug>/<file>` with
  on-demand thumbnails (`thumb_*`).
- `inventory` (location='taiwan', quantity-reserved) → live in_stock.
- `storefront_categories`, `storefront_posts` (type blog|codex|promotion|page,
  extra JSON), `settings` keys `featured_products` (["category/slug", ...])
  and `featured_tags`.

If a POS migration touches any of these, update `posdb.py` in the same
change and deploy both.

Caching: everything is cached in-process and invalidated when the DB file
mtime changes — POS edits appear on the site immediately. Don't add caches
that outlive `posdb.db_mtime()`.

Legacy: the flat-file loaders in `app.py` and the `content/` tree are dead
code kept for rollback (name-rebound to `posdb.*` at the bottom of app.py).
`import_from_pos.py` is obsolete.

## Development

- venv: `source venv/bin/activate`, run with `python3 app.py` (port 5006).
- Needs the POS DB: `posdb.py` auto-finds `../warpmonger-pos/data/warpmonger.db`
  locally, `~/warpmonger_dashboard/data/warpmonger.db` on the VM
  (override with env `POS_DB` / `POS_MEDIA`).
- To refresh local data: snapshot prod (`gcloud compute scp` a checkpointed
  copy) into the POS repo's `data/`.

## Deployment

- VM: `warpmonger-pos` (GCP project `warpmonger-prod`, zone `asia-east1-b`) —
  always pass `--project warpmonger-prod`.
- Service: `abbeystoys.service` (gunicorn 127.0.0.1:5006), dir
  `/home/warpmonger/abbeystoys`, user `warpmonger`, behind Caddy vhost
  `abbeystoys.com, www.abbeystoys.com`.
- Deploy: `./deploy.sh` (tars code — no venv/content/images — scps it to the
  VM, extracts, restarts the service, health-checks). DNS: Cloudflare zone
  for abbeystoys.com, A records → 35.194.159.105, DNS-only (Caddy does TLS).

## Design identity

Stained-glass workshop: walnut `#1E1712`, surface `#292019`, card `#342A21`,
lead `#17100B`, oak bronze `#6E4B2A`, candle amber `#D9A441`, parchment
`#E6DAC4`, glass blue `#8FA3B8`. Display type Cinzel + Noto Serif TC; body
Noto Sans TC. Signature: lead-came frames on cards, glass-panel hero.
The identity layer lives at the bottom of `static/css/public.css` —
prefer extending it over scattering new colors.
