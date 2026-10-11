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

## 2026-10-10 - PR 2 insights-wave2 (branch feat/insights-wave2)

**Result: PASS (final).** Full suite on `feat/insights-wave2` (HEAD 3cf6d3c, clean tree), run by the orchestrator from `backend/` on `fwr_test`: `pytest -q --cov=app` = **965 passed, 1 skipped, 101 s, total coverage 98%** (`gemini.py` 96%, `recipe_cache.py` 98%, `candidates.py` 95%). No xfails are left in `backend/tests`. **Fixed in this PR:** BE-9 (`est_price` overflow → 400, plus the `quantity` / `est_weight_kg` caps), BE-10 (both parts: `/impact` week buckets, the zero-fill and the week/month windows no longer depend on the session time zone or DST), and BE-13 (a scalar or non-list Gemini response → 502 / default shelf life, never a 500; filed on #54, root fix here). The targeted-run details and the two follow-up sections below are the evidence.

| File | Result |
|---|---|
| `test_insights_wave2_impact.py` (new) | 20 passed, 1 xfailed (BE-10) at first; 37 passed, 6 xfailed after the re-verify |
| `test_insights_wave2_batch.py` (new) | 54 passed |
| `test_insights_wave2_recipes.py` (new) | 48 passed |
| `test_insights_wave2_bounds.py` (new) | 29 passed |
| `test_wave2_freshness.py` (BE-9 xfail flipped) | 75 passed |
| `test_ai_endpoints.py` (uses_items now asserted as objects), `test_macros.py`, `test_impact.py`, `test_wave2_restore.py`, `test_removal.py`, `test_tips.py` | 28 / 28 / 8 / 23 / 26 / 3 passed |

`conftest.py`: `_clean` now also calls `recipe_cache.clear()`, because the cache lives on the session-wide app.

| Area | Checked | Result |
|---|---|---|
| `/impact` split | `used` + `donated` = `saved` for count and money (exact), and for kg and co2e (within 0.01 rounding); every range; via SQL fixtures and via the API; `range` echoed | ok |
| Waste reasons | all 4 always present and zero-filled; sorted by count with ties in enum order; `share` sums to 1 and is 0 when empty; per-reason kg, money and co2e; range-filtered; sums equal `wasted` | ok |
| Previous period | week and month windows; `now()` pinned in the since query so events sit **exactly** on `since` (current) and on `prev_since` (previous), and 1 µs earlier (previous / excluded); `null` for `all` | ok |
| `last_6_weeks` | always 6, oldest first, Mondays, the last one is the current UTC bucket; zero-filled; independent of `range`; Monday 00:00:00Z is in the new week and 1 µs earlier in the previous one; the oldest bucket edge is included and 1 µs before it excluded (it still counts in the totals) | ok in a UTC session; see BE-10 |
| Isolation | another user's remove events (and own `add` events) never reach totals, reasons, previous or the series | ok |
| `/impact` N+1 | statement count with 0 and 60 events (many weeks and reasons) is equal; 6 for week/month (auth + since + 4), 5 for all | ok |
| Recipes `servings` | 1..20 int kept (`4.0` becomes 4); 0, 21, negative, 2.5, `"4"`, bool, null, NaN, inf, 1e308 or missing give `null` | ok |
| `uses_items` | `{item_id, name, predicted_expiry}`; case and space-insensitive; exact match beats containment; soonest-expiring wins; each item once per recipe but reusable across recipes; unmatched or garbage names dropped (never a 500); never another user's, removed or group-member item; only the 20 items sent to Gemini | ok |
| Recipe cache | the second call is a hit (Gemini called once) and logs `status=hit age_s=`, with a miss logged as `reason=empty`; no user id, email or item names in the log; key covers `max_results` and `dietary` (dietary order-insensitive); add, remove, remove-batch and PATCH of name, quantity, expiry, category or unit all miss with `reason=items_changed`; a removed item is never served from cache; TTL: just under 6 h is a hit, past 6 h a miss with `reason=expired`; TTL 0 disables it; users never see each other's entries (same item names, different results); 502 not cached; no items means no Gemini call and nothing cached; an empty Gemini result is cached; a cached response is byte-identical | ok |
| `remove-batch` | used and donated: one event per item (outcome, `user_id` = caller, co2e > 0), request order, `share` only on own items, one `removed_at` for the batch; same impact numbers as single removes; 100 ids ok, 101 → 400 | ok |
| Batch validation | `{"error":{"code","message"}}` 400 for empty, non-list, missing or malformed ids, non-string ids, duplicates, `thrown_out` (with or without a reason), a bad or missing outcome, `waste_reason`, `recipient_id`, unknown fields, or a non-object/invalid JSON body; restore-batch the same, including an unknown `outcome` field; nothing written on any 4xx; 401 without auth | ok |
| Atomicity | one unknown or foreign id → 404 for the whole batch with state unchanged; a foreign id and a random id give identical bodies (no existence leak); one already-removed id → 409 `already_removed` with nothing written; restore-batch with one active id → 409 `not_removed`, or one removal older than 11 minutes → 409 `restore_window_expired`, nothing restored; a forced failure on `INSERT food_events`, `UPDATE share_listings` or `UPDATE items` (remove) and on `DELETE food_events`, `UPDATE share_listings` or `UPDATE items` (restore) → 500, items, events, listings and `/impact` (all ranges) unchanged | ok |
| Impact before = after | remove-batch then restore-batch leaves `/impact` for week, month and all **exactly** equal (dict equality, new sections included) and items, events and listings unchanged; 3 cycles then a final removal leave one event per item; mixing single and batch (single removes → batch restore; batch remove → single restore → partial batch restore) works | ok |
| Sharing | donated batch fulfils open listings (claimed one: `recipient_id` = claimer); it leaves the friend's `/share`; restore-batch reopens with `claimed_by` kept and `recipient_id` / `fulfilled_at` cleared; used batch leaves listings open; a cancelled listing is never touched | ok |
| Group pantry | a member batch-removes group items (event `user_id` = member, `group_id` set, impact credited to the member) mixed with own items; outsider and ex-member get 404 for remove and restore | ok |
| Batch N+1 | statement count identical for 1, 2, 20 and 25 items (used: 6 remove / 7 restore; donated with listings: 7 / 8); group-item batches of 2 and 20 equal | ok |
| Concurrency | two overlapping batches (`[a,b]` and `[c,b]`, 5 rounds, threads + barrier): exactly one 200 and one 409, no deadlock, exactly one event per removed item, the loser's other item untouched | ok |
| BE-9 / bounds | `est_price` 0, 0.01, 99,999,999.99 ok; 1e8, 1e8 + 0.01, 1e12, 1e300 and **99,999,999.995** (which rounds to 1e8 in numeric(10,2)) → 400, nothing written; same on PATCH (value unchanged); negatives 400; one bad price in a 2-item create writes nothing. `quantity` 1e6 ok / 1e6 + 0.01 → 400 and `est_weight_kg` 1e5 ok / 1e5 + 0.01 → 400 (create and PATCH); 1e300 and 1e308 inputs (including gallon and dozen weight estimates) are 400 or produce strictly valid JSON; everything at its cap → remove and `/impact` stay finite. Strict xfail `test_huge_est_price_is_400_not_500` flipped to a passing test | ok, **BE-9 fixed** |

### Findings
| ID | Severity | Summary | Status |
|---|---|---|---|
| BE-10 | low (latent) | `/impact` week buckets depended on the DB session time zone: in a non-UTC session every `weekly` / `last_6_weeks` date was the Sunday before, and the zero-fill `generate_series` stepped in local time. | **fixed in PR 2** (part 1 and part 2, see the follow-ups below) |

Notes (not bugs):
- API.md now says 5 queries for week/month and 4 for all (fixed after my first report); the count test asserts exactly that plus the auth lookup.
- `uses_items` containment matching is greedy. If Gemini says "egg" and the fridge has "Eggplant" expiring before "Eggs", it maps to Eggplant. This follows the contract.
- The recipe cache key leaves out `freshness` and `storage` (per contract). It is per process, so with N gunicorn workers a user can see up to N different cached sets.

### 2026-10-10 - PR 2 insights-wave2, BE-10 re-verify

**Result: BE-10 fixed as reported, with a residual (BE-10 part 2, low, latent, strict-xfail-tracked).** Targeted runs only: `test_insights_wave2_impact.py` = **37 passed, 6 xfailed**; `test_impact.py` = 8 passed. Full suite still gated.

What I changed in the tests:
- `test_last_6_weeks_utc_even_if_session_timezone_is_not` is now an ordinary passing test. It runs with the session zone `America/Chicago` and checks:
  - the 6 dates are the UTC Mondays and each bucket has its event;
  - `weekly` has the same Mondays;
  - the whole response equals the one from a UTC session.

  The helper sets the zone on every pooled connection through a `checkout` hook and asserts `SHOW timezone` before the request, so the test can't pass vacuously.
- New `test_last_6_weeks_stable_across_dst_in_any_session_zone`: 4 session zones (`America/Chicago`, `Pacific/Auckland`, `Asia/Kolkata`, `UTC`) × 4 frozen `now` values (the request's `now()` is rewritten in every statement).
  - **Frozen times:**
    - 2026-11-04 12:00Z: the week after US fall-back.
    - 2026-03-11 12:00Z: the week after US spring-forward.
    - 2026-11-02 00:00:00Z: exactly the new bucket.
    - 2026-11-01 23:59:59.999999Z: the last instant of the old bucket; its window crosses NZ spring-forward on 2026-09-27.
  - **Events in each bucket:**
    - exactly Monday 00:00Z;
    - Monday 02:00Z;
    - the bucket's last microsecond (Sunday 23:59:59.999999Z, which is Sunday evening local time in the Americas);
    - plus one event 1 µs before the oldest bucket.
  - **Asserts:**
    - the dates are the exact expected Mondays;
    - no zero gaps, and every event is in its own bucket;
    - `weekly` (range=all) uses the same Monday keys;
    - the totals are right.
- New `test_range_windows_do_not_depend_on_session_zone` (week and month): events 30 min either side of N×24 h and 2N×24 h before a frozen `now`. The response must be identical in Chicago and in UTC.
- `/impact` query count is now asserted **exactly** against the updated API.md: 5 for week/month and 4 for all, plus 1 auth lookup. It's the same with 0 events and with 60.

Evidence that the fix works: Monday dates are correct in all 4 zones and all 4 frozen times; the 6 Chicago/Auckland cases that failed before the fix (Sunday dates) now pass; the Chicago response equals the UTC one at real `now`.

Residual (**BE-10 part 2, low, latent**: it only shows with a non-UTC session zone, and compose and `fwr_test` run in UTC):
1. In `_LAST_6_WEEKS`, the `ev` CTE's lower bound `time >= time_bucket('1 week', now()) - interval '5 weeks'` is still `timestamptz - interval` with day units, evaluated in the session zone. When the 6-week window crosses a **spring-forward** change, the bound lands 1 h late, so an event in the first hour of the oldest week (Monday 00:00-01:00Z) is dropped. Seen in 2 of the 16 cases: Chicago with now = 2026-03-11 (oldest week 2026-02-02 reads used 0 instead of 1), and Auckland with now = 2026-11-01 23:59Z. Fix: bound with the UTC value already computed (`time >= (cur.wk - interval '5 weeks') AT TIME ZONE 'UTC'`), or use `interval '840 hours'`.
2. `since` / `prev_since` = `now() - make_interval(days => N)` are also session-zone day arithmetic. Across a DST change the week/month window is N days ± 1 h, not N × 24 h. In Chicago with now = 2026-03-11 an event 167.5 h ago drops out of `range=week`, and with now = 2026-11-04 one 168.5 h ago gets in. Fix: `make_interval(hours => 24 * N)` (or `secs`).

Both are strict xfails (they flip loudly once fixed):
- `test_last_6_weeks_stable_across_dst_in_any_session_zone[America/Chicago-2026-03-11]` and `[Pacific/Auckland-2026-11-01T23]`
- `test_range_windows_do_not_depend_on_session_zone[America/Chicago-2026-03-11 ...-week|month]` and `[America/Chicago-2026-11-04 ...-week|month]`

### 2026-10-10 - PR 2 insights-wave2, BE-10 part 2 and BE-13 verified fixed

**Result: PASS on targeted runs, confirmed by the full suite (965 passed, 1 skipped, coverage 98%; see the final verdict above).**

| File | Result |
|---|---|
| `test_insights_wave2_gemini_shapes.py` (new) | 106 passed |
| `test_insights_wave2_impact.py` | 45 passed |
| `test_impact.py` | 8 passed |
| `test_ai_endpoints.py` | 28 passed |
| `test_macros.py` | 28 passed |

`grep xfail backend/tests` finds nothing.

- **BE-10 part 2: fixed in PR 2.** The 6 residual strict xfails now pass as normal tests:
  - the DST zero-fill cases Chicago with `now` = 2026-03-11 and Auckland with `now` = 2026-11-01T23:59Z;
  - the week/month window cases in Chicago at 2026-03-11 and 2026-11-04.

  I also added an Auckland 2026-10-01 window case. The `ev` lower bound and `since` / `prev_since` no longer depend on the session zone: the window is exactly N × 24 h, and the oldest week keeps its first hour. **BE-10 is fully fixed (both parts).**
- **BE-13: fixed at the root in PR 2.** BE-13 was filed on #54, but per the orchestrator's ruling the root fix is here, in `services/gemini.py` (`_as_list` inside `_generate`, plus `_unwrap` in each helper). #54's BE-13 xfails flip once it rebases onto this. The new `test_insights_wave2_gemini_shapes.py` stubs `google.genai.Client`, so the real `_generate` runs:
  - **Scalars** (`null`, `"oops"`, `""`, `42`, `0`, `3.5`, `-1`, `true`, `false`) on parse-text, from-photo (Gemini path) and recipes/suggest → `502 upstream_unavailable` in the `{"error":{"code","message"}}` shape, never a 500, with exactly one `gemini_usage` line (`status=error`, the right `purpose`, tokens still read from the response).
  - **A non-list under the expected key** (`items`, `candidates`, `recipes`: `null`, string, number, bool, object) and invalid JSON give the same result.
  - **`POST /items`** with the same bad shapes for `shelf_life` (scalars, `{"days": <non-list>}`, invalid JSON) → 201 with every item on the default table (`expiry_source=default`, date = `expiry.predict(category, storage)`), one `status=error` line, add events written.
  - **Still fine:**
    - a bare list or a `{key: [...]}` list works (`status=ok`);
    - an object without the key means nothing found: `[]` and 200;
    - Gemini `days` given as a list or as `{"days": [...]}` → `expiry_source=gemini`;
    - a 502 from recipes is not cached.
  - **Service level:** each of the four helpers raises `UpstreamError` (never `TypeError` / `AttributeError`) for every scalar and for invalid JSON, with exactly one error line.
