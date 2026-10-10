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
Detail lives in [`qa/backend.md`](qa/backend.md) and [`qa/ml.md`](qa/ml.md). The orchestrator re-ran every suite independently before merging.

| Date | PR | Area | What was tested | Result | Open bugs |
|---|---|---|---|---|---|
| 2026-10-10 | #1 | Scaffold | Orchestrator check, not a QA agent. `.venv` install, `pytest` 1 passed, `docker compose config` valid, Timescale image tag exists | pass (partial: no `compose up`, no iOS build) | none |
| 2026-10-10 | #2 | Design | Not a QA area. Contrast computed for every text pair (min 5.4:1, AA); chart pair passed the colorblind validator | **awaiting team approval** | none |
| 2026-10-10 | #3 | ML | ML QA: eval harness 71 tests; serve contract 14/14 (fake backends); builder tests 24 → 29. Receipt parser: 24 fixtures 84.9% line recall **FAIL** → sent back → 100/100/100; **blind holdout (12 receipts) 98.1 / 100 / 91.7** | **PASS** for parser, service contract and harness. **YOLO not evaluable** (no trained model) | ML-7, ML-8 (medium), ML-9 (low) |
| 2026-10-10 | #4 | Backend core | Backend QA: 93 tests, 1 **FAIL** (BE-1) → sent back → 100/100, coverage 92%. Removal flow verified for every outcome; migration round trip | **PASS** | none |
| 2026-10-10 | #5 | Backend social | Backend QA: 158/158 (100 Wave 1 + 57 social + 1 migration), coverage 94%. Visibility tested for friend, pending, stranger, group member and non-member on every list and mutating endpoint | **PASS** | none |

**Not yet tested anywhere:** the iOS build (no Xcode yet), live Gemini (no key), the live ML service and YOLO accuracy (no GPU), GLM-OCR image-to-text, `docker compose up` of the full stack, and the integration demo path.

## Bug list
Severity: **blocker** (breaks demo path) · high · medium · low. Full repros are in the area logs.

| ID | Severity | Area | Summary | Status |
|---|---|---|---|---|
| BE-1 | high | Backend | `GET /impact` returned 500 for a user with no removals once other users' events spanned more than one Timescale chunk | fixed (#4) |
| ML-1 – ML-6 | medium/low | ML | Receipt parser: qty-first lines, trailing UPCs, Costco item numbers, "Merchandise Total", EUR totals, OCR-spaced decimals | fixed (#3) |
| ML-7 | medium | ML | `Balance to pay $23.83` (mixed case) not recognised as the total | open |
| ML-8 | medium | ML | A voided item leaves a phantom line (the VOID line is dropped, the original is kept) | open |
| ML-9 | low | ML | Multi-buy `3 @ 2/$5.00 GREEN ONIONS 7.50` not parsed | open |

When fixing ML-7 to ML-9, **don't tune against the blind holdout** (`ml/eval/fixtures/receipts_holdout/`). Add new fixtures, then write a fresh holdout.
