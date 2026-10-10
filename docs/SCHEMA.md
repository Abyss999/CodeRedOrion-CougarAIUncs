# Schema

PostgreSQL + TimescaleDB, one database. Relational tables for state; the `food_events`
**hypertable** is the append-only log the Impact Dashboard is computed from.
Status: **planned** — the backend builder creates these as Alembic migrations in Wave 1.

## Relational tables
### users
`id uuid pk`, `email citext unique`, `password_hash`, `display_name`, `created_at`

### items
| Column | Type | Notes |
|---|---|---|
| id | uuid pk | |
| owner_id | uuid → users | |
| group_id | uuid → groups, null | set when the item lives in a group pantry |
| name | text | |
| category | text | spoilage group: `produce_leafy`, `produce_hardy`, `dairy`, `meat`, `seafood`, `bakery`, `eggs`, `leftovers`, `pantry_dry`, `frozen`, `other` (final list in `DECISIONS.md`) |
| storage | text | `fridge` \| `pantry` \| `freezer` |
| quantity, unit | numeric, text | |
| est_weight_kg | numeric, null | for CO₂; estimated from quantity/unit when absent |
| est_price | numeric(10,2), null | |
| source | text | `photo` \| `single_photo` \| `text` \| `barcode` \| `receipt` \| `manual` |
| added_at | timestamptz | |
| predicted_expiry | date | |
| expiry_source | text | `default` \| `gemini` \| `user` |
| **removed_at** | timestamptz, null | soft delete — null means "still in the fridge" |
| **outcome** | text, null | `used` \| `donated` \| `thrown_out` |
| **waste_reason** | text, null | `expired` \| `didnt_like` \| `forgot` \| `other` |
| removed_after_expiry | bool, null | feedback signal for expiry prediction |

Constraints:
```sql
CHECK ((removed_at IS NULL) = (outcome IS NULL))
CHECK ((outcome = 'thrown_out') = (waste_reason IS NOT NULL))   -- reason required iff thrown out
```
Index: `(owner_id, removed_at, predicted_expiry)`.

### Social
- `friendships(user_id, friend_id, status pending|accepted, created_at)` — pk `(user_id, friend_id)`
- `groups(id, name, created_by, created_at)`, `group_members(group_id, user_id, role)`
- `share_listings(id, item_id → items, owner_id, group_id null, status open|fulfilled|cancelled, recipient_id null, created_at, fulfilled_at)`
- `requests(id, author_id, group_id null, text, status open|fulfilled, created_at)`

## Event model (TimescaleDB)
```sql
CREATE TABLE food_events (
  time          timestamptz NOT NULL DEFAULT now(),
  user_id       uuid NOT NULL,
  item_id       uuid NOT NULL,
  group_id      uuid,
  event_type    text NOT NULL,        -- add | share | expiry_warning | remove
  category      text NOT NULL,
  quantity      numeric,
  est_weight_kg numeric,
  est_price     numeric(10,2),
  outcome       text,                 -- remove only: used | donated | thrown_out
  waste_reason  text,                 -- remove + thrown_out only
  co2e_kg       numeric               -- remove only: est_weight_kg × category factor
);
SELECT create_hypertable('food_events', by_range('time'));
CREATE INDEX ON food_events (user_id, time DESC);
```
- Written **in the same transaction** as the state change it records.
- Events are never updated or deleted.
- `co2e_kg` uses per-category factors (source in `DECISIONS.md`). For `used`/`donated` it is
  CO₂e **avoided**; for `thrown_out` it is CO₂e **wasted**.

## Impact queries (sketch)
```sql
SELECT time_bucket('1 week', time) AS week,
       count(*) FILTER (WHERE outcome IN ('used','donated'))  AS saved,
       count(*) FILTER (WHERE outcome = 'thrown_out')         AS wasted,
       sum(est_price) FILTER (WHERE outcome IN ('used','donated')) AS money_saved,
       sum(co2e_kg)   FILTER (WHERE outcome IN ('used','donated')) AS co2e_avoided
FROM food_events
WHERE user_id = :uid AND event_type = 'remove'
GROUP BY week ORDER BY week;
```
waste_rate = wasted / (saved + wasted).
