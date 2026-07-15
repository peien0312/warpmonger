# GA4 setup guide (abbeystoys.com)

- Property: `properties/544443478` "ABBEY'S TOYS 阿北玩具堂" (created 2026-07-07)
- Web stream: `G-FV2XNYBDS5` (the old default `G-HYSSEZVZNK` in app.py was a
  stale earlier property; prod overrides via `GA4_MEASUREMENT_ID`)

The site's templates send a full e-commerce event stream. GA4, however, only
surfaces custom event parameters and funnels after one-time property setup.
**Sections 1, 2 and the retention bump were applied 2026-07-16 via the Admin
API** (see "API automation" at the bottom) — kept here as the record of what
exists and how to recreate it.

## What the site sends

### E-commerce (standard GA4 events — work with built-in reports)

| Event | Fired from | Notes |
|---|---|---|
| `view_item_list` | /products grids, home 新品上架 + 精選商品, related-products carousel | list impressions; `item_list_name` says which list |
| `select_item` | every click on a product link, site-wide | `item_list_name` = origin: `home:new-arrivals`, `home:featured`, `related-products`, `search-suggestions`, category name, `Tag: <tag>`, `Search: <term>`, `blog:<slug>`, `codex:<slug>`, `quiz`, or `page:<path>` fallback |
| `view_item` | product detail page load | |
| `add_to_cart` / `remove_from_cart` | product page / cart page | |
| `view_cart` | /cart | |
| `begin_checkout` | /checkout load | |
| `add_shipping_info` / `add_payment_info` | checkout steps | |
| `purchase` | checkout success page | value = charge amount, TWD |
| `add_to_wishlist` | wishlist heart button | |
| `select_promotion` | home promo banner, quiz result CTA | |
| `search` | header search submit | `search_term` |
| `sign_up` / `login` | after OAuth return | `method` = google/line |

### Custom events (need custom dimensions registered to be reportable)

| Event | Params | Meaning |
|---|---|---|
| `select_content` | `content_type` (blog_post/codex_entry), `content_id` (title) | click on a blog/codex card |
| `article_read` | `content_type`, `content_id` (post slug) | reader reached the end of a blog post body |
| `quiz_complete` | `quiz_result`, `character`, `legion` | quiz finished (first time only) |
| `filter_applied` | `filter_type`, `filter_value` | product list filter/sort used |
| `video_start` | — | hero intro video |

## One-time GA4 property setup

### 1. Register custom dimensions — ✅ done 2026-07-16 via API

All **event-scoped**. Without these, the params are collected but invisible in
reports. Registration is not retroactive — do it once, data appears from then on.

| Dimension name | Event parameter |
|---|---|
| Content type | `content_type` |
| Content ID | `content_id` |
| Quiz result | `quiz_result` |
| Quiz character | `character` |
| Quiz legion | `legion` |
| Filter type | `filter_type` |
| Filter value | `filter_value` |

Do **not** register `item_list_name`, `item_id`, `search_term`, `method` — those
are built-in dimensions (Item list name, Item ID, Search term, Method) and
already work.

### 2. Mark key events — ✅ done 2026-07-16 via API

Key events on the property: `purchase`, `generate_lead`, `sign_up` (pre-existing)
+ `begin_checkout`, `add_to_cart`, `quiz_complete` (added).

Key events unlock per-channel conversion columns in acquisition reports
(which traffic source produces carts/checkouts, not just sessions).

### 3. Cart-flow funnel (探索 Explore → 程序探索 Funnel exploration)

Build once, saved to your Explorations list. Steps (all「間接關聯」/ indirectly
followed by):

1. `view_item` — 看商品
2. `add_to_cart` — 加入購物車
3. `view_cart` — 看購物車
4. `begin_checkout` — 開始結帳
5. `add_shipping_info` — 填寫寄送
6. `add_payment_info` — 選擇付款
7. `purchase` — 完成購買

Useful settings:
- 顯示流失 (Show elapsed time / abandonment) on — shows drop-off % per step.
- Breakdown dimension: `裝置類別` (device) or `第一個使用者來源` (first user source)
  to see where mobile vs desktop or FB vs Google traffic leaks.
- Make it an **open funnel** if you want users entering mid-flow counted.

### 4. Product-click origin report (where clicks come from)

Two ways to read `select_item` / `item_list_name`:

- **Built-in**: 報表 → 營利 → 電子商務購買 — add/plot the
  「商品清單名稱」(Item list name) dimension; metrics 已點按項目 (Items clicked
  in list) and 已檢視項目 (Items viewed in list) give per-section CTR.
- **Explore free-form**: rows = Item list name + Item name, values =
  Items clicked in list, Items viewed in list, Items added to cart. This
  answers "which home section / category page / blog post drives clicks".

Blog-driven product clicks show up as `item_list_name = blog:<slug>`.

### 5. Blog performance report

Explore free-form: rows = 事件名稱 filtered to `select_content` + `article_read`,
breakdown = Content ID (custom dimension from step 1). Compare with 網頁路徑
pageviews to get read-through rate per post.

### 6. Recommended extras (no code involved)

- **管理 → 資料串流 → 加強型評估**: keep scroll/outbound/site-search on.
- **Search Console link** (管理 → Search Console 連結): pulls Google-search
  query data into GA4 — complements the click-source picture.
- **Data retention**: ✅ set to 14 months via API 2026-07-16.
- **Internal traffic filter**: 管理 → 資料串流 → 更多標記設定 → 定義內部流量,
  add your home/office IP, then activate the filter under 資料設定 → 資料篩選器.

## Debugging

- Realtime check: open the site with `?_dbg=1`… simplest is GA4 DebugView
  (管理 → DebugView) with the [GA Debugger Chrome extension] on, then click
  around — every event and its params show live.
- Events also appear in 報表 → 即時 within seconds; custom-dimension breakdowns
  take 24–48 h to appear in standard reports.

## API automation

The GA4 property is manageable headlessly through the service account
`ga4-admin@warpmonger-prod.iam.gserviceaccount.com` (created 2026-07-16;
GA4 property 編輯者 + impersonatable by the gcloud user via
`roles/iam.serviceAccountTokenCreator`). No key files — mint short-lived
tokens by impersonation:

```sh
TOK=$(gcloud auth print-access-token \
  --impersonate-service-account=ga4-admin@warpmonger-prod.iam.gserviceaccount.com \
  --scopes=https://www.googleapis.com/auth/analytics.edit,https://www.googleapis.com/auth/analytics.readonly)

# Admin API (dimensions, key events, retention):
curl -H "Authorization: Bearer $TOK" \
  https://analyticsadmin.googleapis.com/v1beta/properties/544443478/customDimensions

# Data API (reports, incl. funnels via v1alpha runFunnelReport):
curl -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"dateRanges":[{"startDate":"30daysAgo","endDate":"today"}],"dimensions":[{"name":"itemListName"}],"metrics":[{"name":"itemsClickedInList"}]}' \
  https://analyticsdata.googleapis.com/v1beta/properties/544443478:runReport
```

Note the direct browser path (`gcloud auth application-default login
--scopes=…analytics…`) is blocked by Google for the default gcloud OAuth
client — the service account is the supported route.
