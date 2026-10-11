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

## 2026-10-10 - food-group follow-ups (BE-2, BE-3, PATCH semantics) - branch fix/food-group-followups

**Result: PASS.** Full suite from `backend/`: `pytest -q --cov=app` = **335 passed, 1 skipped, coverage 96%** (`gemini.py` 99%, `food_group.py` 100%). Run against `fwr_test` on localhost:5433. No live Gemini calls (SDK `genai.Client` and `gemini._generate` stubbed; `requests` blocked).

| Area | Tests | Checked |
|---|---|---|
| PATCH (`test_food_group.py`) | 11 | category only -> re-derived (also over an earlier manual group, and produce_* uses the name); category + food_group -> explicit wins; invalid group with category -> 400, nothing written; invalid category -> 400; food_group only -> kept, category untouched, later unrelated PATCH keeps it; same category re-derives (resets manual choice, as documented); name only -> group unchanged; `food_group: null` never 500 (200 or 400, alone and with category) |
| BE-2 (`test_food_group_names.py`) | 80+ | 39-row receipt table (`GV WHL MILK GAL`, `KS ORG EGGS`, `CHKN BRST`, `WHT BRD`, `ORG BANANAS`, `BABY SPINACH`, `FRZN PEAS`, many lines from ml/eval/fixtures/receipts); case-insensitive; empty/None/unknown -> other; substring false positives (BUTTERNUT SQUASH, PEANUT BUTTER, EGGPLANT, MILKY WAY, JASMINE RICE, PRICE, HAMMER, CORNER, PEASANT); PINEAPPLE -> fruit; end-to-end `POST /items/from-receipt` with OCR stubbed: Milk -> dairy, Eggs -> protein |
| BE-3 (`test_gemini_usage.py`) | 19 | exactly one INFO record per call on `app.gemini.usage`, with model/purpose/input/output/total tokens/latency_ms/status; each of the 4 helpers logs once with a distinct purpose; record never contains prompt text, a sentinel user string, response text or the fake API key (message and the whole LogRecord); missing/None/partial `usage_metadata` -> `null` fields, no exception; SDK exception -> `status=error`, no traceback attached; bad JSON -> `status=error` but tokens kept (call was billed); unconfigured -> no log; a failing logger never breaks the call; route-level `/items/parse-text` logs once. `scripts/gemini_cost.py` (subprocess): totals, per-model cost math, `--price` / `--default-price`, default table (gemini-3.8-flash 0.75/3.75 per 1M, 1M+1M = $4.50), file arg, empty input, round trip of the real emitted line |

Decisions / findings (all behaviours match docs/API.md):
- CREAMER / COFFEE CREAMER -> dairy; ICE CREAM -> frozen; COCONUT MILK and ALMOND MILK -> dairy; BUTTERNUT SQUASH -> veggies; PEANUT BUTTER -> pantry; APPLE JUICE / ORANGE JUICE -> pantry. Tests assert only the unambiguous ones (creamer, ice cream and juices are asserted only to be a valid group).
- PATCH `name` only keeps the group (documented); `food_group: null` currently returns 400 validation_error (not documented in API.md; tests accept 200 or 400, never 500).
- Existing tests that stubbed `gemini._generate` with `lambda contents, hint:` broke when the builder added the `purpose` kwarg; stubs in `test_food_group.py` updated to accept `*a, **k` (test_macros already did). Any other caller stubbing `_generate` needs the same.
- The usage logger sets `propagate=False`, so pytest `caplog` cannot see it; tests attach their own handler. Anyone writing log assertions must do the same.

### Bug status
| ID | Severity | Summary | Status |
|---|---|---|---|
| BE-2 | low | Receipt `Milk`/`Eggs` got `other` | **fixed, verified** (keyword tables + abbreviations; Milk -> dairy, Eggs -> protein end to end) |
| BE-3 | info | No Gemini token usage logged | **fixed, verified** (one leak-free INFO line per call; `scripts/gemini_cost.py` verified) |
| BE-4 | info | `food_group: null` on PATCH undocumented in docs/API.md (returns 400, never 500) | open, doc request to builder |
| BE-5 | info | Reported cosmetic oddities: POPCORN -> other, PICO DE GALLO -> other, COCOA BUTTER -> dairy, EGG NOODLES -> protein, COCONUT WATER -> fruit | open, optional |

## 2026-10-10 - freshness normaliser (PR A1, branch feat/semi-fresh-contract)

**Result: PASS.** Full suite from `backend/`: `pytest -q --cov=app` = **380 passed, 1 skipped, coverage 96%**, against `fwr_test` on localhost:5433 (no train.py or xcodebuild running). New file `tests/test_freshness_contract.py`; ML and Gemini stubbed, `gemini._generate` stubs take `*a, **k`.

| Checked | Result |
|---|---|
| `fresh`, `semi_fresh`, `spoiled` pass through, no warning | ok |
| Variants: `Semi-Fresh`, `semi fresh`, `SEMIFRESH`, padded, `use soon`, `Rotten`, `stale`, `SPOILT`, `bad`, case/space variants of valid values | ok, no warning |
| Unknown (`??`, empty, `mouldy`, `overripe`, None, int, float, bool, list, dict) -> `fresh` with exactly one WARNING (`freshness_fallback`, source, raw cut to 40 chars) | ok |
| Warning has no user data: item names never appear, a 500-char raw is truncated | ok |
| `/items/from-photo`, ML path: semi_fresh passes through, variants map, junk/None/missing -> fresh with one warning each, mixed list warns once per bad candidate, source=yolo | ok |
| `/items/from-photo`, Gemini fallback: `Semi-Fresh` -> semi_fresh, list and `{"candidates": [...]}` shapes, unknown -> fresh, source=gemini; ML down -> Gemini still normalised | ok |
| Gemini detect prompt lists `fresh|semi_fresh|spoiled` | ok |
| `/items/parse-text`: no freshness key and no warning when Gemini sends none; a stray freshness is normalised | ok |
| Freshness is not stored on items; unauthenticated from-photo is 401 | ok |

### Findings
| ID | Severity | Summary | Status |
|---|---|---|---|
| BE-6 | low | `_FRESHNESS_ALIASES` maps `ripe` -> `semi_fresh`, but `ml/yolo/taxonomy.FRESH_WORDS` treats `ripe` as fresh (ML-28). Also `overripe`, `mouldy`/`moldy`, `decayed`, `rotting`, `damaged` (all in taxonomy's spoiled list) fall through to `fresh` with a warning: the unsafe direction for free-text Gemini output. Impact is small since Gemini is told the enum, but the two tables should agree. Suggest dropping the `ripe` alias (or mapping it the same everywhere) and sending the taxonomy spoiled words to `spoiled`. | open |

Contract grep: `docs/API.md` and the Gemini prompt are 3-value. No two-value enum left in `backend/app` or `ml/serve`. See ML-29 for stale wording elsewhere.

### 2026-10-10 - re-verification after BE-6 fix (commit 5e15b00)

**Result: PASS.** `pytest -q --cov=app` from `backend/` = **394 passed, 1 skipped, coverage 96%** (`fwr_test`, localhost:5433; no train.py/xcodebuild running).

- BE-6 verified fixed. New and extended tests in `tests/test_freshness_contract.py`: `moldy`, `Mouldy`, `overripe`, `decayed`, `rotting`, `damaged`, `DEFECTIVE` -> spoiled and `half-fresh` -> semi_fresh with no warning; `ripe`, `Ripe`, `unripe`, `good`, `Over-Ripe` -> fresh with exactly one warning; a Gemini from-photo run with `moldy`/`overripe`/`decayed` -> spoiled and `ripe` -> fresh with a single warning; and `test_backend_word_lists_equal_taxonomy`, which loads `ml/yolo/taxonomy.py` by path and checks the backend semi aliases equal `SEMI_WORDS` plus `use soon`, the spoiled aliases equal `SPOILED_WORDS` (the exact `spoiled` value is handled separately), no `FRESH_WORDS` entry is aliased to another class, and the `FRESHNESS` tuples match.
- Note: `Over-Ripe` (hyphenated) is not the taxonomy word `overripe`, so it stays fresh + warning in both backend and serve. They agree.
- No new backend bugs.

## 2026-10-10 - receipt abbreviations (branch feat/receipt-abbrevs)

**Result: PASS.** Backend `pytest -q --cov=app` = **523 passed, 1 skipped, coverage 96%** (`fwr_test`, localhost:5433; no train.py/xcodebuild running). Pipeline `pytest pipeline/tests -o python_files="test_*.py qa_*.py"` = 164 passed, 2 skipped, including the no-duplicate-keys / shared-keys-agree test. New file `tests/test_food_group_abbrevs.py`.

| Checked | Result |
|---|---|
| 44 receipt-style names using the new abbreviations -> expected group (`GV SKM MLK GAL` dairy, `CHKN BRST BNLS` protein, `ORG BROC CROWNS` veggies, `STRAWB 1LB` fruit, `OJ NFC 52OZ` pantry, `RCE JASMINE` grains, `SLMN FILLET` protein, `PNAPL CHUNKS` fruit, ...) | ok |
| All 46 listed keys present in `ABBREVIATIONS`; `gr pot pine ban straw` absent; keys lowercase alpha | ok |
| #22's 39-row table (`test_food_group_names.py`) unchanged | ok |
| No key shared with pipeline `abbreviations.json` with a different expansion | ok |
| `TOM ROMA` -> veggies (tomato); `TOMMY'S`, `TOMMYS`, `ATOM`, `CUSTOM` do not hit (whole-token; `TOMMY'S` tokenises to `tommy`,`s`) | ok |
| `CUC` inside `CUCINA`, `ACUC` no hit; `CUCINA PASTA SAUCE` -> pantry | ok |
| `GRP RED` fruit; `GROUP PURCHASE FEE`, `GROUPER` not fruit | ok |
| `BREADED CHICKEN`, `BRED CHICKEN` -> protein (protein is checked before grains); `BRED` alone -> grains | ok |
| Priority: `STRAWB YOGURT`, `PEPR JACK CHEESE` dairy; `APPL JCE`, `ORNG JCE` pantry; `TOM TURKEY` protein | ok |
| Pipeline `clean()` for `GV WHL MILK GAL` (dairy), `KS ORG EGGS` (protein), `BANANAS` (fruit) unchanged | ok |

### Findings
| ID | Severity | Summary | Status |
|---|---|---|---|
| BE-7 | info | Backend and pipeline disagree on juice: backend `OJ NFC 52OZ` / `APPL JCE` -> pantry, pipeline receipt output -> `other` (class `juice`, documented in PIPELINE.md). Same name, two groups depending on entry point. | open, optional |

## 2026-10-10 - items wave 2 (branch feat/items-wave2)

**Result: FAIL (1 open bug, BE-8, low severity; everything else passes).** Run from `backend/` against `fwr_test` (localhost:5433, the worktree's compose DB; `fwr_test` was missing and was created): `pytest -q --cov=app` = **661 passed, 1 skipped, 1 xfailed (BE-8), coverage 97%** (before my fix of one stale test: 660 passed + 1 failed). No live Gemini, no train.py or xcodebuild of mine running.

New files (all in `backend/tests/`): `test_wave2_migration_0004.py`, `test_wave2_freshness.py`, `test_wave2_item_share.py`, `test_wave2_expiry_roundtrip.py`, `test_wave2_restore.py`, `test_wave2_account_delete.py` (139 tests). Edited: `test_freshness_contract.py::test_freshness_not_stored_on_item`, which asserted the pre-0004 contract (freshness not stored); renamed `test_freshness_stored_on_item_since_0004` and inverted.

| Area | Checked | Result |
|---|---|---|
| Migration 0004 | single head; upgrade from 0003 with existing rows (freshness/confidence/checked_at null); downgrade drops the columns and keeps 0003 data; CHECK rejects bad freshness (insert and update), freshness and stamp must travel together, confidence 0..1; `groups.created_by` nullable, downgrade repairs orphan groups | ok |
| Freshness | each value on create; variants normalised (`Semi-Fresh`, `rotten`, `use soon`); unknown string -> `fresh` + WARNING (per API.md); non-string -> 400 and nothing written; PATCH set / change / clear (clears stamp), other edits keep the stamp; other user's item 403; no effect on expiry; present in list, `group_by` sections and remove response | ok |
| Confidence | stored 0..1, out of range / string / bool / list -> 400 and nothing written; not PATCHable (400); `Infinity` rejected | ok; `NaN` -> 500, see BE-8 |
| `share` object | null when unshared (create, list, patch); open; claimed gives `{id, name}`; cancelled not reported, relist shows the new open one; fulfilled after donation; name follows display_name; absent from other users' lists, Food Pantry entries and group pantry items | ok |
| N+1 | SQLAlchemy `before_cursor_execute` counting: `GET /items` has the same statement count for 1 and 20 shared/claimed items; `group_by` with 20 items <= 8 statements | ok |
| Expiry round trip | `expiry_source` default/gemini/ml kept when posted with an expiry; omitted -> user; invalid -> 400; PATCH with a changed expiry -> user, same expiry or other fields keep the source; `candidates.normalize` output posts back intact | ok |
| Restore | within window (used / donated / both thrown_out reasons): item active, remove event gone, `GET /impact` (all/week/month) equals the pre-removal numbers exactly; neighbouring history untouched; 9 min ok, 11 min -> 409 `restore_window_expired` (time patched in SQL on item and event); not removed -> 409 `not_removed`; double restore 409; other user 403/404; unknown / bad id 404; unauth 401; remove -> restore -> remove leaves exactly one remove event, 3 cycles leave none; atomic (forced failure rolls back the event delete) | ok |
| Restore + share | donated shared item: listing back to `open`, `fulfilled_at` and `recipient_id` cleared, `claimed_by` kept, item `share.status` open, visible to friends again; explicit `recipient_id` cleared; non-donated removal leaves listing alone; cancelled listing not resurrected; group member may restore a group item, outsider may not | ok |
| `DELETE /auth/me` | 204; token -> 401 (also login and a second delete); email reusable with an empty account; items, listings (own and on her items), friendships (both directions, pending too), memberships, requests gone; nothing references her id in any table; events kept (same count and values) with `user_id` = nil-UUID tombstone, remove aggregates unchanged, a new user does not inherit them; others' impact/events/items/requests unchanged; listings she claimed reopen and requests she fulfilled reopen; group ownership passes to the oldest remaining member, solo group becomes an empty orphan with `created_by` null and does not 500; no trace of her in others' `/share`, `/requests`, `/friends`, `/groups`; atomic on failure | ok |

### Findings
| ID | Severity | Summary | Status |
|---|---|---|---|
| BE-8 | low | `POST /items` with `"confidence": NaN` (Python's JSON parser accepts the bare token) passes `_check_confidence` (`NaN < 0` and `NaN > 1` are both false), then Postgres rejects it on `ck_items_confidence` and the API returns 500 instead of 400. `Infinity` is rejected correctly. Fix: reject non-finite numbers (`math.isfinite`) in `parse_number` or `_check_confidence`. The same hole probably exists for `est_price` / `quantity` via `parse_number`. Test: `test_confidence_nan_inf_rejected[NaN]` (xfail strict, so it fails loudly once fixed). | open |

Notes (not bugs): an empty-string `freshness` is normalised to `fresh` with a stamp, which follows API.md ("unknown strings become fresh") but means a blank client value reads as "assessed fresh"; consider treating `""` like null. `restore` deletes the remove event, so `food_events` is no longer strictly append-only (documented in SCHEMA.md).

### 2026-10-10 - items wave 2, final verdict

**Result: PASS (one open low bug, BE-9, xfail-tracked).** Full `pytest -q --cov=app` from `backend/` on `fwr_test` (localhost:5433) = **680 passed, 1 skipped, 3 xfailed, coverage 97%**. Run note: an iOS xcodebuild was still alive (0% CPU, idle) when the run started; the suite only needs the DB and memory was fine.

- **BE-8 fixed and verified.** `parse_number` now rejects NaN, Infinity and -Infinity with 400. The xfail is now passing tests: `NaN`, `Infinity` and `-Infinity` on create for `confidence`, `est_price`, `quantity` and `est_weight_kg`, and on PATCH for `quantity`, `est_price` and `est_weight_kg`. Each case checks nothing was written (create) or the value is unchanged (PATCH).
- **BE-9 (low, open):** a finite `est_price` beyond numeric(10,2) (1e8, 1e12, 1e300) overflows in Postgres and returns 500 instead of 400. Repro: `POST /items {"items":[{"name":"x","est_price":1e8}]}`. `test_huge_est_price_is_400_not_500` is xfail strict (3 cases), so it fails loudly once fixed. The same may apply to `est_weight_kg` and `quantity`, which are unbounded `numeric`, so likely only extreme exponents matter there; not tested.

## 2026-10-10 - receipt candidates + Gemini category guide + retry (branch feat/receipt-gemini-link, rebased onto main with PR #50)

**Result: PASS.** `pytest -q --cov=app` from `backend/` = **757 passed, 1 skipped, 3 xfailed, coverage 97%** (`fwr_test`; the 3 xfails are the existing BE-9 `test_huge_est_price_is_400_not_500` cases). New files: `tests/test_receipt_candidates.py` (57 tests), `tests/test_gemini_retry.py` (~30). Gemini and the ML service are stubbed; no network.

| Checked | Result |
|---|---|
| `from-receipt` shape `{candidates,total,categorized_by}`; full item fields + `price == est_price` + `receipt_text`; candidate (as returned, with extras) posts to `POST /items {items:[...]}` -> 201 (also under PR #50 validation) | ok |
| Gemini stub: `display_name` as name, category/food_group/storage used, invalid enums fall back, fewer entries than lines -> one candidate per line, non-dict entries, name capped at 120, `categorized_by: gemini` | ok |
| `UpstreamError` -> heuristic + 200; not configured / no lines -> no Gemini call | ok |
| Heuristic categories (milk, chicken, salmon, eggs, bananas, frozen peas, bread, `XQZT 99`) all in CATEGORIES | ok |
| `_money`/`_qty`: `$3.48`, `1,29`, `1,299.50` -> 1299.5, garbage -> null, NaN/inf -> null (qty 1.0), valid JSON emitted; total variants | ok |
| Odd ML lines (non-dict, nameless, bad types) skipped, no 500; ML down -> 502 | ok |
| `CATEGORY_GUIDE` in parse_text, detect_from_image and categorize_receipt_lines prompts; schema enums equal CATEGORIES / FOOD_GROUPS / fridge,pantry,freezer and is passed | ok |
| Retry: 503/429/504 codes and UNAVAILABLE/RESOURCE_EXHAUSTED/DEADLINE_EXCEEDED text retried once (sleep patched); second failure -> UpstreamError; 400/500/ValueError not retried; exactly one `gemini_usage` line per call (ok after retry, error otherwise, incl. bad JSON after retry) | ok |

### Findings
No new bugs (BE-10 unused). Observation: a receipt price above numeric(10,2) (e.g. `"999999999"`) is passed through as `est_price`, so posting it back hits the open BE-9 500 path.

## 2026-10-10 - PR #54 receipt-gemini-link (backend QA)

_Independent backend QA (food-main-mac). Supersedes the PASS in the section above: it found BE-11..BE-13, which the author-side run did not cover. Tests live in `tests/test_receipt_candidates_qa.py`, alongside the author's `tests/test_receipt_candidates.py`._

**Result: PASS pending the full-suite run, with BE-13 tracked (low, xfail strict, resolves when #54 rebases onto PR 2).** BE-11 and BE-12 are fixed on #54 (ported fix, commit 7044932) and re-verified; see the re-verification below. First run (before the fix): `pytest -q tests/test_receipt_candidates_qa.py` = 85 passed, 14 xfailed (strict: BE-11 x6, BE-12 x4, BE-13 x4). The full suite has not been run yet (shared DB, possible xcodebuild). Gemini is never called: stubbed at `google.genai.Client` (so the real `_generate` retry/logging and the SDK's `GenerateContentConfig` validation of the receipt enum schema run) or at `gemini.categorize_receipt_lines`; OCR stubbed at `ml.ocr`; `requests.get/post` raise.

New file: `backend/tests/test_receipt_candidates_qa.py`.

| Area | Checked | Result |
|---|---|---|
| Gemini categorises | one call per receipt with the stripped line names; candidates take Gemini's `display_name`/category/food_group/storage, keep `receipt_text`; `categorized_by: "gemini"`; price `"$7.99"` -> 7.99; null quantity -> 1; candidates post straight back to `POST /items` (201); invalid category/food_group/storage fall back per line; empty `display_name` keeps the printed name; short answer padded; `display_name` capped at 120; no lines -> no Gemini call | ok |
| Gemini fails | 400, 403, 500, generic exception, non-JSON, 503 twice, `UpstreamError` at the service boundary: 200, `categorized_by: "heuristic"`, heuristic categories (dairy/meat/produce_leafy), total intact; no key -> never called | ok; empty answer reported as gemini (BE-12, fixed); scalar JSON -> 500 (BE-13, open) |
| Numbers | `_money`: `$3.48`, `" $ 3.48 "`, `1,29`, `$1,299.50`, `3.48 F` parse; `abc`, `""`, `$`, list, dict, inf, NaN, 400-digit string -> null; route never 500s on any of these for price or total and emits strict JSON (no NaN/Infinity); quantity `abc`/0/negative/inf -> 1 | ok (notes below) |
| Total | number, numeric string, `$4.21`, `TOTAL $4.21`, `1,29`, `0`, null, junk, missing key; `raw_text` not echoed | ok |
| Total/tax lines | OCR lines named TOTAL / SUBTOTAL / TAX / Sales Tax / GRAND TOTAL / BALANCE DUE | BE-11, fixed |
| Retry (`_generate`) | 503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED, 504 DEADLINE_EXCEEDED and an untyped exception whose text contains `UNAVAILABLE`: retried exactly once after `RETRY_DELAYS_S = (1.5,)`, then success, or `UpstreamError` on a second failure; 400/401/403/404/500, `TimeoutError`, `ConnectionError`, `ValueError`, bad JSON: one attempt, no sleep; retry applies to every helper (checked `parse_text`) | ok |
| Usage logging | exactly **one** `gemini_usage` line per logical call (not per attempt), `status=ok` after a successful retry, `status=error` after an exhausted retry or fast failure, `purpose=receipt_categorize`; key not in the error text. This matches the code comment and API.md ("still one `gemini_usage` log line"), so it is intended, not ambiguous. | ok |
| Auth / validation | no token and a bad token -> 401 with `{error:{code,message}}`; no body, JSON body, empty multipart, empty file, wrong field name -> 400 `validation_error` and OCR never called; OCR down -> 502 with the error shape | ok |

### Findings
| ID | Severity | Summary | Status |
|---|---|---|---|
| BE-11 | low | `POST /items/from-receipt` passes every OCR line through, so a line named `TOTAL`, `SUBTOTAL`, `TAX`... becomes a candidate whose price is the receipt total (`backend/app/routes/items.py:405`). ml/serve's deterministic parser drops these lines, but its Gemini-structuring path (`ml/ocr/receipt_pipeline.py:291`, `gemini_structure` -> `clean_structured`) excludes them only by prompt wording, and that path overrides the deterministic parse whenever it returns lines. Repro: stub `ml.ocr` -> `{"lines":[{"name":"MILK","price":3.48},{"name":"TOTAL","price":4.21}],"total":4.21}`; the response has 2 candidates. Fix in either layer (a total/tax/subtotal/balance/change/coupon name guard in `candidates.from_receipt_lines` or `clean_structured`); needs an owner ruling. Test: `test_total_and_tax_lines_do_not_become_items` (now passing). | **fixed on #54** (ported fix, 7044932) |
| BE-12 | low | `categorized_by` says `"gemini"` when Gemini categorised nothing. `categorize_receipt_lines` pads its answer to `len(names)` with `{}` (`backend/app/services/gemini.py:153`), so `[]`, `{}`, `{"items":[]}` or `[1,2,3]` produce a truthy list of empty dicts and the route reports gemini (`backend/app/routes/items.py:414`) while every line used the heuristic and kept the printed name. Fix: report gemini only if at least one entry contributed a valid field. Test: `test_empty_gemini_answer_is_not_reported_as_gemini` (now passing). | **fixed on #54** (ported fix, 7044932) |
| BE-13 | low | Valid JSON that is neither a list nor a dict (`null`, `"a string"`, `42`, `true`) reaches `data.get("items", [])` at `backend/app/services/gemini.py:151` -> `AttributeError`, which is outside `_generate`'s `try` and is not an `UpstreamError`, so the route's fallback (`items.py:410`) does not catch it and `/items/from-receipt` returns 500. The response schema makes this unlikely, but the documented contract is "if that call fails, heuristic". The same pre-existing pattern is in `parse_text` (`gemini.py:112`), `detect_from_image` and `suggest_recipes`. Fix: treat a non-list/non-dict answer as `[]` or raise `UpstreamError`. Test: `test_non_container_gemini_answer_is_not_500` (xfail strict, 4 cases). | open, pending the rebase of #54 onto PR 2 |
| BE-14 | low/medium | Coupon/discount lines (`COUPON -0.50`, `MFR COUPON`, `INSTANT SAVINGS`) passed through `from-receipt` as candidates with a negative `est_price`. `POST /items` rejects a negative price, so posting the Add batch back failed with 400 for every item. Repro: OCR `[MILK 3.48, COUPON -0.50]` -> 2 candidates, and posting them back -> 400. Fix: `candidates.is_receipt_noise(name, price)` drops any negative price and coupon/discount/savings/mfr names under the same tail rule, with `off` added as a tail word. It runs in `from_receipt_lines` and in the route before Gemini. Tests: `test_be14_*`, `test_route_negative_price_dropped_not_500`. | **found and fixed on #54** (ported fix) |

Notes (not bugs, for the builder):
- `_is_transient` also retries 504 / `DEADLINE_EXCEEDED`, and any exception whose first 300 chars contain `UNAVAILABLE`, `RESOURCE_EXHAUSTED` or `DEADLINE_EXCEEDED`. A client-side `TimeoutError` is not retried. A daily-quota 429 is retried once too (harmless, adds 1.5 s).
- The failed first attempt gets no usage line of its own, and the logged latency includes the 1.5 s sleep. That's fine for cost, because a 429 or 503 isn't billed.
- `_money("1e400")` returns 1.0 (the regex drops the exponent), and `_money(True)` returns 1.0 (`bool` is not excluded, unlike `ml/ocr._to_num`). Negative prices (coupon lines such as `-1.00`) pass through as a negative `est_price`. A finite huge price (`1e308`) comes back on the candidate and would hit BE-9 (500) if posted back to `POST /items`.

### Re-verification after commit 7044932 (BE-11, BE-12 fixed)
Targeted runs only, from `backend/` on `fwr_test`: `tests/test_receipt_candidates_qa.py` = **130 passed, 4 xfailed** (BE-13 x4, strict); the author's `tests/test_receipt_candidates.py` = 57 passed; `tests/test_gemini_retry.py` = 20 passed. Combined: 207 passed, 4 xfailed. Full suite still pending.

- **BE-11 fixed.** `candidates.is_receipt_total` (now the tail rule, see below; it replaced the first prefix-only regex) runs in the route before Gemini and in `from_receipt_lines`. The 6 former xfails now pass. New tests:
  - 16 total-like names match (`Sub Total`, `SUB-TOTAL`, `VISA TENDER`, `DEBIT CARD`, `CHANGE`, `CASH`, `TOTAL 4.21`...).
  - 14 food names are kept: Cashews, Cardamom pods, Tortilla, Taxi bread, Totino pizza, Balanced oats and Changua, in mixed and upper case. Kept end to end with SUBTOTAL, TAX and TOTAL dropped.
  - **Totals are never sent to Gemini.** In the stubbed `generate_content` request, the contents are exactly `["GV 2% MLK GAL", "Cashews"]` for a receipt that also had SUBTOTAL, Sales Tax, GRAND TOTAL, VISA TENDER and CHANGE.
  - A receipt with only total lines makes no Gemini call.
- **BE-12 fixed.** `categorized_by` is `"gemini"` only when some entry has a non-empty `display_name`, `category`, `food_group` or `storage`. The 4 former xfails pass. A boundary test confirms that a single usable entry (`[{}, {"category":"meat"}]`) still counts as gemini.
- **BE-13 open** (4 strict xfails kept as they were); resolves with the rebase onto PR 2.

**Total guard: tail rule (orchestrator ruling, implemented in `candidates.is_receipt_total`, documented in `docs/API.md` under from-receipt).** The guard replaces the earlier prefix-only regex, whose "Total Cereal is dropped" limitation is resolved. A line is dropped only if it is:
- optional prefixes (`sales`, `grand`, or a card network: `visa|debit|credit|mastercard|mc|amex|discover`),
- then a keyword (`subtotal`/`sub total`/`sub-total`, `total`, `tax`, `change`, `cash`, `card`, `balance`, `tender`, or a card network),
- followed by nothing except numbers, `%`, currency, punctuation, masked card digits (`x1234`, `****1234`), or the closed word set `due, amount, amt, paid, tendered, tend, back, purchase, sale, savings, saved, auth, approved, chip, contactless` plus the card networks.

Verified on top of the earlier cases (targeted: `test_receipt_candidates_qa.py` 143 passed, 4 xfailed for BE-13; `test_receipt_candidates.py` 57 passed; `test_gemini_retry.py` 20 passed):
- **Kept:** "Total Cereal" (`test_total_cereal_is_kept`, formerly the limitation test), "Cash & Carry Crackers", "Change Coffee Co Beans" and "Discover granola".
- **Dropped:** "TOTAL DUE", "TAX 1 8.25%", "CHANGE DUE", "CASH TENDERED", "VISA CREDIT ****1234", "BALANCE DUE", "TOTAL $4.21", "VISA x1234" and "CARD XXXX1234".
- Both lists are also checked end to end through `/items/from-receipt`.
- The earlier 16 drop cases and 14 food-name keeps still hold.

**Note for the orchestrator:** a bare card-network line is treated as a payment line and dropped. This covers "MC", "DISCOVER" and "Discover", and also "MC 1234". It is intended under the ruling, because a product named only "Discover" or "MC" is not expected on a grocery receipt. Any brand that is exactly a keyword plus tail words (e.g. a product printed as "TOTAL SAVINGS") would also be dropped.

### BE-14 (coupon/discount lines) found and fixed on #54
Found in the orchestrator's review and fixed by the builder (ported fix). `candidates.is_receipt_noise` drops a line if its price is negative, or if its name is a coupon/discount line under the tail rule. That means an optional `instant`/`mfr` prefix, then `coupon|discount|savings|mfr`, then only amounts, `%`, punctuation or tail words (now including `off`).

Targeted runs, from `backend/` on `fwr_test`:

| File | Result |
|---|---|
| `test_receipt_candidates_qa.py` | 166 passed, 4 xfailed (BE-13, strict) |
| `test_receipt_candidates.py` | 57 passed |
| `test_gemini_retry.py` | 20 passed |

- **Repro:** OCR `[MILK 3.48, COUPON -0.50]` now gives 1 candidate, and posting the candidates back to `POST /items` gives 201.
- **Dropped:** MFR COUPON (with a positive and a negative price), INSTANT SAVINGS, `INSTANT SAVINGS 1.00 OFF`, `COUPON $1.00 OFF`, `DISCOUNT 10%`, SAVINGS, and MILK at -0.5, `"-1.00"` and -0.01.
- **Kept:** Savings Bread, Discount Ham, Coupon Cookies and `Coupon Cookies 2.00`. MILK at price 0, None or junk is also kept.
- **End to end:** the keeps come back, the drops don't, and posting back gives 201.
- **Never sent to Gemini:** in the stubbed request, the contents are exactly `["GV 2% MLK GAL", "Coupon Cookies"]`.
- **Changed test:** `test_route_price_never_500[-1.00--1.0]` is removed from that parametrisation. A negative price is now dropped, not returned, and `test_route_negative_price_dropped_not_500` checks this for `"-1.00"`, -0.5, `"$-1.00"` and `"-$1.00"`.

**Verdict for #54 backend: PASS pending the full suite.** BE-11, BE-12 and BE-14 are fixed. BE-13 is tracked (strict xfail) until the rebase onto PR 2.
