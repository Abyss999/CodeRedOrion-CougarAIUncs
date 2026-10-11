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
- YOLO on a held-out set: precision/recall per class (spoiled vs not-spoiled, with semi_fresh counted as not-spoiled; the 3×3 matrix is informational), and under normal / low /
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
| YOLO | Precision, per class (not-spoiled, spoiled), where not-spoiled = fresh + semi_fresh | ≥ 0.80 |
| YOLO | **Recall, spoiled** (a missed spoiled item is the costly error) | ≥ 0.85 |
| YOLO | Recall drop, low or warm light vs normal | ≤ 10 points |
| OCR | Line-item recall (≥ 20 receipts) | ≥ 85% |
| OCR | Price exact match | ≥ 90% |
| OCR | Receipt total exact match | ≥ 90% |
| iOS | Build errors | 0 |
| iOS | UI tests (5 main flows) | 100% |
| Integration | Demo path | completes with no manual fix-ups |

**Held-out leakage (ML-21, decided 2026-10-10).** A YOLO metric counts only if the held-out split passes `ml/eval/leakage_check.py`:
- **Timestamped images:** 0% of held-out images have a train or val image from the same source within 300 s. The 60 s and 300 s neighbour rates are reported per source.
- **Untimestamped or numbered series:** grouped by series, and **≤ 1%** of held-out images have a perceptual near-duplicate (pHash Hamming ≤ 6) in train or val.
- **Sessions:** a session is a maximal run of one source's timestamped images with gaps under 300 s. Untimestamped images are grouped by series, or by specimen for AgriFreshNET, using pHash connected components across all 8 flip and rotation variants. **Sessions with fewer than 10 images don't count** toward the "≥ 2 qualifying sessions" requirement.
- **Coverage (ML-23):** a class × freshness cell is **required in held-out** if it has ≥ 10 images and ≥ 2 qualifying sessions or groups. It's split by whole session. **Train keeps ≥ 50% of every measurable cell.** No cell may sit only in held-out or only in val. If no session-respecting cut satisfies all of this, the cell goes **entirely to train** and is reported as "not measurable on held-out", with N/A metrics and its image and session counts stated. **Leakage beats coverage.**
- **Pooling:** small groups may be pooled into a held-out unit when they are **complete** sessions or untimestamped groups, never fragments of a larger session. The leakage gate runs after pooling, and `leakage_check.py` asserts that every held-out session is complete and ≥ 300 s from train and val. Pooled units are recorded per cell.
- **Per-source reporting:** spoiled recall is reported per source with Wilson 95% CIs (ML-18) and pooled. The ≥ 0.85 gate applies to the pooled value, and any source below it is listed as a named risk. hien_fridge detection metrics are labelled "single fixed camera" (ML-32).
- **Near-duplicate signals:** the gate is pHash (Hamming ≤ 6). Other hashes, such as dHash, are informational. When they flag a source heavily, QA inspects a sample of flagged pairs by eye. "Same scene, different contents" is a domain-similarity risk, so that source's metrics are reported separately and labelled. "Same shot" is a grouping bug and fails the gate.
- Everything is reported per source. A model trained on a split that fails this check has contaminated metrics and must not be quoted.

**Freshness gates (decided 2026-10-10):** freshness is three-class (`fresh | semi_fresh | spoiled`), but **the YOLO gates stay binary: spoiled vs not-spoiled**. For spoiled recall, per-class precision and the lighting-drop gate, `semi_fresh` counts as not-spoiled in both ground truth and predictions. ML QA also reports the full 3×3 freshness confusion matrix, plus `semi_fresh` precision and recall, **for information only, with no gate**. Every `semi_fresh` label comes from one source (AgriFreshNET), so that metric can't be separated from the source (ML-16). Revisit this if a second semi_fresh source is added. **Lighting gates are signed off only on real low and warm images, never on synthetic copies** (ML-17, ML-22), and that includes models trained with lighting augmentation.

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
| 2026-10-10 | #26 | ML pipeline (port of #21) | Pipeline QA ran its own pass (#21's self sign-off was not reused): 145 passed / 3 skipped (the semi tests waited for #29). CI green | **PASS** | PL-2, PL-3 (low) |
| 2026-10-10 | #29 | semi_fresh contract (port of #21, A1) | `fresh / semi_fresh / spoiled` across taxonomy, serve, backend and eval. Normalisers tested against the taxonomy word lists. Binary gates. Suites: serve 14, ocr 89, yolo 24, eval 131, pipeline 146, backend 394 (96%) | **PASS** | none (ML-27 / 28 / 30 / 31 and BE-6 fixed before merge) |
| 2026-10-10 | #27 | ML data v3 (4 sources) | **Dataset readiness only, no YOLO metrics yet.** leakage_check PASS on all 4 sources (0 within 60 / 300 s, pHash 0%, complete-session assertion). stratification_check 0 failures (minimum train share 60.9%). Measurable spoiled held-out: potato 77, apple 97, tomato 66, bell_pepper 44. Suites: serve 14, ocr 89, yolo 35, eval 138, pipeline 146 | **PASS: Colab gate open** | ML-28 (medium, val lacks potato and apple/spoiled), ML-32 |
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
| ML-21 | high | ML | Held-out leaked near-duplicate and same-session photos | fixed (#27) |
| ML-23 | medium | ML | Class-homogeneous splits / required cells missing from held-out | fixed (#27) |
| ML-28 | medium | ML | val has no potato and no apple/spoiled, so best-epoch selection can't see them | open: Colab run uses **last.pt**, not best.pt, until fixed |
| ML-32 | medium | ML | hien_fridge is one fixed camera, so its detection metrics are optimistic (logged as ML-27 in `qa/ml.md`; renumbered because A1 used ML-27) | open: report separately |

**Blind sets:** holdout v1 and v2 have both been used to fix bugs, so neither is blind any more. **The next parser change needs a fresh blind set v3**, written by QA and never shown to the builder.
