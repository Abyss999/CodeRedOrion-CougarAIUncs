# QA

Test plan, pass thresholds, sign-off log and bug list. **Merge gate:** a PR merges only with a QA
pass recorded in the sign-off log below. Area QA agents write to `docs/qa/<area>.md`; the
orchestrator folds results in here.

## Test plan
### Backend QA (`backend/tests/`, pytest from `.venv`, against Docker TimescaleDB)
- Every endpoint: happy path, bad input, auth (missing token → 401, someone else's resource → 403).
- **Removal flow, end to end, for each outcome:**
  - `used` / `donated` / `thrown_out` each set `removed_at`, `outcome`, `waste_reason`,
    `removed_after_expiry` correctly.
  - Each writes **exactly one** `remove` event with matching outcome, category, quantity, price, co2e.
  - `thrown_out` without `waste_reason` → 400; `waste_reason` on `used`/`donated` → 400.
  - Removing an already-removed item → 409, and no second event.
  - `donated` on a shared item marks the listing `fulfilled` (+ `recipient_id` if sent).
- Impact endpoint matches a hand-computed fixture.
- Gemini and ML service are stubbed in unit tests; one opt-in live test each.

### iOS QA (`ios/Tests/`, XCTest + XCUITest, CI on macOS)
- Flows: sign-in, add food, remove food via the 3-option sheet (incl. waste reason), Social tab,
  Impact Dashboard.
- App builds cleanly (zero errors); screens match approved designs in `docs/design/`.

### ML QA (`ml/eval/`)
- YOLO on a held-out set: precision/recall per class (fresh vs spoiled), and under normal / low /
  warm lighting.
- OCR on sample receipts: line items, prices, totals.

### Integration QA (after builders merge)
Whole stack in Docker, walk the **demo path**: add food by photo → expiry prediction → remove →
dashboard updates.

## Pass thresholds
| Area | Metric | Threshold |
|---|---|---|
| Backend | Tests passing | 100% |
| Backend | Route coverage (`pytest --cov=app`) | ≥ 80% |
| YOLO | Detection mAP@0.5 | ≥ 0.60 |
| YOLO | Precision, per class (fresh, spoiled) | ≥ 0.80 |
| YOLO | **Recall, spoiled** (a missed spoiled item is the costly error) | ≥ 0.85 |
| YOLO | Recall drop, low or warm light vs normal | ≤ 10 points |
| OCR | Line-item recall (≥ 20 receipts) | ≥ 85% |
| OCR | Price exact match | ≥ 90% |
| OCR | Receipt total exact match | ≥ 90% |
| iOS | Build errors | 0 |
| iOS | UI tests (5 main flows) | 100% |
| Integration | Demo path | completes with no manual fix-ups |

## Sign-off log
| Date | PR | Area | What was tested | Result | Open bugs |
|---|---|---|---|---|---|
| 2026-10-10 | bootstrap | Scaffold (orchestrator check, not a QA agent) | `.venv` install, `pytest` → 1 passed (`/health`), `docker compose config` valid, Timescale image tag exists, workflow/XcodeGen YAML parses. **Not run:** `docker compose up`, iOS build (no Xcode on the VPS) — the Mac covers these (CI is parked, see `ci/README.md`) | pass (partial) | — |

## Bug list
Severity: **blocker** (breaks demo path) · high · medium · low.

| ID | Severity | Area | Summary | Repro | Status |
|---|---|---|---|---|---|
| — | | | | | |
