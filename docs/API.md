# API (v0 contract)

Status: ✅ = implemented in Wave 1 (backend core). Social endpoints are Wave 3 (planned). Base URL:
`http://127.0.0.1:5055`. JSON in/out, `snake_case`, ISO-8601 UTC timestamps (`...Z`). Auth:
`Authorization: Bearer <jwt>` (HS256, 30-day expiry) on everything except `/health` and `/auth/*`.
Errors always: `{"error": {"code": "...", "message": "..."}}` (including 404/405/413/500).
UUID path ids that are malformed return 404. Numeric money/weight fields serialise as JSON numbers.

| Status | `code` values | Meaning |
|---|---|---|
| 400 | `validation_error` | Bad/missing fields, e.g. `waste_reason` on a non-`thrown_out` removal |
| 401 | `unauthorized`, `invalid_credentials` | Missing/invalid/expired token; bad login |
| 403 | `forbidden` | Authenticated but not your item |
| 404 | `not_found` | Not found (also for removed items on `PATCH`) |
| 405 | `method_not_allowed` | |
| 409 | `already_removed`, `already_shared`, `email_taken` | Conflict |
| 413 | `payload_too_large` | Upload over 10 MB |
| 500 | `internal_error` | Unhandled error |
| 502 | `upstream_unavailable` | Gemini / ML service / Open Food Facts unavailable or not configured |

## Health
- ✅ `GET /health` → `200 {"status": "ok"}`

## Auth
- ✅ `POST /auth/signup` `{email, password (>=8 chars), display_name}` → `201 {token, user}`;
  `409 email_taken`. Emails are case-insensitive.
- ✅ `POST /auth/login` `{email, password}` → `200 {token, user}`; `401 invalid_credentials`.
- `user` = `{id, email, display_name, created_at}`.

## Items
An **item** is `{id, owner_id, group_id, name, category, storage, quantity, unit, est_weight_kg,
est_price, source, added_at, predicted_expiry (date), expiry_source, removed_at, outcome,
waste_reason, removed_after_expiry}`. `category` ∈ `produce_leafy, produce_hardy, dairy, meat,
seafood, bakery, eggs, leftovers, pantry_dry, frozen, other`; `storage` ∈ `fridge|pantry|freezer`;
`source` ∈ `photo|single_photo|text|barcode|receipt|manual`.

- ✅ `GET /items?storage=fridge|pantry|freezer&include_removed=false` → `200 {items}` sorted by
  `predicted_expiry`, then `added_at`. Only the caller's items. Invalid `storage` → 400.
- ✅ `POST /items` `{items: [{name, category?, storage?, quantity?, unit?, est_price?, est_weight_kg?,
  predicted_expiry?, source?}]}` → `201 {items}` (1-100 items). Defaults: category `other`, storage
  `fridge`, quantity 1, unit `piece`, source `manual`. Invalid enum/negative number → 400 and nothing
  is written. One `add` event per item, same transaction. If `predicted_expiry` is omitted the
  backend predicts it: Gemini batch estimate when configured (`expiry_source=gemini`), else the
  default shelf-life table (`default`); a client-supplied expiry is stored as `user`.
  `est_weight_kg` is estimated from quantity/unit/category when absent.
- ✅ `PATCH /items/:id` — body may contain `name, quantity, unit, storage, category,
  predicted_expiry, est_price, est_weight_kg` (unknown fields → 400). Changing the expiry sets
  `expiry_source=user`. Changing quantity/unit/category re-estimates `est_weight_kg` unless sent.
  → `200 {item}`; `403` other user's item; `404` unknown or already removed.
- ✅ `POST /items/:id/remove` — **the core endpoint**
  ```json
  {"outcome": "used" | "donated" | "thrown_out",
   "waste_reason": "expired" | "didnt_like" | "forgot" | "other",   // required iff thrown_out
   "recipient_id": "uuid"}                                          // optional, donated only
  ```
  → `200 {item}`. Order of checks: body validation (400) → item lookup (404) → ownership (403) →
  already removed (409 `already_removed`). One transaction (row-locked): sets `removed_at`,
  `outcome`, `waste_reason`, `removed_after_expiry` (removed date > `predicted_expiry`); writes
  exactly one `remove` event (`co2e_kg`, weight, price, outcome, reason); on `donated`, marks the
  item's open share listing `fulfilled` (+`recipient_id`, `fulfilled_at`). `recipient_id` must be
  an existing user (else 400). A 4xx writes no event.

## Adding food
Candidates are **not saved** until `POST /items`. Every candidate also carries a suggested
`storage`, `quantity`, `unit`, `est_price`, `predicted_expiry` and `expiry_source` so the client can
post it straight back.
- ✅ `POST /items/parse-text` `{text (<=4000 chars)}` → `200 {candidates: [item…]}` (Gemini);
  `502 upstream_unavailable` when Gemini is not configured/failing.
- ✅ `POST /items/from-photo` multipart `image` (required), `mode=fridge|single` (default `fridge`) →
  `200 {candidates: [{name, category, confidence, freshness: "fresh"|"spoiled", bbox: [x1,y1,x2,y2]|null,
  …}], source: "yolo"|"gemini"}`. Uses `ML_SERVICE_URL`/detect when set; if unset **or the ML
  service errors**, falls back to Gemini vision; neither → `502`.
- ✅ `POST /items/from-receipt` multipart `image` → `200 {candidates: [{name, quantity, price}], total}`
  via `ML_SERVICE_URL`/ocr; `502` when unset or failing. `quantity` defaults to 1.
- ✅ `GET /items/barcode/:code` (6-14 digits, else 400) → `200 {candidate}` (Open Food Facts, adds
  `barcode`, `brand`, `quantity_text`); `404 not_found` unknown product; `502` OFF unreachable.

## Share (minimal, Wave 1)
- ✅ `POST /share` `{item_id, group_id?}` → `201 {listing}` (`status=open`; writes a `share` event).
  `403` not your item; `404`; `409 already_removed` / `409 already_shared`.
  `listing` = `{id, item_id, owner_id, group_id, status, recipient_id, created_at, fulfilled_at}`.
  `GET /share` and the Food Pantry are Wave 3.

## Recipes, impact, tips
- ✅ `POST /recipes/suggest` `{max_results?: 3 (1-10), dietary?: [str]}` → `200 {recipes: [{title,
  minutes, uses_items, missing_items, steps}]}` built from the caller's 20 soonest-expiring active
  items. With no active items → `200 {recipes: []}` without calling Gemini; Gemini missing → `502`.
- ✅ `GET /impact?range=week|month|all` (default `all`; week=last 7 days, month=last 30; bad → 400) →
  `{saved: {count, kg, money, co2e_kg}, wasted: {count, kg, money, co2e_kg}, waste_rate, weekly:
  [{week (date of bucket start), saved, wasted}]}`. `saved` = `used`+`donated` removals, `wasted` =
  `thrown_out`; `weekly` values are counts; `waste_rate = wasted.count / (saved.count + wasted.count)`
  (0 when empty). Computed from `food_events` with `time_bucket('1 week', time)`; money/kg/co2e
  rounded to 2 dp. Zero data → zeros and `weekly: []`.
- ✅ `GET /tips` → `200 {tips: [{code, message}]}`. Based on the last 90 days of `thrown_out` events
  (top reason, most-wasted item, most-wasted category) plus items expiring within 2 days. Zero data
  → one `getting_started` tip.

## Social (Wave 3)
- `GET/POST /friends`, `DELETE /friends/:id`
- `GET/POST /groups`, `POST /groups/:id/join`, `GET /groups/:id/pantry`
- `GET /share` (Food Pantry: friends' + groups' open listings)
- `GET/POST /requests` (sticky-note board), `POST /requests/:id/fulfil`
