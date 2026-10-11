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

---

# 2026-10-10 - Dataset stage QA (branch feat/ml-mps-training, VegQual only)

Scope: `ml/yolo/sources.json`, `mldata/fwr_data` as written by `prepare_dataset.py`. Roboflow sets and the Kaggle set are `pending`, so
**the dataset contains VegQual only**. No training or inference was run by QA; checks were file reads plus light Python.

## Regression suites (venv-ml, light)
| Suite | Expected | Got |
|---|---|---|
| `ml/serve/tests` | 12 | 12 pass |
| `ml/ocr/tests` | 89 | 89 pass |
| `ml/yolo/tests` | 3 | 3 pass |
| `ml/eval/tests` (from root) | 74 | 74 pass |
No regressions. (Run before the builder finished; re-run if new yolo tests land.)

## 1. sources.json and mapping
- Licences recorded for all 4 sources. VegQual: CC BY 4.0, which matches the Roboflow export `data.yaml` (rakib151p/vegmining-i6j82 v6); the figshare page itself was not opened. Fridge sets CC BY 4.0, Kaggle fresh/stale CC0 1.0 (all still `pending`, so unverified by QA).
- All 14 VegQual source labels are mapped or deliberately dropped: 10 mapped, 4 gourd labels `null` with a stated reason (not in taxonomy), plus `drop_image_if_label` so a mixed gourd image is not left half-labelled. Good.
- **Freshness mapping correct**: `defected_*` -> `:spoiled`, `fresh_*` -> `:fresh`. Verified on ALL 3,207 kept source images (not just 20): for every label line, class id (via `data.yaml` names), x-centre, and `freshness/*.txt` flag (1 = spoiled) match the source label and the mapping. 0 mismatches, 0 unmatched files. Kept-image count matches an independent recount (3,207 = 4,831 - 1,615 gourd-only - 6 mixed - 3 empty).
- Crop classifier folders: train fresh 3,370 / spoiled 2,929, val 410 / 358. Fresh counts equal the box counts exactly; spoiled is 2 short in train (likely degenerate tiny crops, not reported).
- `data.yaml` names (0..56) in the output are **identical** to `ml/yolo/data.yaml`; append-only order unchanged.

## 2. dataset_report.json
Images: train 2,493 / val 346 / heldout 368 real (+674 synthetic copies = 1,042 held-out rows).
Boxes (fresh/spoiled), train: bell_pepper 1118/510, eggplant 619/805, potato 880/203, onion 457/1026, tomato 296/387.
Val: bell_pepper 159/124, eggplant 94/61, potato 74/24, onion 48/102, tomato 35/47.
Held-out (real images only, all lightings in the file): bell_pepper 105/97, eggplant 70/98, potato 137/16, onion 49/194, tomato 65/50.
- **classes_with_no_data: 52 of 57** (everything except the 5 above). Only 5 detector classes exist: bell_pepper, eggplant, onion, potato, tomato.
- Dropped/unmapped: report only gives `1621` (1,615 gourd-only + 6 mixed) lumped into one key, plus 3 "source skipped" entries. The 3 images with empty label files are dropped silently and appear nowhere (ML-20).
- No group leakage by the `.rf.` stem: 1,324 groups, 0 appear in more than one split.
- **But near-duplicate leakage exists** (ML-21): 127 of 132 timestamped held-out photos have a train/val photo shot within 10 s (same item, same session).

### Held-out lighting mix (manifest, 1,042 rows)
| Lighting | real (auto) | synthetic | total images | boxes | **spoiled boxes** |
|---|---|---|---|---|---|
| normal | 337 | - | 337 | 725 | **369** |
| low | **2** | 337 | 339 | 727 | **369** (real: **0**) |
| warm | 29 | 337 | 366 | 879 | **455** (real: 86) |
Synthetic copies reuse the same 725 boxes, so there are 369 independent spoiled boxes, in 152 independent photo groups, not 3x that.
Spoiled by class (normal): eggplant 98, onion 194, tomato 50, potato 16, bell_pepper 11.
The real warm images (29) are 154 boxes dominated by bell_pepper (149 of 154 boxes are bell pepper, 86 of them spoiled): the auto tagger is flagging orange/red peppers, so real-warm is a different population from normal.

### Are the QA.md thresholds testable?
- Spoiled recall >= 0.85: n=369 clustered in 152 groups. 95% Wilson CI at 0.85 is about +/-3.6 pts if boxes were independent; wider in truth. Testable **only as a statement about 5 produce classes on plain backgrounds**.
- Per-class precision >= 0.80: fresh/spoiled over 5 classes, OK in n; but spoiled bell_pepper (11) and potato (16) in the normal set are too small for any per-class claim (CI for 10/11 is 62-98%).
- Lighting recall drop <= 10 pts: **synthetic only is testable** (paired, n=369 each, SE ~2.6 pts). **Real low: 2 images, 0 spoiled = untestable.** Real warm: 86 spoiled boxes, but mostly one class, confounded.
- mAP@0.5 >= 0.60 is computed over 5 classes only; it says nothing about the other 52, so passing would overstate the system.

## Bugs found (continue after ML-14)
| ID | Severity | Summary |
|---|---|---|
| ML-15 | **high** | Domain gap. VegQual = 1-2 vegetables on white paper or dark table (Bangladeshi market produce, phone photos). Not fridge shelves, no clutter, no occlusion, no packaging. Spoiled recall measured here will not transfer to the demo (fridge photo). Fridge sets are still pending. |
| ML-16 | **high** | Class coverage and source confound. 52/57 classes have zero data. All 5 present classes come ONLY from VegQual, and the planned fridge sources add `tomato`, `bell_pepper` (and others) only as `freshness_default: fresh`. Once merged, "spoiled" will correlate with "plain-paper VegQual look" and "fresh" with "fridge look", so the classifier can learn the source rather than rot, and the held-out score will not catch it. No fridge/pantry class (milk, egg, meat, etc.) is trained or evaluable. |
| ML-17 | **high** (for the lighting threshold) | Real low-light held-out = 2 images / 0 spoiled; real warm = 29 images dominated by bell pepper. The "lighting recall drop <= 10 pts" check can only be run on synthetic copies (x0.35 / colour cast), which are easier than a real dim fridge. A pass would not be evidence for real lighting. |
| ML-21 | **high** | Near-duplicate leakage: held-out photos have sibling shots from the same session in train/val (127/132 within 10 s). The `.rf.` grouping handles Roboflow augmentations only. Held-out metrics will be optimistic. Fix: group by capture timestamp bucket (e.g. 60 s) or by item/session before the split, or accept and flag it in every reported number. |
| ML-18 | medium | Per-class spoiled n in normal held-out: bell_pepper 11, potato 16. Per-class spoiled claims are noise; spoiled recall should be reported overall and with the Wilson CI. 369 spoiled boxes are clustered in 152 groups. |
| ML-19 | medium | Imbalance: potato spoiled 203 train (vs fresh 880), onion spoiled 1026 (vs fresh 457), tomato fresh only 296. Spoiled prior differs per class (eggplant/onion spoiled-heavy, potato/bell_pepper fresh-heavy), so the classifier can lean on class identity. Held-out spoiled share by class differs from train. |
| ML-22 | medium | Synthetic lighting triples the held-out rows without adding independent samples: any pooled "all lightings" number must not be used as sample size; `detection_metrics.py --manifest` already separates real vs synthetic and QA reports must keep doing so. Also the auto tagger labels reddish/orange produce as `warm` (see ML-17). |
| ML-20 | low | Report gaps: 3 empty-label images dropped silently; drop reasons not split (gourd-only vs mixed-gourd vs empty); no per-class totals per lighting, no source-by-split table, no mention of 2 spoiled crops missing from `cls/train/spoiled` (2,929 vs 2,931 boxes). |

## Verdict: dataset stage
**PASS (mechanics): FAIL for evaluation readiness.**
- PASS: licences recorded, every label mapped or dropped with a reason, freshness mapping verified on all 3,207 kept images (0 errors), taxonomy ids unchanged, no `.rf.`-group leakage, deterministic splits, report and manifest consistent with disk.
- FAIL (cannot sign off any YOLO threshold from this dataset): ML-15, ML-16, ML-17, ML-21 (all high). Held-out is only 5 produce classes on plain backgrounds, real low light has no samples, and near-duplicates leak across splits. Smoke training for the MPS pipeline is fine; do not treat its metrics as QA numbers.
- Needed before a real YOLO sign-off: the fridge sets (and fresh/stale Kaggle) merged, a timestamp/session-grouped split, a hand-tagged real low/warm held-out set (at least ~50 spoiled boxes each, outside VegQual), and a few real fridge photos with spoiled items as a final out-of-domain test.

## 2026-10-10 - semi_fresh contract (PR A1, branch feat/semi-fresh-contract)

**Result: PASS (harness, serve, taxonomy and infer contract), 3 low findings.** Venv `.venv-ml`. Suites: `ml/eval/tests` **119 passed, 3 xfailed** (was 74; +45), `ml/serve/tests` 14, `ml/ocr/tests` 89, `ml/yolo/tests` 24, all passing. Nothing needs a model: infer is tested with fake detector and classifier objects.

Eval harness changes (ml/eval is QA's; LemurTech22's 7843e06 ported where it fits):
- **Gates stay binary.** `semi_fresh` folds into `not_spoiled` in ground truth and predictions before spoiled recall, per-class precision and the lighting drop. Result keys are `freshness.not_spoiled` and `freshness.spoiled`; `freshness.fresh` is kept as an alias of `not_spoiled` for old consumers.
- **Decision: the "fresh precision" gate reads as NOT-SPOILED precision.** Jose's version treated semi_fresh as a third matched class, which would have charged fresh precision for every fresh/semi confusion. `check_thresholds.py` now prints `YOLO precision [not-spoiled]` and reads `not_spoiled` (legacy `fresh` accepted for old JSON). It never reads `semi_fresh` or `freshness_3way`.
- **Information only:** `freshness_3way` has the 3x3 confusion matrix (rows GT, cols prediction, plus `missed` column and `false_positive` row; localisation-only matching), per-class 3-way P/R including `semi_fresh`, and `recall_drop_points.<light>.semi_fresh`. `print_report` prints it under "NOT gated".
- Unknown freshness labels (`rotten`, `Semi_Fresh`, `None`) now raise ValueError instead of being dropped silently. 2-class files give identical numbers; all 74 old tests pass.
- Not ported: Jose's 3-class per-class P/R tests (they assert the semi_fresh class is matched on its own, which is the behaviour we decided against). His builder tests are covered by `test_ml_contract_freshness.py`.

New tests: `test_semi_fresh_eval.py` (folding, fresh/semi swap costs nothing, spoiled-called-semi is a gated miss, hand-computed 3x3, missed/conf/name, lighting drops, check_thresholds not gating semi, end-to-end fresh/semi swaps pass every gate through JSON); `test_ml_contract_freshness.py` (new classes have food group/category and are appended with old ids unchanged; `Semi fresh Pineapple (15-25)` -> pineapple / semi_fresh; `label()` table; simulated 2-class and 3-class classifier outputs in either index order; serve passes the three values and turns junk into fresh).

### Bugs (continue after ML-26)
| ID | Severity | Summary |
|---|---|---|
| ML-27 | low | `ml/serve` freshness check is exact-match. `"SPOILED"`, `"Semi Fresh"`, `"semi-fresh"` become `fresh` with a log warning, and "spoiled shown as fresh" is the costly direction. The real detector only emits canonical values, so no live impact. Pinned by 3 strict xfails in `test_ml_contract_freshness.py`. Suggest folding case, hyphens and spaces before the check. |
| ML-28 | low | Vocabulary mismatch: `taxonomy.FRESH_WORDS` has `ripe` -> **fresh** (and `unripe`, `good`, `healthy`), while the backend normaliser maps `ripe` -> **semi_fresh** (see BE-6). Different layers, different answer for the same word. Matters only for free text (Gemini). Pick one table. |
| ML-29 | info | Stale two-class wording left in files outside the PR's edits: `docs/ARCHITECTURE.md:24`, `docs/DECISIONS.md:16`, `docs/IDEA.md:33`, `ml/yolo/train.py:12` and `ml/yolo/prepare_dataset.py:3` comments, and `ml/yolo/tests/test_prepare.py:61` asserts freshness `in ("fresh","spoiled")` (passes only because its fixture has no semi folder). |

Not tested: real 3-class weights, and any real `semi_fresh` metric. All `semi_fresh` data is AgriFreshNET (ML-16).

### 2026-10-10 - re-verification after fixes (commit 5e15b00, rebased on main with pipeline/ from #26)

**Verdict: FAIL (2 findings to fix before merge): ML-30 and ML-31.** The ML-27 and ML-28 fixes are verified.

| Suite | Result |
|---|---|
| `ml/eval/tests` (.venv-ml, from root) | **131 passed**, 0 xfail (+12 from flipping the 3 ML-27 xfails and adding every taxonomy spoiled/semi word) |
| `ml/ocr/tests` | 89 passed |
| `ml/yolo/tests` | 24 passed |
| `ml/serve/tests` | 13 passed, **1 failed** (ML-31) |
| `pipeline/tests` (pipe-ci venv, CI command) | 144 passed, **2 failed** (ML-30), 2 skipped (both `needs_2class`, correct: the taxonomy now has semi_fresh) |

- **ML-27 verified fixed.** `SPOILED`, `Rotten`, `moldy`, ` spoiled ` -> spoiled; `semi-fresh`, `Semi Fresh`, `SEMI_FRESH`, `use soon` -> semi_fresh; every `taxonomy.SPOILED_WORDS` entry (upper-cased) -> spoiled and every `SEMI_WORDS` entry -> semi_fresh; `ripe` and `Over-Ripe` -> fresh with a warning.
- **ML-28 verified fixed** (backend dropped the `ripe` alias, see BE-6).
- **Pipeline tests that were skipped before and now run:**
  - `test_agrifreshnet_folder_names[Semi fresh Pineapple (15-25)-pineapple-semi-15-25]` PASS
  - `test_agrifreshnet_folder_names[Semi_Fresh eggplant(4-8)-eggplant-semi-4-8]` PASS
  - `test_agrifreshnet_folder_names[Semi Fresh Bittermelon ( 3-5)-bitter_melon-semi-3-5]` PASS
  - `test_semi_fresh_mapped_to_fresh_is_flagged_not_silent` PASS (asserts `semi_mapped_to_fresh is False` on this taxonomy)
  - `test_prepare_semi_fresh_class` **FAIL** (ML-30)
  - `test_prepare_outputs` **FAIL** (ML-30; its sidecar-code assertion became `{"0","1","2"}` now that HAS_SEMI is true)
  - The two `qa_pipeline.py::test_two_class_*` tests are skipped as intended.

### New bugs
| ID | Severity | Summary |
|---|---|---|
| ML-30 | **medium** | `ml/yolo/prepare_dataset.py` line ~145 still writes the freshness sidecar as `1 if spoiled else 0`, so every semi_fresh box gets code 0 (same as fresh). `taxonomy.FRESHNESS_CODE` (semi_fresh = 2) is defined but used nowhere, and `dataset_report.json` has no `boxes_by_freshness` (Jose's 7843e06 had both; the rebase lost them or they were never ported). Staging and the `cls/<split>/semi_fresh` crop folders are correct (162 semi images staged, `splits` counts them), so a classifier trained from crops is fine, but the sidecar can no longer tell fresh from semi_fresh. Repro: `pipeline/tests/test_prepare_augment.py::test_prepare_outputs` and `::test_prepare_semi_fresh_class`. Fix: write `T.FRESHNESS_CODE[b['freshness']]`, update the comment, add `boxes_by_freshness`. |
| ML-31 | low | `ml/serve/tests/test_app.py::test_detect_freshness_normalisation` expects `"rotten"` -> `fresh`, which the ML-27 fix deliberately changed (now `spoiled`). Stale builder test; change the expectation to spoiled. |

### ML-29 split (stale two-class wording)
- **Owned by A1** (ml/yolo, ml/serve, backend, API.md, ML.md): `ml/yolo/train.py:12` (comment "fresh/spoiled crop classifier"); `ml/yolo/prepare_dataset.py:3` (docstring) and `:145` (comment "0/1 (1 = spoiled)", the real bug in ML-30); `ml/yolo/tests/test_prepare.py:61` (asserts `in ("fresh", "spoiled")`; passes only because its fixture has no semi folder). docs/ML.md:50 and :76 describe the data sources and read fine.
- **Orchestrator-owned docs:** `docs/ARCHITECTURE.md:24` (fresh/spoiled crop classifier), `docs/DECISIONS.md:16` ("labels each crop fresh or spoiled"), `docs/IDEA.md:33` (YOLO, fresh vs spoiled; product wording, fine to leave). `docs/QA.md:26` and `:40` say "fresh, spoiled" per class; correct under the binary-gate note once "fresh" is read as not-spoiled, but worth the one-line wording fix.

### 2026-10-10 - final verdict (PR A1) after ML-30 / ML-31 / ML-29 fixes

**PASS.** Independent re-run: `ml/serve` 14, `ml/ocr` 89, `ml/yolo` 24, `ml/eval` 131, `pipeline/tests` (CI command) 146 passed / 2 skipped (the two `needs_2class` tests, correct now that the taxonomy has semi_fresh). All six previously skipped semi_fresh / pineapple / bitter_melon pipeline tests pass, including `test_prepare_outputs` and `test_prepare_semi_fresh_class`.
- ML-30 verified fixed: on a synthetic AgriFreshNET drop with semi sources the sidecar now has codes {0, 1, 2} (62 / 54 / 182 lines, the last including augmented copies) and `boxes_by_freshness` = fresh 54, semi_fresh 162, spoiled 54.
- ML-31, ML-27, ML-28 and the A1-owned part of ML-29 are fixed. Still open: orchestrator-owned wording in `docs/ARCHITECTURE.md:24`, `docs/DECISIONS.md:16` and `docs/QA.md:26,40` (info only).
- Backend: no source or test file under `backend/` changed since the 394-passed / 1 skipped / 96% run, so it was not re-run.
