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

### iOS QA (`ios/Tests/`, XCTest + XCUITest, CI on macOS via `.github/workflows/ios.yml`)
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
| 2026-10-10 | #7 | Design | Not a QA area. Photo-review and Recipes screens added; new color pairs checked (5.9:1, 6.3:1) | **awaiting team approval** | none |
| 2026-10-10 | #8 | ML parser fixes | ML QA: new blind holdout **v2** (15 receipts) written while the builder fixed ML-7/8/9 without seeing it, giving **97.2 / 100 / 100**. The ML-10 fix that followed brought all three sets to 100/100/100. A ~60-line black-box probe of the skip logic was also run. Suites: eval 74, ocr 89, serve 12, yolo 3 | **PASS** | ML-11 to ML-14 (all low) |
| 2026-10-10 | #5 | Backend social | Backend QA: 158/158 (100 Wave 1 + 57 social + 1 migration), coverage 94%. Visibility tested for friend, pending, stranger, group member and non-member on every list and mutating endpoint | **PASS** | none |

**Not yet tested anywhere:** the iOS build (no Xcode yet), live Gemini (no key), the live ML service and YOLO accuracy (no GPU), GLM-OCR image-to-text, `docker compose up` of the full stack, and the integration demo path.

## Bug list
Severity: **blocker** (breaks demo path) · high · medium · low. Full repros are in the area logs.

| ID | Severity | Area | Summary | Status |
|---|---|---|---|---|
| BE-1 | high | Backend | `GET /impact` returned 500 for a user with no removals once other users' events spanned more than one Timescale chunk | fixed (#4) |
| ML-1 – ML-6 | medium/low | ML | Receipt parser: qty-first lines, trailing UPCs, Costco item numbers, "Merchandise Total", EUR totals, OCR-spaced decimals | fixed (#3) |
| ML-7 – ML-9 | medium/low | ML | Mixed-case total phrases, voided items, and multi-buy lines | fixed (#8) |
| ML-10 | medium | ML | Products containing a skip word were dropped (`INSTANT OATMEAL`) | fixed (#8) |
| ML-11 | low | ML | Quantity markers (`x3`, `2 x Brioche`) stay in the name and quantity stays 1. Price and total unaffected | open |
| ML-12 | low | ML | A product ending in a weak skip word on a priced line is dropped (`Hot Cocoa Instant 3.00`) | open |
| ML-13 | low | ML | Payment/loyalty lines *before* TOTAL with a mid-label weak word can leak as items (`Cash Tendered 20.00`) | open |
| ML-14 | low | ML | `Receipt Paper Roll` is dropped (`receipt` is a strong skip word) | open |

**Blind sets:** holdout v1 and v2 have both been used to fix bugs, so neither is blind any more. **The next parser change needs a fresh blind set v3**, written by QA and never shown to the builder.
