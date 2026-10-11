# API (v0 contract)

Status: ✅ = implemented in Wave 1 (backend core). Social endpoints are Wave 3 (✅ implemented, migration `0002_social`). Base URL:
`http://127.0.0.1:5055`. JSON in/out, `snake_case`, ISO-8601 UTC timestamps (`...Z`). Auth:
`Authorization: Bearer <jwt>` (HS256, 30-day expiry) on everything except `/health` and `/auth/*`.
Errors always: `{"error": {"code": "...", "message": "..."}}` (including 404/405/413/500).
UUID path ids that are malformed return 404. Numeric money/weight fields serialise as JSON numbers.

| Status | `code` values | Meaning |
|---|---|---|
| 400 | `validation_error` | Bad/missing fields, e.g. `waste_reason` on a non-`thrown_out` removal |
| 401 | `unauthorized`, `invalid_credentials` | Missing/invalid/expired token; bad login |
| 403 | `forbidden` | Authenticated but not your item / not a member of that group / not the owner or author |
| 404 | `not_found` | Not found (also for removed items on `PATCH`) |
| 405 | `method_not_allowed` | |
| 409 | `not_removed`, `restore_window_expired`, `already_removed`, `already_shared`, `email_taken`, `already_friends`, `request_pending`, `already_member`, `already_claimed`, `listing_closed`, `request_closed` | Conflict |
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
- ✅ `DELETE /auth/me` (Bearer) → `204` (App Store account deletion). One transaction. **Deleted:** the
  user, their items (including ones in group pantries), every listing on those items and their own
  listings, friendships (both directions), group memberships, requests they wrote. **Detached:** listings
  they claimed/received elsewhere get `claimed_by`/`recipient_id` null (open again); requests they
  fulfilled are reopened; ownership of groups they owned passes to the longest-standing remaining
  member and `groups.created_by` becomes null (`created_by: null` in group responses). **Anonymised:**
  their `food_events` keep every number but `user_id` becomes the nil UUID
  `00000000-0000-0000-0000-000000000000`, so aggregates survive with no personal link. The same JWT
  then fails with `401 unauthorized`; login fails with `401 invalid_credentials`.

## Items
An **item** is `{id, owner_id, group_id, name, category, storage, quantity, unit, est_weight_kg,
est_price, source, added_at, predicted_expiry (date), expiry_source, removed_at, outcome,
waste_reason, removed_after_expiry, freshness, freshness_checked_at, confidence, share}`
(`expiry_source` ∈ `default|gemini|ml|user`). `category` ∈ `produce_leafy, produce_hardy, dairy, meat,
seafood, bakery, eggs, leftovers, pantry_dry, frozen, other`; `storage` ∈ `fridge|pantry|freezer`;
`source` ∈ `photo|single_photo|text|barcode|receipt|manual`.
- **Numeric bounds** (create and `PATCH`, BE-9): `est_price` 0..99,999,999.99 (column is
  `numeric(10,2)`), `quantity` >0..1,000,000, `est_weight_kg` 0..100,000. Out of range, negative,
  non-numeric or non-finite → `400 validation_error`, nothing written (never a 500).
- `freshness` (`fresh|semi_fresh|spoiled|null`) and `freshness_checked_at` (timestamp of the last
  assessment, null iff `freshness` is null): stored when a create payload carries `freshness`
  (validated via `candidates.normalize_freshness`: variants such as `rotten` map, unknown strings become
  `fresh` with a WARNING, a non-string is `400`); `freshness_checked_at` = now. `confidence` is the
  detector's 0..1 score (create only; `400` outside 0..1), null for manual items. All three are on
  every item response.
- `share` is present on the **owner's own** items (`GET /items`, also with `group_by`; create, `PATCH`,
  `remove`, `restore` responses) and is `{id, status (open|fulfilled), claimed_by: {id, name} | null}` for
  the item's most recent **non-cancelled** listing, else `null`. Loaded with a single query for the whole
  list (no N+1). The group pantry (`GET /groups/:id/pantry`) and other users' views do **not** include it.

- ✅ `GET /items?storage=fridge|pantry|freezer&include_removed=false` → `200 {items}` sorted by
  `predicted_expiry`, then `added_at`. Only the caller's **personal** items (`group_id` null; group-pantry items are listed by `GET /groups/:id/pantry`). Invalid `storage` → 400.
- ✅ `POST /items` `{items: [{name, category?, storage?, quantity?, unit?, est_price?, est_weight_kg?,
  predicted_expiry?, source?, group_id?}], group_id?}` → `201 {items}` (1-100 items). A top-level `group_id` applies to every item; a per-item `group_id` overrides it. A group `group_id` puts the item in that group's pantry; caller must be a member (`403` otherwise, `404` unknown group; nothing written). Defaults: category `other`, storage
  `fridge`, quantity 1, unit `piece`, source `manual`. Invalid enum/negative number → 400 and nothing
  is written. One `add` event per item, same transaction. If `predicted_expiry` is omitted the
  backend predicts it: Gemini batch estimate when configured (`expiry_source=gemini`), else the
  default shelf-life table (`default`); a client-supplied expiry is stored as `user`.
  `est_weight_kg` is estimated from quantity/unit/category when absent.
  **Candidate round trip:** post a candidate back as-is, including `expiry_source`
  (`default|gemini|ml`), and that source is **kept** when `predicted_expiry` is sent. Edit detection is
  client-driven and the server trusts the enum: the client sends `expiry_source: "user"` (or omits the
  field, which defaults to `user`) once the person changed the date. Invalid value → `400`; a
  `expiry_source` sent without `predicted_expiry` is ignored (the backend predicts and sets it).
  `freshness` and `confidence` from the candidate are stored (see above).
- ✅ `PATCH /items/:id` — body may contain `name, quantity, unit, storage, category, food_group,
  predicted_expiry, est_price, est_weight_kg, freshness` (unknown fields → 400, so `confidence` is not
  editable). `freshness` set → stored and `freshness_checked_at` = now; `freshness: null` clears **both**
  (null means "never assessed"). Changing the expiry sets
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
  an existing user (else 400). A 4xx writes no event. **Group-pantry items (`group_id` set) can be
  removed by any member of that group**; the `remove` event's `user_id` is the *remover* and carries
  the item's `group_id`, so impact is credited to whoever removed it. Personal items of other users
  stay `403`; non-members of the group get `403`. `PATCH` stays owner-only. If the item's open
  listing was claimed and `recipient_id` is omitted, the claimer becomes `recipient_id`.

- ✅ `POST /items/:id/restore` (no body) → `200 {item}`. Undoes a removal made less than **10 minutes**
  ago (same permission as remove: owner, or any member for a group-pantry item). `409 not_removed` if
  the item is active, `409 restore_window_expired` after 10 minutes, `403`/`404` as for remove. One
  transaction under the row lock: clears `removed_at`, `outcome`, `waste_reason`,
  `removed_after_expiry`; **deletes the item's `remove` event** (by id + time) so `/impact`, `/tips` and
  any other event query are automatically correct; and if the removal fulfilled a listing
  (`fulfilled_at == removed_at`) the listing goes back to `open` with `fulfilled_at` and `recipient_id`
  cleared (`claimed_by` kept). The `share` event from listing creation is untouched.

- ✅ `POST /items/remove-batch` `{"item_ids": ["uuid", …] (1-100, unique), "outcome": "used" | "donated"}`
  → `200 {items: [item…]}` (request order; `share` on the caller's own items). **All or nothing.**
  `thrown_out` is not allowed here (it needs a per-item `waste_reason`; use the single endpoint), and so
  are `waste_reason` / `recipient_id` / any other field (`400`). Order of checks: body validation (400:
  empty/oversized/duplicate/malformed ids, bad outcome, unknown field) → lookup + visibility (**`404
  not_found` for the whole batch** if any id is unknown or not removable by the caller: another user's
  personal item, or a group-pantry item of a group you are not in) → `409 already_removed` if any item is
  already removed. Otherwise one transaction with all rows locked (`FOR UPDATE`, id order): same per-item
  effects as `POST /items/:id/remove` (one `remove` event each, `user_id` = caller, same `removed_at` for
  the batch); `donated` fulfils each item's open listing with `recipient_id` = its `claimed_by`. A 4xx
  writes nothing. Constant query count regardless of batch size.
- ✅ `POST /items/restore-batch` `{"item_ids": [...]}` (same id rules) → `200 {items}`. All or nothing:
  `404` as above, `409 not_removed` if any item is active, `409 restore_window_expired` if any removal is
  older than 10 minutes. Otherwise mirrors `POST /items/:id/restore` per item (deletes its `remove`
  event, reopens a listing that removal fulfilled). `remove-batch` then `restore-batch` leaves `/impact`
  exactly as before. Items removed singly can be restored in a batch and vice versa.

## Food groups (`food_group`)
`food_group` is the user-facing grouping: `protein | veggies | fruit | dairy | grains | pantry |
leftovers | frozen | other`. It is separate from the spoilage `category` (which still drives expiry and
CO2e). Returned on every item response and every candidate (parse-text, from-photo, from-receipt,
barcode). `POST /items` and `PATCH /items/:id` accept it (invalid -> `400 validation_error`); when
omitted on create it is derived from `category` + name (meat/seafood/eggs -> protein, bakery -> grains,
pantry_dry -> pantry, dairy/leftovers/frozen/other -> same name, produce_* -> `fruit` if the name is a
known fruit else `veggies`).
**PATCH rules:** (1) an explicit `food_group` always wins (valid value, else `400`), including when
`category` is sent in the same request; (2) `category` without `food_group` re-derives `food_group`
from the new category + current name (this overwrites a previous manual choice); (3) a `name`-only
change does **not** re-derive (the user's grouping is left alone); `name` + `category` re-derives. Sending `"food_group": null` returns `400` (to clear a manual group, send `category` again so it re-derives).
Receipt lines (`from-receipt`) without a Gemini category get their `food_group` from a deterministic keyword
match on whole, case-insensitive name tokens (with receipt abbreviations such as `CHKN`, `GRND BF`,
`YGRT`, `BRD`, `FROZ`, `MLK`, `OJ`, `TOM`, `SLMN` expanded): frozen, then pantry modifiers (juice, sauce, broth, soup, peanut
butter...), dairy, protein, grains, fruit, common vegetables, other pantry staples; no match -> `other`.
No Gemini call is involved. Tables: `backend/app/services/food_group.py`.
Candidates use the ML service's `food_group` when present, else Gemini's (validated), else the heuristic.
- ✅ `GET /items?group_by=food_group` (only valid value; anything else -> `400`) →
  `200 {sections: [{food_group, items: [item…]}]}`. Sections follow the Fridge design order
  (protein, veggies, fruit, dairy, then grains, pantry, leftovers, frozen, other); **empty sections
  are omitted**; items within a section sort by `predicted_expiry` ascending (nulls last). Other
  filters (`storage`, `include_removed`) still apply. Without `group_by` the response is unchanged
  (`{items: [...]}`).

## Adding food
Candidates are **not saved** until `POST /items`. Every candidate also carries a suggested
`storage`, `quantity`, `unit`, `est_price`, `predicted_expiry` and `expiry_source` so the client can
post it straight back.
- ✅ `POST /items/parse-text` `{text (<=4000 chars)}` → `200 {candidates: [item…]}` (Gemini);
  `502 upstream_unavailable` when Gemini is not configured/failing.
- ✅ `POST /items/from-photo` multipart `image` (required), `mode=fridge|single` (default `fridge`) →
  `200 {candidates: [{name, category, confidence, freshness: "fresh"|"semi_fresh"|"spoiled", bbox: [x1,y1,x2,y2]|null,
  …}], source: "yolo"|"gemini"}`. Uses `ML_SERVICE_URL`/detect when set; if unset **or the ML
  service errors**, falls back to Gemini vision; neither → `502`.
  `freshness` is normalised server-side for both sources (`candidates.normalize_freshness`): the
  three values pass through; variants map `semi-fresh`/`semi fresh`/`use soon`/… → `semi_fresh`
  and `rotten`/`stale`/`moldy`/`overripe`/`decayed`/… → `spoiled` (case/hyphen/space-insensitive; the word
  lists mirror `SEMI_WORDS`/`SPOILED_WORDS` in `ml/yolo/taxonomy.py`, and `ripe` is fresh in both); anything unknown or
  missing becomes `fresh` and logs a WARNING (`freshness_fallback raw=… source=yolo|gemini`). It is
  informational on the candidate and does not change `predicted_expiry`; post it back with
  `POST /items` to store it on the item (`freshness`, `freshness_checked_at`).
- ✅ `POST /items/from-receipt` multipart `image` → `200 {candidates: [item…], total, categorized_by:
  "gemini"|"heuristic"}` via `ML_SERVICE_URL`/ocr; `502` when unset or failing. Each candidate is a full
  item like the other add paths (`name, category, food_group, storage, quantity, unit, est_price,
  predicted_expiry, expiry_source`) plus `price` (= `est_price`, kept for older clients) and
  `receipt_text` (the line as printed), so it can be posted straight back to `POST /items`.
  With Gemini configured, **one call per receipt** (`gemini.categorize_receipt_lines`, JSON schema with the
  category / food_group / storage enums) turns abbreviated lines into readable names (`GV WHL MILK GAL` →
  `Whole milk`) with category, food group and storage. Without Gemini, or if that call fails, `name` stays
  as printed and the category comes from the food-group heuristic below (`categorized_by: "heuristic"`):
  dairy→dairy, grains→bakery, pantry→pantry_dry, fruit/veggies→produce_leafy (short-life on purpose),
  protein→seafood/eggs/meat by keyword, else `other`. Numbers may arrive as strings (`"$3.48"`, `"1,29"`)
  and are parsed; unusable → `price: null` / `total: null`; `quantity` defaults to 1 (and to 1 if not positive).
  Receipt total/payment lines are dropped before Gemini and before building candidates
  (`candidates.is_receipt_total`): the name must start with optional `sales`/`grand`/card-network prefixes
  plus a keyword (`total`, `subtotal`/`sub total`/`sub-total`, `tax`, `change`, `cash`, `card`, `balance`,
  `tender`, or a card network `visa|debit|credit|mastercard|mc|amex|discover`), followed only by amounts,
  `%`/currency/punctuation, masked card digits (`****1234`, `x1234`, `XXXX1234`) or the words `due, amount,
  amt, paid, tendered, tend, back, purchase, sale, savings, saved, auth, approved, chip, contactless` (or a
  card network). So `TOTAL 4.21`, `CHANGE DUE`, `VISA CREDIT ****1234` are dropped; `Total Cereal`,
  `Cash & Carry Crackers`, `Cashews` are kept. Coupon/discount lines follow the same rule with the keywords
  `coupon`, `discount`, `savings`, `instant savings`, `mfr` (`MFR COUPON`, `COUPON $1.00 OFF`; `off` is an
  allowed tail word), and any line with a **negative price** is dropped too (`candidates.is_receipt_noise`),
  since `POST /items` rejects negative prices.
- **Gemini category guide.** Every Gemini prompt that assigns a category (text parse, vision, receipt
  lines) carries the same definitions as `ml/yolo/taxonomy.py`: `produce_leafy` = short-life produce
  (greens, herbs, berries, tomatoes, cucumbers, peppers, bananas, avocados, papaya, pineapple...),
  `produce_hardy` = long-life produce (apples, citrus, pears, roots, onions, eggplant...), so Gemini and YOLO
  give the same shelf life for the same food. Transient Gemini errors (503 `UNAVAILABLE` "high demand",
  429, 504) are retried once after 1.5 s inside the same call (still one `gemini_usage` log line).
- ✅ `GET /items/barcode/:code` (6-14 digits, else 400) → `200 {candidate}` (Open Food Facts, adds
  `barcode`, `brand`, `quantity_text`); `404 not_found` unknown product; `502` OFF unreachable.

## Share / Food Pantry
`listing` = `{id, item_id, owner_id, group_id, status (open|fulfilled|cancelled), recipient_id,
claimed_by, created_at, fulfilled_at}`.
- ✅ `POST /share` `{item_id, group_id?}` → `201 {listing}` (`status=open`; writes a `share` event).
  No `group_id` = shared to the owner's accepted friends; `group_id` = shared to that group only.
  `403` not your item / not a member of `group_id`; `404` unknown item or group; `409
  already_removed` / `already_shared`; `400` for a group-pantry item (those cannot be shared).
- ✅ `GET /share` → `200 {listings: [...]}` — the Food Pantry, newest first. Open listings whose
  item is still active, **excluding your own**, that are either (a) a friends-listing by one of your
  accepted friends or (b) in one of your groups. Listings claimed by someone else are hidden; ones
  you claimed show with `claimed_by_me: true`. Each entry: `{id, item_id, owner_id, owner_name,
  group_id, status, claimed_by_me, created_at, source: {type: "friend"|"group", name}, item: {name,
  category, quantity, unit, predicted_expiry}}` (`source.name` = owner's display name for `friend`,
  group name for `group`).
- ✅ `DELETE /share/:id` → `200 {listing}` (`status=cancelled`). Owner only: `403` for a viewer who
  can see it, `404` if invisible/unknown, `409 listing_closed` if not open.
- ✅ `POST /share/:id/claim` → `200 {listing}` (`claimed_by` = you). `404` if you cannot see the
  listing, `400` your own, `409 already_claimed`, `409 listing_closed` (not open / item removed).
  The owner then removes the item with `outcome=donated` (optionally `recipient_id`; defaults to the
  claimer), which sets the listing `fulfilled`.

## Friends
Friendship is one row, requester → target; once accepted it is symmetric. Entry shape:
`{user_id (the other person), display_name, status, created_at}`.
- ✅ `POST /friends` `{email}` → `201 {friend}` (`status=pending`). `404` unknown email, `400` self /
  missing email, `409 already_friends` / `409 request_pending` (in either direction).
- ✅ `POST /friends/:user_id/accept` → `200 {friend}` (`status=accepted`). Only the target can accept:
  `404` when there is no pending request *from* `:user_id` to you.
- ✅ `GET /friends` → `200 {friends: [...], incoming: [...], outgoing: [...]}` (accepted; pending
  received; pending sent).
- ✅ `DELETE /friends/:user_id` → `204`. Removes the relationship in either direction and either
  status (unfriend / cancel / decline); `404` if none exists. Visibility ends immediately.

## Groups
`group` = `{id, name, role (owner|member — yours), member_count, invite_code, created_by,
created_at}`; `GET /groups/:id` adds `members: [{user_id, display_name, role, joined_at}]`. Invite
codes are 8 chars from `ABCDEFGHJKMNPQRSTUVWXYZ23456789` (no 0/O/1/I/L); joining is
case-insensitive and ignores spaces/dashes.
- ✅ `POST /groups` `{name (1-60 chars)}` → `201 {group}` (creator = `owner`).
- ✅ `GET /groups` → `200 {groups}` (mine only).
- ✅ `GET /groups/:id` → `200 {group}`; `404` unknown, **`403` not a member**.
- ✅ `POST /groups/join` `{invite_code}` → `200 {group}`; `404` bad code, `409 already_member`.
- ✅ `POST /groups/:id/leave` → `200 {left: true}`; `404` unknown, `403` not a member. If the owner
  leaves, the longest-standing member becomes owner. The leaver's open listings and requests in that
  group are cancelled. A group whose last member leaves is kept but unreachable.
- ✅ `GET /groups/:id/pantry` → `200 {items}` — the group's active items by `predicted_expiry`, each
  an item plus `added_by` (display name). `404` unknown, `403` not a member.

## Request board
`request` = `{id, author_id, author_name, group_id, group_name, text, status (open|fulfilled|
cancelled), fulfilled_by, fulfilled_by_name, created_at, source: {type: "me"|"friend"|"group",
name}}` — `source` drives the sticky-note header (`me` → your display name, `friend` → author's name,
`group` → group name).
- ✅ `POST /requests` `{text (1-280 chars), group_id?}` → `201 {request}`. No `group_id` = visible to
  your friends. `403` not a member of `group_id`, `404` unknown group, `400` bad text.
- ✅ `GET /requests` → `200 {requests}` — open only, newest first: your own, friends' non-group
  requests, and requests in your groups.
- ✅ `POST /requests/:id/fulfil` → `200 {request}` (`status=fulfilled`, `fulfilled_by` = you). `404`
  if you cannot see it, `403` your own, `409 request_closed` if not open.
- ✅ `DELETE /requests/:id` → `200 {request}` (`status=cancelled`). Author only: `403` for a viewer
  who can see it, `404` invisible/unknown, `409 request_closed` if not open.

## Visibility rules (security core)
- Friend-scoped things (friends-listings, group-less requests) are visible only to **accepted**
  friends of the author, plus the author. Pending requests grant nothing; unfriending revokes at once.
- Group-scoped things are visible only to current members of that group.
- **Resource ids** (listing, request) you may not see return **`404`**, same as nonexistent, so
  existence does not leak. **Group-addressed endpoints** (`/groups/:id…`, a `group_id` in a body)
  return `404` for an unknown group and **`403`** for a group you are not in.
- Acting on a visible resource you lack the right for (cancel someone else's listing/request) is `403`.

## Recipes, impact, tips
- ✅ `POST /recipes/suggest` `{max_results?: 3 (1-10), dietary?: [str]}` → `200 {recipes: [{title,
  minutes, servings, uses_items, missing_items, steps, macros, macros_estimated}]}` built from the caller's
  20 soonest-expiring active items.
  - `servings`: int 1-20 from Gemini, else `null`.
  - `uses_items`: `[{item_id, name, predicted_expiry (date)}]` — Gemini's names mapped back to the
    caller's items (case/space-insensitive exact match, then containment; soonest-expiring wins; each
    item at most once per recipe). Names that match no item are dropped. `missing_items` stays `[str]`.
  - `macros` = `{kcal: int, protein_g, carbs_g, fat_g}` per serving, estimated by Gemini (validated:
    kcal 0-3000, grams 0-300, numeric); missing/invalid -> `macros: null` (no error).
    `macros_estimated` is always `true`.
  - **Cache:** per user, keyed by a SHA-256 of all the caller's active items (id, name, category,
    quantity, unit, expiry) plus `max_results` and `dietary`; TTL 6 h (`RECIPE_CACHE_TTL_SECONDS`, `0`
    disables). Any add/edit/remove/restore changes the key, so the next call goes to Gemini. In-process
    per gunicorn worker (not shared, lost on restart). Each lookup logs one INFO line on
    `app.recipes.cache`: `recipes_cache status=hit age_s=<n>` or `status=miss reason=empty|items_changed|expired`
    (no user data). Errors (`502`) are not cached.
  - With no active items → `200 {recipes: []}` without calling Gemini; Gemini missing → `502`.
- ✅ `GET /impact?range=week|month|all` (default `all`; week=last 7 days, month=last 30; bad → 400) →
  ```json
  {"range": "week",
   "saved":   {"count": 3, "kg": 1.2, "money": 8.5, "co2e_kg": 2.1},   // used + donated
   "wasted":  {"count": 1, "kg": 0.5, "money": 3.5, "co2e_kg": 2.25},  // thrown_out
   "used":    {"count": 1, "kg": …, "money": …, "co2e_kg": …},
   "donated": {"count": 2, "kg": …, "money": …, "co2e_kg": …},
   "waste_rate": 0.25,
   "waste_reasons": [{"reason": "forgot", "count": 1, "kg": 0.5, "money": 3.5, "co2e_kg": 2.25, "share": 1.0}, …],
   "previous": {"saved": {…}, "wasted": {…}, "used": {…}, "donated": {…}, "waste_rate": 0.0},
   "weekly": [{"week": "2026-10-05", "saved": 3, "wasted": 1}],
   "last_6_weeks": [{"week": "2026-09-07", "used": 0, "donated": 0, "saved": 0, "wasted": 0}, …]}
  ```
  - `saved` = `used`+`donated`, so `saved.x == used.x + donated.x` (up to 2 dp rounding).
    `waste_rate = wasted.count / (saved.count + wasted.count)` (0 when empty).
  - `waste_reasons`: always all 4 reasons (`expired, didnt_like, forgot, other`), zero-filled, sorted by
    `count` desc (ties keep that enum order); `share` = count / `wasted.count` (0 when none). Same range.
  - `previous`: the same totals for the window of equal length just before the current one (week: 14..7
    days ago; month: 60..30 days ago); `null` for `range=all`. Clients compute deltas.
  - `weekly`: range-filtered weekly counts, only weeks with data (unchanged; zero data → `[]`).
  - `last_6_weeks`: **always 6 entries**, oldest first, ending with the current week, gap-filled with
    zeros, independent of `range`. Buckets are `time_bucket('1 week')` (Monday 00:00 UTC); `week` is the
    bucket start date. Counts only.
    Week dates (here and in `weekly`) are computed in UTC whatever the DB session time zone (BE-10).
  - Computed from `food_events` (`event_type='remove'`) on every request, never stored totals; money/kg/
    co2e rounded to 2 dp. A fixed number of queries, independent of data size (5 for `week`/`month`,
    including the window-start lookup; 4 for `all`). Zero data → zeros.
- ✅ `GET /tips` → `200 {tips: [{code, message}]}`. Based on the last 90 days of `thrown_out` events
  (top reason, most-wasted item, most-wasted category) plus items expiring within 2 days. Zero data
  → one `getting_started` tip.

## Gemini usage logging
Every Gemini call (`parse_text`, `detect`, `recipes`, `shelf_life`) writes one INFO line on the
logger `app.gemini.usage` (its own stderr handler, so it shows in `docker compose logs api`):

    gemini_usage model=<model> purpose=<purpose> input_tokens=<n|null> output_tokens=<n|null> total_tokens=<n|null> latency_ms=<n> status=ok|error

A response that is not usable JSON (unparseable, a scalar such as `null`/string/number/bool, or an
object whose `items`/`candidates`/`recipes`/`days` value is not a list) counts as a failed call
(`status=error`, one line) and the endpoint returns `502 upstream_unavailable` (BE-13); for the shelf-life
estimate on `POST /items` it falls back to the default table.
Tokens come from the response's `usage_metadata` (`output_tokens` includes thinking tokens); they are
`null` when it is missing, and on `status=error` when the call failed. Prompts, response text, user
data and the API key are never logged. Cost report:

    docker compose logs api | python scripts/gemini_cost.py
    python scripts/gemini_cost.py api.log --price gemini-2.5-flash=0.30,2.50 --default-price 0.30,2.50

`scripts/gemini_cost.py` prints calls, errors, tokens and USD per model + purpose and a total. Its
price table (USD per 1M input/output tokens) is a placeholder dated 2026-10-10 and must be verified
against Google's pricing page; override per model with `--price MODEL=IN,OUT`.
