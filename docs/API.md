# API (v0 contract)

Status: **planned** unless marked ✅. Base URL: `http://127.0.0.1:5055`. JSON in/out, `snake_case`,
ISO-8601 UTC timestamps. Auth: `Authorization: Bearer <jwt>` on everything except `/health` and
`/auth/*`. Errors: `{"error": {"code": "...", "message": "..."}}`.

| Status | Meaning |
|---|---|
| 400 | Validation error (bad/missing fields, e.g. `waste_reason` on a non-`thrown_out` removal) |
| 401 | Missing/invalid token |
| 403 | Authenticated but not your item/group |
| 404 | Not found (also for removed items on mutating calls) |
| 409 | Conflict (e.g. item already removed) |
| 502 | Upstream (Gemini / ML service) failed |

## Health
- ✅ `GET /health` → `200 {"status": "ok"}`

## Auth
- `POST /auth/signup` `{email, password, display_name}` → `201 {token, user}`
- `POST /auth/login` `{email, password}` → `200 {token, user}`

## Items
- `GET /items?storage=fridge|pantry|freezer&include_removed=false` → items sorted by `predicted_expiry`
- `POST /items` `{items: [{name, category, storage, quantity, unit, est_price?, predicted_expiry?, source}]}`
  → `201 {items}`; writes one `add` event per item. If `predicted_expiry` is omitted the backend
  predicts it (`expiry_source` = `default` | `gemini` | `user`).
- `PATCH /items/:id` — edit name/quantity/expiry/storage (sets `expiry_source=user` if expiry changed)
- `POST /items/:id/remove` — **the core endpoint**
  ```json
  {"outcome": "used" | "donated" | "thrown_out",
   "waste_reason": "expired" | "didnt_like" | "forgot" | "other",   // required iff thrown_out
   "recipient_id": "uuid"}                                          // optional, donated only
  ```
  → `200 {item}`. One transaction: sets `removed_at`, `outcome`, `waste_reason`,
  `removed_after_expiry`; writes a `remove` event; on `donated`, marks an open share listing
  `fulfilled`. `409` if already removed.

## Adding food
- `POST /items/parse-text` `{text}` → `{candidates: [item…]}` (Gemini; not saved until `POST /items`)
- `POST /items/from-photo` multipart `image`, `mode=fridge|single` →
  `{candidates: [{name, category, confidence, freshness: "fresh"|"spoiled", bbox?}], source: "yolo"|"gemini"}`
- `POST /items/from-receipt` multipart `image` → `{candidates: [{name, quantity, price}], total}`
- `GET /items/barcode/:code` → `{candidate}` (Open Food Facts)

## Recipes, impact, tips
- `POST /recipes/suggest` `{max_results?: 3, dietary?: []}` → recipes using the soonest-expiring items
- `GET /impact?range=week|month|all` →
  `{saved: {count, kg, money, co2e_kg}, wasted: {count, kg, money, co2e_kg}, waste_rate, weekly: [{week, saved, wasted}]}`
- `GET /tips` → personalised tips from waste reasons (e.g. most-forgotten item)

## Social (Wave 3)
- `GET/POST /friends`, `DELETE /friends/:id`
- `GET/POST /groups`, `POST /groups/:id/join`, `GET /groups/:id/pantry`
- `POST /share` `{item_id, group_id?}` / `GET /share` (Food Pantry: friends' + groups' open listings)
- `GET/POST /requests` (sticky-note board), `POST /requests/:id/fulfil`
