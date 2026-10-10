# Backend QA

Suite: `backend/tests/` (run from `backend/`: `.venv/bin/pytest --cov=app --cov-report=term-missing`).
Schema is built by running the real Alembic migration against `TEST_DATABASE_URL` (`fwr_test`); tables are
truncated before each test. A Postgres advisory lock serialises whole pytest sessions (concurrent runs share
`fwr_test` and one run's `DROP SCHEMA` broke the other - observed "could not open relation with OID").
Gemini / ML / Open Food Facts are stubbed; a fixture fails any test that attempts a real `requests` call.

## What was tested
- Auth: signup/login, duplicates, bad input, wrong password, 401 on every protected route, bad token.
- Items: create (add event per item, atomic on a bad row), list (sort, storage filter, scoping, removed hidden), PATCH (expiry -> `user`, 400/403/404, removed -> 404).
- Expiry: default / user / gemini (stubbed) / gemini-failure fallback, category ordering.
- Removal (core): used / donated / thrown_out x 4 reasons; soft-delete fields; `removed_after_expiry` true+false; exactly one `remove` event with outcome, category, quantity, price, co2e > 0; every 400 (missing/invalid reason, reason on used/donated, recipient on non-donated, bad outcome, unknown recipient) leaves no event and item untouched; 409 keeps one event; 401/403/404; donated fulfils an open listing (+ recipient, fulfilled_at); used does not.
- Schema: `food_events` hypertable, extensions, CHECK constraints on `items` and `food_events` reject mismatches.
- Impact: hand-computed fixture (events backdated 0 / 14 / 60 days) for week / month / all, weekly buckets, zero data, per-user scoping, `add` events ignored, end-to-end through the API.
- Tips: zero data, forgot pattern, per-user scoping.
- parse-text, from-photo (ML -> `yolo`, Gemini fallback -> `gemini`, ML-down fallback), from-receipt, barcode, recipes: success shapes, bad input, no-key -> 502 `upstream_unavailable`, upstream failure -> 502.
- Share (`POST /share`) in Wave 1; the rest of Social is below.

## Wave 3 (social) - `tests/test_social.py`, 57 tests
Fixture world: Alice; Bob (accepted friend); Carol (pending request to Alice only); Dave (stranger, owns group H); Erin (member of Alice's group G, not a friend).
- Visibility matrix for `GET /share`, `GET /requests`, `GET /friends`, `/groups`, `/groups/:id`, `/groups/:id/pantry`: friends see friend-scoped things only, group members see group-scoped things only (a friend outside the group does not, a group member who is not a friend does not), pending-only and strangers see nothing, own listings are excluded from the board; unfriending / leaving revokes at once.
- Authorization on every mutator: accept (only the target), unfriend either side (204; 404 when no relation), group join/leave, `POST /items` with a foreign `group_id` (403, all-or-nothing), remove of group items by members only (outsiders and ex-members blocked), share to a foreign group (403), cancel/claim listings and cancel/fulfil requests (invisible -> 404, visible-but-not-yours -> 403, own request fulfil -> 403, closed -> 409).
- Lifecycles: friends, groups (codes, normalisation, counts, owner transfer on leave, leaver's listings/requests cancelled), group pantry removal (one `remove` event with `user_id` = remover and `group_id`; all Wave 1 reason rules still enforced), share end to end (claim -> donated removal -> fulfilled + recipient, default recipient = claimer, impact credited to owner), requests (length 0/280/281, `source` me/friend/group, newest first).
- Migration 0002 round trip (head -> 0001 -> head, tables identical).
- Not tested: concurrent claim races (no threaded test), pagination (none in the contract).

## Wave 3 final run
158 tests, 158 passed (100 Wave 1 + 57 social + 1 migration step). Coverage 94% (threshold 80%); all social modules 95-100%.

## Final run
100 tests, 100 passed. Coverage 92% (threshold 80%). Added in the final pass: 413 `payload_too_large` (photo and receipt), `already_shared` / `already_removed` codes on `POST /share`, ML HTTP error -> Gemini fallback (and 502 when both fail), barcode 400 shape, recipes `{recipes: []}` with no active items, and a migration round trip (base -> head -> base -> head, hypertable intact).
Uncovered: mostly Gemini SDK internals (`_generate`, needs a key) and defensive branches.

## Bugs
| ID | Severity | Summary | Repro | Status |
|---|---|---|---|---|
| BE-1 | high | `GET /impact` 500 for a user with no removals when other users' events span several Timescale chunks | `pytest tests/test_impact.py::test_scoped_to_user_and_ignores_add_events` | fixed, verified |

No Wave 3 bugs found. Observation (not a bug, decided by the orchestrator): group-addressed endpoints return 403 for a non-member and 404 for an unknown group, so a group UUID's existence is distinguishable; ids are random UUIDs so this is negligible.

## 2026-10-10 - api container runs migrations on start (branch fix/api-migrate-on-start)
Files checked: `backend/entrypoint.sh` (retries `flask --app wsgi db upgrade` up to 10 times, 3 s apart, exits 1 if all fail, then `exec gunicorn`), `backend/Dockerfile` (`CMD ["/app/entrypoint.sh"]`), `docs/SETUP.md`.

| # | Check | Result |
|---|---|---|
| 1 | `docker compose down -v && docker compose up -d --build`, no host migration; logs show `Running upgrade -> 0001_initial` and `0001 -> 0002_social`, then gunicorn; `POST /auth/signup` | 201, pass |
| 2a | `docker compose restart api`: no `Running upgrade` lines (alembic context lines only), gunicorn back up; new signup | 201, pass |
| 2b | `docker compose down && up -d` (volume kept): upgrade a no-op, new signup | 201, pass |
| 3 | `docker compose run --rm -T -e DATABASE_URL=postgresql+psycopg://x:y@nowhere:5432/z api`: 9 retry messages, then `db upgrade failed after 10 attempts`, never reached gunicorn | exit code 1 after about 30 s, pass |
| 4 | `pytest -q --cov=app` against `fwr_test` on localhost:5433 | 158 passed, coverage 94%, pass |
| 5 | `docs/SETUP.md` describes the entrypoint, idempotency, the host-venv manual command and the test DB step | matches, pass |

Notes (no bugs): the builder's stack was up when QA ran `down -v`, and a concurrent `restart` by the builder overlapped with QA's first run; results were re-confirmed afterwards. SETUP.md does not mention the 10 x 3 s retry window (about 30 s before the container gives up); low-value doc nit only.

Bugs: none new.

## 2026-10-10 - food_group + recipe macros (branch feat/food-group-and-macros)
Files: `backend/tests/test_food_group.py` (new, 58 cases), `backend/tests/test_macros.py` (new, 28 cases incl. 19 parametrised bad-macros), `test_ai_endpoints.py::test_receipt_success` loosened (receipt candidates now also carry `food_group`).

**Result: PASS.** `pytest -q --cov=app` against `fwr_test` (localhost:5433): **243 passed, 1 skipped, 0 failed; coverage 95%** (threshold 80%). Previous total: 158 (158 + 86 new = 244 collected).
The skip is `test_group_by_nulls_last_when_db_has_null_expiry`: `items.predicted_expiry` is NOT NULL, so "nulls last" cannot be reached through the schema. The test turns itself on if the column ever becomes nullable.

| Area | Checked |
|---|---|
| Migration 0003 | Downgrade to 0002, insert 17 items (every category, 4 fruit and 4 vegetable produce names), upgrade: all map as specified (meat/seafood/eggs → protein, bakery → grains, pantry_dry → pantry, dairy/leftovers/frozen/other same, produce → fruit/veggies). Column nullable, CHECK rejects `bogus`, downgrade drops the column and keeps the rows, re-upgrade works, single alembic head |
| POST/PATCH | All 9 enum values stored; 6 invalid values (`bogus`, `""`, wrong case, int, list, bool) → 400 `validation_error` with nothing written (whole batch); null/omitted → derived (13 category/name cases); explicit value beats derivation; PATCH valid, invalid → 400, other user → 403; present on POST, list, remove and `include_removed` responses |
| Grouping | Enum section order, expiry ascending inside a section, empty sections omitted, empty → `{"sections": []}`, unknown `group_by` → 400, 401 without a token, no `group_by` → unchanged `{items}`, other users' / removed / group-pantry items never appear, composes with `storage` (and a bad `storage` is still 400) |
| Candidates | parse-text, from-photo (ML and Gemini fallback), from-receipt, barcode all carry a valid `food_group`; invalid Gemini values (`bogus`, `""`, null, 7, list, wrong case) fall back to the heuristic; a candidate posted back to `POST /items` round-trips |
| Macros | Gemini stubbed at `gemini._generate` so the real code runs. Valid → rounded `macros` + `macros_estimated: true` (zeros accepted); missing → null; 19 invalid shapes (non-dict, missing key, string, bool, null, list, negative, huge, NaN, inf) → null with the recipe kept; mixed lists independent; non-dict entries skipped; never a 500 |

Assumptions the tests make about an ambiguous spec: section order = enum order; macros range is [0, 3000] kcal and [0, 300] g (from the implementation: tests use values far outside those); `macros_estimated` is not asserted when macros is null.

### Live Gemini, once each (model per `.env`; key never printed)
Run against the rebuilt container API (migration 0003 applied on start, `ML_SERVICE_URL` empty), fresh test user, 3 calls total. Photo: Wikimedia Commons `Fruit_bowl.jpg` (960x867 JPEG, 187 KB, fetched via Special:FilePath; licence not checked, used only for this test, not committed).

| Call | HTTP | Latency | Schema-valid | Output excerpt |
|---|---|---|---|---|
| `POST /items/parse-text` "2 cartons of milk, a dozen eggs and some spinach" | 200 | 6.89 s | yes: 3 candidates, each with a valid `food_group` | milk 2 carton → dairy; eggs 12 → protein; spinach 1 bunch → veggies |
| `POST /recipes/suggest` (4 items expiring in 1-2 days, `max_results=2`) | 200 | 6.27 s | yes: 2 recipes, `macros` present and in range, `macros_estimated: true` | "Pan-Seared Chicken and Garlic Spinach" 295 kcal / 36.5 P / 3.2 C / 14.0 F; "Baked Spinach and Egg Frittata" 190 kcal / 14.0 P / 4.5 C / 12.5 F |
| `POST /items/from-photo` (Gemini fallback, `source: "gemini"`) | 200 | 4.78 s | yes: 6 candidates, all `food_group: fruit`, freshness `fresh` | pomegranate 0.98, red apple 0.95, green apple 0.95, pears 0.94, green bananas 0.92, grapefruit 0.88 |

Token usage: the backend neither logs nor returns it (`resp.usage_metadata` is discarded in `gemini._generate`), so these are **estimates**, not measurements. Rough guess: parse-text ~150 in / ~150 out, recipes ~450 in / ~700 out, photo ~1,300 in (image) / ~450 out. At public Gemini Flash list pricing of about $0.30 per 1M input and $2.50 per 1M output tokens (the configured model's exact price was not checked; reasoning tokens, if any, would add to this): **about $0.0004, $0.002 and $0.0015 per call**, roughly $0.004 for all three. Treat as order-of-magnitude.

### Bugs / observations
| ID | Severity | Summary | Repro | Status |
|---|---|---|---|---|
| BE-2 | low | Receipt candidates only have a name, so `food_group` comes from the name alone: `Milk` and `Eggs` receipt lines get `other` (an item posted as category `dairy` gets `dairy`). Valid but not useful for grouping | `ml.ocr` stub returning `{"name":"Milk"}` → `POST /items/from-receipt` → `food_group: "other"` | open, builder's call (name keyword table, or accept) |
| BE-3 | info | No Gemini token usage is logged, so cost cannot be measured in production | see above | open, optional |
| - | info | `predicted_expiry` is NOT NULL, so the spec's "nulls last" in `group_by` can never trigger | skipped test | spec note |

Env note: `docker compose up -d` brought up `db` (created `fwr_test`) and `--build api` for the live run; both are left running.
