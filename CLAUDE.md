# Claude Instructions for Abbey's Toys (toy-seller-site)

## What this is

The B2C storefront **ABBEY'S TOYS 阿北玩具堂** at **https://abbeystoys.com**
(zh-TW primary; legal entity 阿北的店, 統編 60079547). Flask + Jinja2, served
by gunicorn behind Caddy on the same GCP VM as the POS.

**Product/content data lives in the POS, not here.** The site reads the
warpmonger-pos SQLite DB directly (read-only) and renders it; all product
and editorial management happens in the POS. The only data the site owns
is `data/members.db` (members / wishlist / 到貨通知 / 收件資料 address
book) — this Flask app is its single writer. `/admin` redirects to the POS.

## The sibling repo (the admin / source of truth)

- Local: `../warpmonger-pos` — FastAPI POS, admin UI, the DB, the media files.
- Products, prices, stock, images, categories, blog/codex/promotions/pages,
  featured picks: ALL edited in the POS (its 網站商店 section + product forms).
- This repo only owns: templates, CSS, routes, checkout, membership
  (`memberdb.py`), payments (`linepay.py`), LINE push (`linepush.py`),
  notifications (`notify_arrivals.py`) and the read layer `posdb.py`.

## The cross-repo contract (change with care, in both repos together)

`posdb.py` is a read-only layer over the POS SQLite (WAL; safe concurrent
reads). It depends on this POS schema:

- `products` storefront columns: `slug`, `category_slug`, `tags` (JSON),
  `order_weight`, `is_on_sale`, `sale_price_twd`, `is_new_arrival`,
  `storefront_group`, `is_published` — plus the base columns
  (names/prices/preorder). `description_zhtw` (zh-TW) is the displayed site
  description; `description_enus` preserves the audited English source (not
  shown — `/en` 301-redirects to zh-TW; kept as an archive). `product_detail`
  picks by locale and falls back to zh-TW.
- `product_images` (kind cover|gallery|detail, sort_order, filename
  `media/<SKU>/<file>`) — images live on disk in the POS repo's `media/` dir,
  served by this app at `/static/images/products/<cat>/<slug>/<file>` with
  on-demand thumbnails (`thumb_*`).
- `inventory` (all locations) + `order_items` in 待配貨 on live orders →
  the availability engine in `posdb._availability` (priority order):
  1. in_stock 現貨: tw − waiting > 0 (overrides the preorder flag)
  2. incoming 約2週到貨: tw + in_transit + china − waiting > 0
  3. preorder 預購: is_preorder with future preorder_date
  4. orderable 可訂購約2-3週: not is_deprecated (can order from JoyToy)
  5. inquiry 絕版詢價: deprecated + not preorder — price hidden (final_price
     forced to 0), cart line shows 詢價
  Stale preorders (date passed) fall through to 4/5. Badges/notes live in
  `templates/public/_availability.html`. Show/hide on site = `is_published`.
- `storefront_categories`, `storefront_posts` (type blog|codex|promotion|page,
  extra JSON). Codex `body` is the displayed zh-TW; `body_enus` preserves the
  English source (archive, not shown). `title` is kept English as it's the
  `[[crosslink]]` anchor.
- `settings` keys `featured_products` (["category/slug", ...]), `featured_tags`,
  and `tag_glossary` (`{english_tag: zhtw_label}` — tags stay English keys for
  filtering; the `tag_label` Jinja filter shows the zh-TW label).

If a POS migration touches any of these, update `posdb.py` in the same
change and deploy both.

Caching: everything is cached in-process and invalidated when the DB file
mtime changes — POS edits appear on the site immediately. Don't add caches
that outlive `posdb.db_mtime()`.

Legacy: the flat-file loaders in `app.py` and the `content/` tree are dead
code kept for rollback (name-rebound to `posdb.*` at the bottom of app.py).
`import_from_pos.py` is obsolete.

## Membership

- Login: **Google OAuth** (`/auth/google`) and **LINE Login**
  (`/auth/line`, `bot_prompt=aggressive` prompts adding the 官方帳號);
  both offered on `/login`. Identities live in `member_identities`
  (provider, subject) — one member can own both; linking from 會員中心
  (`?link=1` OAuth mode) auto-merges duplicate accounts (wishlist/notify
  union, profile coalesce, dup row deleted).
- `/account`: profile (own name/phone/LINE ID), 收件資料 multi-address
  book (`member_addresses`, one default, selectable at checkout,
  auto-saves used addresses deduped), web-order history (matched by
  member email/phone against POS `web_orders`, read-only, incl. converted
  order statuses), 轉帳後五碼 reporting (→ POS API sets 待確認), wishlist,
  LINE binding state.
- LINE notification binding: LINE Login binds automatically; Google-only
  members send their 綁定碼 (shown on /account) to the OA — handled by
  `/line/webhook` (signature-verified with LINE_CHANNEL_SECRET).
- Guest checkout is allowed but **email is required when not logged in**;
  history appears retroactively if they later sign up with the same
  email/phone.

## Checkout & web orders

- `/checkout` groups the cart 一般/預購/詢價 (prices + availability
  re-resolved server-side from posdb at load AND submit — never trust the
  client), collects contact + 收件資料 (saved-address selector or manual:
  7-11/全家 store picker via `/api/stores` reading the POS store JSONs,
  郵局 address, 面交 = 雙北限定 note) + payment + 合併出貨(default)/現貨先出.
- Pricing: guests pay 定價 (sale-aware); members pay 會員價 =
  `regular_price_twd` when > 0 (0 = unset) else round(售價 × 0.9), capped
  by the sale price. Both prices show to everyone (slashed 定價 + 會員價
  tag); schema.org carries the guest price.
- 運費: NT$60 under NT$1,000 priced total, free at 1,000+, 面交 always
  free. Computed by the POS at submit; the LINE Pay charge must match POS
  `_charge_now_twd` exactly (now-items + fee − discount).
- Submit posts to POS `/api/storefront/orders` with the shared secret
  `STOREFRONT_API_KEY`; orders stage in POS `web_orders` for review
  (payment tracking lives there, NOT on internal orders).
- Payments: 取貨付款 (COD) · 銀行轉帳 (先審後付 — bank info only sent after
  order confirmation) · **LINE Pay pay-first** (`linepay.py`, v3
  request→redirect→confirm; sandbox creds in .env — production = swap
  channel creds + `LINEPAY_API_BASE=https://api-pay.line.me`). Confirm
  marks the web order 已付款 via the POS API; cancel/error keeps the order.

## Notifications & email

- Outgoing mail: Brevo SMTP relay (`SMTP_*` envs), From = `SMTP_FROM`
  (noreply@abbeystoys.com, domain DKIM-authenticated in Brevo),
  `Reply-To` = `REPLY_TO` (sales@abbeystoys.com → Cloudflare Email
  Routing catch-all → Gmail). Brevo silently drops mail from unvalidated
  senders AFTER accepting it over SMTP — check Brevo Transactional Logs
  when mail vanishes.
- `/api/internal/notify` (same shared secret): the POS pushes customer
  notifications through here — member matched by phone/email, LINE push
  first, email fallback; supports an `order_confirmed` template that
  composes transfer instructions (site holds `BANK_TRANSFER_INFO`).
- `notify_arrivals.py` (VM crontab, 10:00 daily): LINE-pushes/emails
  members whose 到貨通知 products flipped to 現貨.

## Quiz

`/quiz` — 「你是哪位原體？」16-question, 4-axis (忠誠/反骨 · 熱血/沉穩 ·
信念/理性 · 直率/深沉) personality test, 16 Primarch/character results,
animated axis graph, shareable `?r=<combo>&s=<scores>` URLs. Results link
to codex entries and legion products (prefers `/products?tag=<軍團>` when
that tag exists, else name search). Mapping in `app.py` (`QUIZ_RESULTS`),
copy in `templates/public/quiz.html` — all original writing; never import
question/result content from other quiz sites.

## Environment (.env)

`SECRET_KEY` (Flask sessions) · `POS_API_URL` · `STOREFRONT_API_KEY`
(shared with the POS) · `GOOGLE_CLIENT_ID/SECRET` ·
`LINE_LOGIN_CHANNEL_ID/SECRET` (LINE Login) ·
`LINE_CHANNEL_ACCESS_TOKEN/SECRET` (Messaging API / OA push + webhook) ·
`LINEPAY_CHANNEL_ID/SECRET/API_BASE` ·
`SMTP_SERVER/PORT/USERNAME/PASSWORD` · `SMTP_FROM` · `REPLY_TO` ·
`SHOP_EMAIL` · `BANK_TRANSFER_INFO` · optional `POS_DB` / `POS_MEDIA` /
`MEMBERS_DB`.

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
  VM, extracts, restarts the service, health-checks). **New top-level .py
  modules must be added to deploy.sh's tar file list or they won't ship**
  (this has bitten before). DNS: Cloudflare zone for abbeystoys.com,
  A records → 35.194.159.105, DNS-only (Caddy does TLS). `data/members.db`
  lives only on the VM — never shipped or overwritten by deploys.

## Design identity

Stained-glass workshop: walnut `#1E1712`, surface `#292019`, card `#342A21`,
lead `#17100B`, oak bronze `#6E4B2A`, candle amber `#D9A441`, parchment
`#E6DAC4`, glass blue `#8FA3B8`. Display type Cinzel + Noto Serif TC; body
Noto Sans TC. Signature: lead-came frames on cards, glass-panel hero.
The identity layer lives at the bottom of `static/css/public.css` —
prefer extending it over scattering new colors.
