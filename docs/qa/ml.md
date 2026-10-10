# ML QA log

Owner: ML QA agent. Harness: `ml/eval/` (see `ml/eval/README.md`). Last updated 2026-10-10.

## State at this run (final run, builder code present)
Builder code landed (`ml/ocr/receipt_pipeline.py`, `ml/serve/app.py`, `ml/yolo/*`, `docs/ML.md`).
Everything runs with fakes only; **no model was loaded, no training/inference was run.**

## Results
| Item | Result |
|---|---|
| Eval harness tests (`ml/eval/tests`) | 71 pass (after builder fixes) |
| **OCR parser on 24 fixtures (93 GT lines)** | FIRST RUN (before builder fixes): line recall 84.9% (FAIL by one line), price 100%, total 95.8%. AFTER ML-1..6 fixes: 100% / 100% / 100% (builder had seen these fixtures; see the blind holdout below) |
| Serve contract tests (fake backends) | 14/14 pass: /detect + /ocr shapes, category/freshness enums, bbox sanity, mode=single <=1, 400 envelopes (missing/corrupt/empty/wrong field/invalid mode), 413 oversize, JSON 404, /health 200 |
| Builder's own tests (`cd ml && ../.venv/bin/python -m pytest serve/tests ocr/tests yolo/tests -q`) | 24 passed |
| `docs/ML.md` formats vs harness | agree (same JSONL shapes, absolute-pixel xyxy bbox, GT confidence=1.0 ignored, conf 0.10 export, manifest columns). Adapted: new `--manifest heldout_manifest.csv` option in `detection_metrics.py` reports REAL vs SYNTHETIC lighting separately (synthetic low/warm compared with the originals they derive from via `variant_of`). |

Note on the recall FAIL: 14 of 93 lines missed (02: 5, 04: 4, 08: 4, 19: 1). Fixing any one of ML-1/ML-2/ML-3 clears 85%.
The margin is thin and the fixture set is mine, so expect real receipts to be worse; the verdict is a fail as measured.

## Not run / cannot be evaluated
- **YOLO metrics: not evaluable** (no trained model, no real held-out predictions). Harness verified on synthetic fixtures only.
- GLM-OCR image-to-text, real detector/classifier paths, Docker build, Gemini structuring: not run.
- Spoiled recall will be a produce-only statement (per docs/ML.md section 3); synthetic lighting is easier than real.

## Assumptions
1. `price` = line total charged; discount/tax/deposit/fee lines are not items; `total` = amount paid.
2. Fresh/spoiled P/R matching ignores item name unless `--match-name`.
3. Lighting recall drop is checked on overall and spoiled recall.

## Bug table
| ID | Severity | Summary | Repro | Status |
|---|---|---|---|---|
| ML-1 | medium | Parser drops all lines of the quantity-first layout `3 @ 1.25  GREEK YOGURT      3.75` (returns `lines: []`, total fine) | `parse_receipt_text(open("ml/eval/fixtures/receipts/04_qty_times_price.txt").read())` | FIXED (re-tested on fixtures after builder fix; all lines match) |
| ML-2 | medium | UPC numbers after the name stay in the item name (`GV WHL MILK GAL 078742013251`); docs claim UPC/PLU stripped but only a prefix is. Pollutes names sent to backend/Gemini | fixture `02_walmart_tax_upc` | FIXED (re-tested on fixtures after builder fix; all lines match) |
| ML-3 | medium | Costco item-number prefix kept in name (`E 1234567 KS ORG EGGS 24CT`) | fixture `08_costco_bulk` | FIXED (re-tested on fixtures after builder fix; all lines match) |
| ML-4 | low | `Merchandise Total 16.36` emitted as an item line (total correctly 16.36) | fixture `24_grand_total_label` | FIXED (re-tested on fixtures after builder fix; all lines match) |
| ML-5 | low | `SUMME EUR 4,52` emitted as an item and total null (non-English total keyword; comma decimals parse OK for items) | fixture `21_euro_style` | FIXED (re-tested on fixtures after builder fix; all lines match) |
| ML-6 | low | Heavily spaced OCR noise (`M ILK  2 %  GAL           4 .29`) loses the line | fixture `19_ocr_noisy_spacing` | FIXED (re-tested on fixtures after builder fix; all lines match) |
| ML-7 | medium | `Balance to pay $23.83` (mixed-case, Trader Joe's style) is not recognised as the total: emitted as an item line, `total` is null | holdout `h01_traderjoes` | FIXED (verified 2026-10-10: h01 total 23.83, no phantom line; also v2 v01/v02/v04/v05/v08/v10/v11/v12/v13/v14/v15 phrasing variants `Balance Due`, `AMOUNT DUE`, `You Pay`, `Order Total`, `TOTAL DUE`, `Total Due` all correct) |
| ML-8 | medium | Voided item: the `VOID ORGANIC KALE -2.49` line is dropped but the original `ORGANIC KALE 2.49` line stays, giving a phantom item (net charge was zero) | holdout `h10_voided` | FIXED (verified: h10 and v2 void-after/void-between/void-first/`VOIDED ITEM`/`** VOID **`/void-with-no-match all net out; the 2 residual v2 misses are ML-10, not voids) | |
| ML-9 | low | Multi-buy line `3 @ 2/$5.00 GREEN ONIONS  7.50` is not parsed: name keeps `3 @ 2/$5.00`, quantity 1 instead of 3 | holdout `h12_whole_numbers_and_long` | FIXED (verified: h12, plus v2 `2 @ 3/$4.00`, `4 @ 2 for $5`, `3 @ 2/$5.00` give qty 2/4/3 and the right names) |
| ML-10 | medium | Items whose name contains a SKIP word are silently dropped. `\binstant\b` (meant for `Instant Savings`) kills `INSTANT OATMEAL 10CT`, `Instant Ramen 5pk` (also instant coffee/rice/pudding). Same class: `Credit Card Cookies`, `Coupon Clipper`, `Discount Bread Co`, `Promo Pack Gum`, `Change Purse Candy`, `Cash`-led names (rarer). Found blind on v2 | holdouts v2 `v06_walgreens_voided_item` (oatmeal), `v07_99ranch_mixedcase_void_nomatch` (ramen); repro `parse_receipt_text('S\nINSTANT OATMEAL 10CT 3.79\nTOTAL 3.79')` returned no lines | FIXED (verified 2026-10-10 after builder's `_is_skip()` rewrite: v06 and v07 now match 71/71; black-box probe kept Instant Oatmeal/Ramen/Coffee/Pot Liners, Credit Union Cookies, Coupon Clipper Cookies, Promo Pack Gum, Cash Cow Cheese, Snap Peas, Member's Mark, Rewards Blend Tea, Phone Case Candy, Card Stock Paper). Residual limitation: ML-12 |
| ML-12 | low | Weak-word skip is end-anchored, so a product whose name ENDS in a weak word on a priced line is still dropped (`Hot Cocoa Instant 3.00`). Known limitation flagged by the builder; confirmed | probe | open (accepted limitation) |
| ML-13 | low | Non-item lines with a weak/uncovered word in the middle leak as items when they appear BEFORE total/subtotal (after TOTAL they are all suppressed): `Loyalty Rewards 150 pts 0.00`, `Mastercard ending 4421 15.00`, `Auth Code 123456 0.00`, `Cash Back 20.00`, `Cash Tendered 20.00`, `Credit Card Tendered 5.00`, `Payment Received`, `Savings Today 1.00`, `E-Coupon Applied 0.75`, `Change Given 3.21`, `SNAP BENEFITS 20.00`, `Tip 2.00`. Payment lines normally follow the total, so impact is small | probe | open |
| ML-14 | low | Strong-word false skip: `Receipt Paper Roll 1.99` dropped (`receipt` is a strong skip anywhere) | probe | open |
| ML-11 | low (info) | Quantity markers kept in the name and quantity left at 1: `APPLES GALA x3`, `2 x Brioche Buns` (Aldi), `Sweet corn x6`, `Grass-fed butter 2` (Wegmans two-line), line numbers `01 BANANAS` left as name prefix, `M ILK 2 % GAL` noise. Prices/totals unaffected; quantity exact is 94-96% (informational only, no threshold) | originals 11/17/19/20/23, holdout h03/h08 | open (pre-existing, not part of ML-7/8/9) | |

## Blind holdout (12 new receipts, `fixtures/receipts_holdout/`, written after the ML-1..6 fixes and never shown to the builder)
Stores/layouts: Trader Joe's, H-E-B BOGO, Aldi qty lines, Target Circle + tax, Whole Foods Prime deal + weighted, corner bodega,
mixed-case Asian grocery, farmers-market, multi-page with repeated headers, voided item, loyalty savings + tax, 2-for multi-buy.
| Set | Receipts / GT lines | Line recall (>=85%) | Price exact (>=90%) | Total exact (>=90%) | Line precision (info) |
|---|---|---|---|---|---|
| Original 24 (builder saw these) | 24 / 93 | 100% | 100% | 100% | 100% |
| **Blind holdout** | 12 / 52 | **98.1% (51/52)** | **100% (51/51)** | **91.7% (11/12)** | 94.4% |
The holdout passes all three thresholds, but the total-exact margin is one receipt (ML-7). The 12-receipt sample is small; treat as
evidence of reasonable generalisation, not proof. Parser verdict: PASS on both sets. Reminder: real GLM-OCR output will be noisier than
clean text fixtures; this does not test image-to-text.

## Holdout v2 (15 receipts / 71 GT lines, `fixtures/receipts_holdout_v2/`, `build_holdout_v2.py`) - CURRENT BLIND SET
**Holdout v1 was used to fix ML-7/8/9, so it is no longer blind. v2 was blind for the ML-7/8/9 fix, but ML-10 was found from its failures (v06/v07) and fixed, so v2 has now been SEEN THROUGH ITS FAILURES and is no longer blind: the next parser change needs a fresh blind set v3.**
Stores: Kroger x2, Publix x2, Sprouts x2, Safeway x2, Costco Business, Walgreens x2 (grocery), 99 Ranch, Fiesta, campus dining market, food co-op.
Total phrasings: Balance Due, AMOUNT DUE, You Pay, Order Total, TOTAL DUE, Total Due. Voids: after / between / first / `VOIDED ITEM` / `** VOID **` / no matching item.
Multi-buy: `2 @ 3/$4.00`, `4 @ 2 for $5`, `3 @ 2/$5.00`. Decoys: Subtotal, Total Savings, Total Tax, Item Total, Savings Total, Total Items.
Gate: `test_builder_parser.py`, set `holdout_v2` (85/90/90, no 20-receipt minimum), writes `results/ocr_parser_metrics_holdout_v2.json`.
| Set (after ML-7/8/9 fix) | Receipts / GT lines | Line recall (>=85%) | Price exact (>=90%) | Total exact (>=90%) | Line precision (info) |
|---|---|---|---|---|---|
| Original 24 | 24 / 93 | 100% | 100% | 100% | 100% |
| Holdout v1 (used for fixing, not blind any more) | 12 / 52 | 100% | 100% | 100% | 100% |
| **Holdout v2 (blind)** | 15 / 71 | **97.2% (69/71)** | **100%** | **100% (15/15)** | 100% |
The two v2 misses are both ML-10 (`Instant` in an item name). All 15 totals correct, no phantom void items, no decoy emitted as an item/total.
Parser verdict: PASS on all three sets. Still text-only: real GLM-OCR output is noisier.

### Re-run after the ML-10 fix (`_is_skip()`: strong phrases / card mask / weak words only on negative amount or ending the label)
| Set | Receipts / lines | Line recall | Price exact | Total exact | Line precision |
|---|---|---|---|---|---|
| Original 24 | 24 / 93 | 100% | 100% | 100% | 100% |
| Holdout v1 (used) | 12 / 52 | 100% | 100% | 100% | 100% |
| Holdout v2 (seen via ML-10) | 15 / 71 | 100% | 100% | 100% | 100% |
Black-box probe (~60 lines, before and after TOTAL): all genuine non-item lines tested (Instant Savings +/-, COUPON +/-, MFR COUPON, CASH TEND, CHANGE, CHANGE DUE, VISA XXXX1234 APPROVED, EBT SNAP TEND, DEBIT TEND, Club Card Savings, You Saved, Bottle Deposit, CRV, Bag Fee) are dropped; real products with weak words in start/middle position are kept. Residuals: ML-12/13/14 (all low). No v3 set was written: 100% on v2 is not evidence of generalisation any more.

## 2026-10-10 - 3-class freshness (fresh | semi_fresh | spoiled), branch feat/data-pipeline
Scope: `ml/eval` harness, `taxonomy.py`, `TwoStage.label`, serve `/detect`, `prepare_dataset`. No torch/ultralytics; nothing trained.
- Harness: `detection_metrics.FRESHNESS` now includes `semi_fresh` (per-class P/R, overall sums three classes, lighting-drop tables and printed summary include `semi_fresh`). `check_thresholds.py` untouched: gates stay fresh/spoiled precision >=0.80, spoiled recall >=0.85, drop <=10, mAP >=0.60; semi_fresh is reported only (test proves extreme/None semi numbers change no status).
- New tests: `ml/eval/tests/test_builder_freshness.py` (all 24 AgriFreshNET folder names parse to the right item+class; semi parsed before fresh; old behaviours `rottenapples`/`Fresh_Banana`/`Apple__Rotten`/`Tomatoes`; day-range normalize; constants and `bittergourd` alias; new classes appended at ids 57-59; `TwoStage.label` decision table incl. boundaries, custom thresholds and 2-class probs; serve `/detect` passes semi_fresh and maps junk to fresh; `prepare_dataset.main` on a synthetic folders source gives `boxes_by_freshness`, sidecar codes {0,1,2}, `cls/*/semi_fresh/` crops) plus 3-class cases in `test_detection_metrics.py` and `test_check_thresholds.py`.
- Results: ml/eval 109 passed (was 74 + 35 new); ml/serve 12; ml/ocr 89; ml/yolo 3. All green.
- Limits: the "first 57 class names unchanged vs main" check could not be done literally (QA does not run git); the test asserts the 3 new names sit at ids 57-59 and are not in the first 57, which catches insert/reorder-by-insertion but not a pure permutation of old names. Orchestrator should diff against `git show main:ml/yolo/taxonomy.py`. `export_predictions --semi-fresh-threshold` only checked as present in source (needs ultralytics to run).
- Bugs: none found (no ML-15).
- Verdict: **PASS** for the semi_fresh change (CPU-side logic only; model quality for semi_fresh untested).
