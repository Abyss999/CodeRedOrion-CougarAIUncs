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

---

# 2026-10-10 (evening) - Re-review of the session-grouped split (VegQual only), smoke export, suites

Scope: `mldata/fwr_data` as rewritten at 18:10 (**still VegQual only**: fridge_objects v1 and hien_fridge v12 were downloaded at 18:2x but not yet merged; `sources.json` still had them `pending`). The 3-source numbers below are therefore NOT reviewed; sections marked "pending" must be redone after the 3-source prep. Light Python only; no training or inference by QA. New tool: `ml/eval/leakage_check.py` (stdlib, my timestamp method as a re-runnable script).

## ML-21 verdict (gate): **NOT FIXED - FAIL. Do not start a Colab run on this split.**
Method: for each held-out ORIGINAL (not the `__low/__warm` copies) with a filename timestamp (epoch-ms, `IMG_YYYYMMDD_HHMMSS`, `IMG2025...`), nearest train/val shot of the same source.
| | before (17:25 split) | after (session split, 18:10) |
|---|---|---|
| timestamped held-out originals | 132 | 276 (of 325; 49 have no timestamp) |
| nearest train/val shot within 10 s | 127 (96%) | **6** (2%) |
| within 60 s | n/a | **154 (56%)** |
| within 300 s | n/a | 249 (90%) |
| min gap | ~0 | 10 s |
| `.rf.` stems in more than one split | 0 | 0 |
Reading: the worst leakage (same-second siblings) is largely gone, but more than half the held-out photos still have a train/val shot taken within a minute, and 90% within 5 min. Cause (read from `prepare_dataset.py`): `--session-max-span 900` cuts long chains at their largest internal gap, and that gap can be as small as 10-60 s, so a continuous shoot is split across splits; the 60 s gap rule also treats a 61 s pause as a new session although it is the same scene. The 49 un-timestamped originals (`Defected_begun_104`-style names, grouped by stem only) cannot be tested by this method and probably have numbered siblings in other splits. Fix suggestions: no max-span cut (or cut only at gaps > 300 s), session gap >= 300 s, and group numbered series (`Defected_begun_N`) by neighbour index or hold out whole source folders. Until then every held-out number is optimistic. The builder's own `residual_leak` diagnostic should report these 154.

## Dataset review (VegQual-only rerun)
- **Class mapping, ML-16 mechanics:** `class_names.json` = {0 tomato, 1 bell_pepper, 2 potato, 3 onion, 4 eggplant}; `data.yaml` names identical; label ids found in train/val/heldout are exactly {0..4} (counts 1022/2239/1586/1956/2177): contiguous, no empty class, none outside the map. Mapping to canonical names is correct for these 5. PASS. **Unreviewed:** whether the 3-source rerun keeps ids contiguous and `class_names.json` consistent with `ml/serve` and the 57-name taxonomy lookup.
- **Roboflow class maps (static check, before the data is merged):** `fridge_objects` data.yaml names `[avocado bacon butter cheese eggs lemon milk pepper tomatoes yogurt]` all have an entry in `sources.json` (10/10; pepper->bell_pepper, eggs->egg, tomatoes->tomato). `hien_fridge` `[apple egg milk_carton others soda_can yogurt_container]` 6/6 (others dropped). Sizes: fridge_objects 731/125/107 images, hien_fridge 1378/363/171. Spot-check of label files against ids: **pending** (not merged yet).
- **Split balance (new): worse in one respect.** Session grouping makes splits class-homogeneous: **val has only eggplant and bell_pepper** (no tomato, potato, onion); **held-out has no onion and no bell_pepper in the 18:10 dataset report** (report: eggplant, potato, tomato). Per-split class presence in the train/val/heldout report vs the manifest I read differ (see next bullet); the point stands that validation/early stopping sees 2 of 5 classes. New bug ML-23.
- **Report/manifest inconsistency:** `dataset_report.json` "heldout" shows 200 images and no onion/bell_pepper, but `heldout_gt.jsonl`/manifest hold 325 originals (873 rows) including bell_pepper (63 boxes), onion (40). The report was written at 18:10 and the manifest/images belong to the same run, so the report's `splits.heldout` block and `heldout_images_by_lighting_method` (195+5) disagree with the files (325 + 2 real-low + real-warm). New bug ML-24.
- **Drop reasons (ML-20): FIXED.** Now `mixed_with_unmodelled_object` 6, `only_unmodelled_objects` 1615, `empty_label_file` 3; `source_by_split` table present; crops expected 7587 / written 7582 (5 `missing_too_small/train/spoiled`) so the 2-crop gap is now explained. Still missing: per-class totals per lighting in `source_by_split` (they exist in `heldout_boxes_by_lighting_method_class`).
- **ML-16 source confound:** with VegQual only there is no confound yet (every class has both freshness from one source). It reappears once the fridge sets merge: they supply only `fresh` (tomato, bell_pepper, lemon, milk, ...), so tomato/bell_pepper spoiled = VegQual only, fresh = VegQual + fridge. Per-class source table must be produced from the 3-source report: **pending**. Proposed guard: report spoiled recall/fresh FPR on a VegQual-only held-out slice AND a fridge-only slice, and keep fridge-set fresh images out of the "spoiled" decision metric.
- **Lighting mix and per-class spoiled counts in held-out (from `heldout_gt.jsonl`, 18:10):**
| Lighting | method | images | spoiled boxes |
|---|---|---|---|
| normal | auto | 325 (originals, 323 + 2 real-low reclassified) | 182 (eggplant 101, potato 56, bell_pepper 13, onion 12, tomato 0) |
| low | synthetic | 325 | 182 |
| low | **real** | **2 (eggplant fresh)** | **0** |
| warm | synthetic | 325 | 182 |
| warm | **real** | n/a (bell_pepper only, 71 boxes) | 31 (all bell_pepper) |
Note: tomato in held-out is 71 fresh and **0 spoiled**; the 18:10 split put every spoiled tomato in train. Independent spoiled boxes: 182 (eggplant 101, potato 56, bell_pepper 13, onion 12) in far fewer photo groups; per-class spoiled claims for bell_pepper/onion are noise (ML-18). The earlier report line claiming 10 real-warm tomato boxes belongs to a different run.

## Task 2: smoke-export metrics (**PLUMBING TEST / pipeline check only**)
`mldata/runs/smoke_export`: 873 rows, a **2-epoch yolo26n smoke model trained on the PRE-FIX split**. Two problems make these numbers non-evidence beyond plumbing: (a) the held-out images of the new split were not held out from that model (it was trained on the old split, so many new held-out images were in its train set: contamination); (b) 2 epochs. Harness ran fine (`detection_metrics.py --manifest`, `check_thresholds.py`); output was sane, nothing crashed.
| Threshold | Value | Result |
|---|---|---|
| mAP@0.5 >= 0.60 | 0.901 | PASS (meaningless: contaminated, 5 classes) |
| Precision fresh >= 0.80 | 0.783 | FAIL |
| Precision spoiled >= 0.80 | 0.665 | FAIL |
| Recall spoiled >= 0.85 | 0.726 | FAIL |
| Recall drop low vs normal, overall <= 10 | 25.9 pts | FAIL |
| Recall drop low vs normal, spoiled <= 10 | 5.5 pts | PASS (synthetic only; see below) |
| Recall drop warm vs normal, overall <= 10 | 8.5 pts | PASS (pooled real+synthetic, do not read) |
| Recall drop warm vs normal, spoiled <= 10 | 4.0 pts | PASS (pooled, do not read) |
| OCR (4 checks) | not in this run | FAIL by definition of `check_thresholds` when no OCR json is given (not an ML failure) |
Real vs synthetic, separately (never pooled): synthetic low: overall drop 25.6, spoiled 5.5; synthetic warm: overall 7.0, spoiled 2.7. **Real low: not measurable** (2 images, 0 spoiled; the 88-point overall "drop" is 2 eggplant images). **Real warm: not measurable as a lighting claim** (bell_pepper only, 31 spoiled boxes; overall drop 19.1, spoiled 11.3 on that single-class population). So the low-light and warm-light spoiled rows above that print PASS are synthetic or pooled and are NOT a pass on real lighting (ML-17 rule: report as "not measurable"). Overall per-lighting recall: normal 0.882, low 0.623, warm 0.797.

## Task 3: light suites (.venv-ml), run before the builder's later edits
serve/tests 12 pass; ocr/tests 89 pass; yolo/tests 3 pass (from `ml/`, one at a time); ml/eval/tests 74 pass (root). No regressions. Re-run after the builder's final change (yolo tests may grow).

## Task 4: notebook `ml/yolo/train_colab.ipynb` (as read at 18:07, **before** the builder's notebook update landed)
Valid JSON (nbformat 4, 9 cells). No key in the file; the only secret access is the commented example `userdata.get('ROBOFLOW_API_KEY')` (Colab userdata): PASS. Steps vs docs/ML.md: clone -> pip -> fetch sources -> prepare_dataset -> train.py (80/30 epochs) -> val on split=test -> export zip: consistent in order. Gaps: the fetch cell is commented-out example code, so a fresh run does `cp -n sources.example.json sources.json` and silently runs with no real sources; `sources.json` has absolute local paths, notebook ignores them; no step prints/asserts the ML-21 residual-leak numbers; Kaggle step absent. **Re-check after the builder's rewrite: pending.**

## Task 5: secret scan
Whole worktree plus `mldata/*.json`/`*.md` (none exist at top level) and `fwr_data/*.json`, patterns for Google (`AIza`), Roboflow (`rf_`), Kaggle (`KGAT_`/32-hex key) and `*_API_KEY=`/`*_TOKEN=` assignments: **no real key found.** One match, `.env.example` `GEMINI_API_KEY=`, is a placeholder (hyphenated words, 19 chars). Values never printed.

## Status of ML-15..ML-22 and new bugs
| ID | Status |
|---|---|
| ML-15 domain gap (high) | open. Fridge sets downloaded but not yet merged; reassess after the 3-source report. |
| ML-16 class coverage / source confound (high) | partly fixed: contiguous 5-class ids + `class_names.json` verified correct, no empty class. Confound analysis pending the 3-source report; will return when fridge sets (fresh-only) merge. |
| ML-17 real low/warm lighting (high) | open. Real low = 2 images / 0 spoiled; real warm = bell_pepper only. Report as "not measurable"; synthetic passes are not evidence. |
| ML-18 tiny per-class spoiled n (medium) | open (bell_pepper 13, onion 12 spoiled in held-out). |
| ML-19 imbalance (medium) | open (potato spoiled 177 vs fresh 1059; onion spoiled 1322 vs fresh 554). |
| ML-20 report gaps (low) | FIXED (drop reasons split, source_by_split, crop shortfall explained). |
| **ML-21 near-duplicate leakage (high)** | **NOT FIXED**: 154/276 within 60 s, 249/276 within 300 s; 10 s leakage down from 96% to 2%. Gate stays closed. |
| ML-22 synthetic lighting inflation (medium) | open; manifest still separates real vs synthetic and QA reports keep doing so. |
| ML-23 (medium) | Session grouping makes splits class-homogeneous: val contains only eggplant + bell_pepper; held-out has 0 spoiled tomato. Early stopping and spoiled-recall see an arbitrary subset of classes. Stratify at the group level or deal by class (builder says it deals per stratum, but the result shows it does not hold). |
| ML-24 (low) | `dataset_report.json` `splits.heldout` (200 images, no onion/bell_pepper) and `heldout_images_by_lighting_method` disagree with `heldout_gt.jsonl`/manifest (325 originals, 873 rows). |
| ML-25 (medium) | Smoke predictions come from a model trained on the pre-fix split but scored on the post-fix held-out: contamination. Any metric from it is plumbing only. |
| ML-26 (low) | Notebook fetch cell is commented example code and `cp -n sources.example.json`; a fresh Colab run silently has no real sources (re-check after builder's notebook update). |

## Verdicts
- Dataset (this rerun, VegQual only): mechanics PASS (ids, mapping, drop reasons); **evaluation readiness FAIL (ML-21, ML-23, ML-17, ML-15)**.
- Eval harness plumbing on smoke export: PASS (runs, real/synthetic separated). Detector metrics: no sign-off.
- Suites: PASS (12 / 89 / 3 / 74). Notebook: PASS on JSON/secrets, re-check after update. Secrets: PASS (none found).

---

# 2026-10-10 (night) - Re-review of the 4-source reworked split (PR #27): fwr_data, then fwr_data_v2

Tools (ml/eval, mine): `leakage_check.py` now reports **per source** (60 s / 300 s neighbour rates with `re.search` timestamp patterns for epoch-ms, `IMG_YYYYMMDD_HHMMSS`, `Screen_Shot_..._at_H_MM_SS_PM`, `WhatsApp_Image_..._at_...`; independent `imagehash` pHash-64 and dHash-64, Hamming <= 6, held-out originals vs train+val originals; numbered-series index check). Its JSON keeps flat `within_60s`/`within_300s` keys for the notebook gate. New `stratification_check.py` (cells x sessions, class x source, report-vs-manifest). Hash tooling ran in a throwaway venv (`scratchpad/qa-venv`); no heavy jobs were running (`pgrep` clean).

## Verdict against QA.md ML-21 (#25) + orchestrator rulings (#28)
| Source | fwr_data (first rework) | **fwr_data_v2** |
|---|---|---|
| vegqual | 0 / 0 within 60 / 300 s (520 timestamped), pHash 0% | **PASS**: 60 s 0, 300 s 0 (519 ts, min gap 798 s), pHash 0 (0%), numbered series 0 |
| fridge_objects | PASS (no timestamps; pHash 0) | **PASS**: ts n=1; pHash 0 (0%) |
| hien_fridge | pHash 0; dHash 38% | **PASS (gate = pHash)**: ts n=1, pHash 0 (0%); dHash 86/206 = 41.7% informational, see below |
| fresh_stale_fruits_veg (Kaggle) | **FAIL**: 50/192 held-out (26%) within 60 s and 300 s (min gap 1 s). Builder's "0" was wrong: the WhatsApp-named images (`WhatsApp_Image_2020-11-07_at_11_30_46_PM...`) had no parsed time (142 of 192 timestamped; 192 of 192 with my regexes) | **PASS**: 107/107 timestamped, 0 within 60/300 s (min gap 52,754 s), pHash 1/107 = 0.93% (<= 1%; the one pair is a green vs a red wrinkled pepper, a false positive) |
**ML-21: FIXED on fwr_data_v2 for all four sources.** Not fixed on fwr_data (superseded). The mechanical Colab gate (`within_300s == 0`) opens on v2 (aggregate 0). Caveat: Kaggle "capture times" are screenshot/phone-file times and the hold-out is 107 images; the pHash margin there is 0.93% vs 1%.

## hien_fridge dHash flags (eyeballed)
37% on v1, 41.7% on v2. I viewed 30 sampled flagged pairs on v1 and 12 on v2 (side-by-side images). **Every pair is a different photo from the same fixed camera in the same fridge**: identical shelf geometry, same jar, same milk box, with different contents (apples vs eggs vs yogurt cups vs soda). Many "hub" train images (ID16 apple_001, ID23 egg_tray_x2_004) pair with dozens of held-out images because dHash on a flat, mostly-white fridge background is low-entropy. No same-shot or burst duplicate found, so per #28 this is **not a grouping bug**; gate passes. Two v2 pairs (`milk_yogu_othe_00x` vs `milk_yogu_egg__002`) are the same shelf with one object added/removed: the nearest thing to a real near-duplicate, still a different photo and pHash > 6. **Risk (report, do not hide):** hien_fridge is one camera/one fridge, so its held-out score measures "same fridge, rearranged items" and will be optimistic for a new fridge; quote hien_fridge metrics separately and labelled.

## Stratification (#28: cell required in held-out if >= 10 images AND >= 2 capture sessions)
fwr_data: eggplant/spoiled was **only in held-out** (0 train / 3 val / 369 held-out): model never trained on it. FAIL. (Also apple/spoiled and the 6 single-session cells missing.)
**fwr_data_v2 (train/val/held-out images):** eggplant/spoiled 369/3/0 (fixed: now trained on); apple/spoiled 250/0/0; bell_pepper/spoiled 256/332/0; banana, onion, orange fresh+spoiled single-session, all train. No cell held-out/val-only; no cell < 10 images. Report counts match manifest/disk (ML-24: 12 checks incl. per-source and by-lighting, all equal). Totals train 5,911 / val 1,577 / held-out 945 originals (2,617 rows); val is VegQual-heavy (1,114 of 1,577).
Cells the rule requires but that are missing from held-out, my session counts (300 s chain; untimestamped by series stem):
- **bell_pepper/spoiled: FAIL.** Sessions: Kaggle 45 + 158 + 47 (all train), VegQual 6 (train) and 332 (val). Five sessions, held-out has 0 and val holds 332 images. Moving a Kaggle session (or the 332 val one) to held-out leaks nothing, because the cell has other sessions in train. Coupling to other cells is a builder-side balance problem, not an exemption.
- **apple/spoiled: FAIL as written, weakly.** All 250 are Kaggle screenshot images in 4 timestamp sessions (26 / 125 / 1 / 98; gaps 444 s and 655 s, then one 23 h gap), all in train. A 98- or 125-image session can go to held-out with no 300 s leakage. If the orchestrator judges that 444/655 s gaps inside one scrape are one session, call it "single session" instead. Your call.
- **eggplant/spoiled: effectively single-session; accept as "not measurable on held-out".** 368 images are the `Defected_begun_N` numbered series (train), 1 more train image, and 3 val images (a second timestamped session). A held-out slice of 3 images would measure nothing. If the rule is applied literally (3 sessions) it is a FAIL; I recommend ruling sessions under 10 images do not count.
- The 6 single-session cells (banana f+s, onion f+s, orange f+s): legitimate exception under #28 (each is one 250-image Kaggle burst or a single VegQual stem series). **Effect:** spoiled recall is N/A for apple, banana, onion, orange (and eggplant, bell_pepper unless fixed). Held-out spoiled boxes on v2 exist for **only two classes: potato (VegQual, 160 boxes) and tomato (Kaggle, 57)**. The YOLO "spoiled recall >= 0.85" and per-class spoiled-precision gates can therefore only be stated for potato and tomato; per-class precision for the rest is N/A. This meets #28 as ruled but **does not meet the original QA.md wording** ("every cell >= 10 images appears in held-out") for these cells; they have to be listed "not measurable" in every report.

## ML-16 confound (class x source, v2 verified against my own counts from labels)
Spoiled examples: apple (Kaggle only), banana (Kaggle), orange (Kaggle), potato (VegQual), eggplant (VegQual), onion (VegQual): **6 classes have spoiled from exactly one source**. bell_pepper and tomato have spoiled from two (VegQual + Kaggle). **No spoiled data at all** for lemon, egg, yogurt, bacon, milk, avocado, butter, cheese, soda (9 classes, fridge sets are fresh-assumed). Consequences: spoiled vs fresh is confounded with source for 6 classes (e.g. onion spoiled is VegQual-only and fridge/Kaggle supply the rest of the "fresh" look), and the held-out spoiled signal itself is source-pure (potato=VegQual, tomato=Kaggle). Recommend reporting spoiled recall per source.

## Class mapping spot-check
20 random label files from each of VegQual, fridge_objects, hien_fridge (compared to the raw Roboflow label file through my own class tables built from each data.yaml; null/dropped classes removed; freshness from the class name) and 20 Kaggle files (folder name = class and fresh/stale): **80/80 correct on both fwr_data and fwr_data_v2**, 0 mismatches. `class_names.json` has 17 contiguous ids matching data.yaml.

## Suites (.venv-ml, rerun after builder's final change)
ml/serve 12, ml/ocr 89, ml/yolo 11, ml/eval/tests 74 (root): all pass. New scripts have no unit tests yet.

## Notebook (train_colab.ipynb, 7 cells)
Valid JSON (nbformat 4). Secrets only via `google.colab.userdata` (ROBOFLOW_API_KEY, KAGGLE_API_TOKEN, never printed): PASS. **ML-26: fetch cell is now real** (VegQual figshare download, Roboflow `version(...).download("yolov8")` with pinned versions, Kaggle REST download behind the secret); I did not execute it (no network run), and the figshare file id is unverified. Gate cell asserts `rep["split_grouping"]=="session"` and `lk["within_300s"] == 0` from `leakage_check.py` (works with my new flat keys). Gaps: (1) **`imagehash` is not in the notebook's pip line**, so on Colab my script prints a warning and skips pHash; the gate then checks timestamps only. Add `imagehash` to cell 1 and assert per-source `phash_near_dup_pct <= 1`. (2) `REPO_URL` is still `<OWNER>/<REPO>`: a fresh run fails at clone until the owner sets it. (3) The gate does not assert the stratification rules (no held-out-only cell, required cells present).

## Secret scan
No real secret found (only placeholders/test fixtures).

## Bug status
| ID | Status |
|---|---|
| ML-21 | **fixed on fwr_data_v2** (all 4 sources pass 60/300 s and pHash). fwr_data first rework was FAIL (Kaggle 26%, builder's 0 was a parsing miss). |
| ML-23 | **open**: bell_pepper/spoiled (required, missing), apple/spoiled (judgement), eggplant/spoiled (accept as not measurable); 6 single-session cells accepted under #28 |
| ML-24 | fixed (report == manifest == disk, per source and per lighting) |
| ML-26 | fixed (real fetch cell); two new notebook gaps above (imagehash, REPO_URL) |
| ML-16 | open, quantified (6 classes spoiled from one source; 9 classes no spoiled; held-out spoiled = potato/VegQual + tomato/Kaggle only) |
| ML-15, ML-17, ML-18, ML-19, ML-22, ML-25 | open / unchanged (smoke export not regenerated for v2, skipped by instruction) |
| NEW ML-27 (medium) | hien_fridge single fixed camera/fridge: pHash 0 but 42% dHash neighbours of same-scene frames; metrics optimistic for a new fridge, report separately |

## Verdict
- **ML-21 PASS on fwr_data_v2, per source (vegqual, fridge_objects, hien_fridge, fresh_stale_fruits_veg).** The Colab leakage gate can open mechanically.
- **Stratification/coverage (ML-23) FAIL on v2** per #28: bell_pepper/spoiled must be in held-out (and apple/spoiled unless ruled single-session). Fix is cheap (move a session). Until then, QA recommends **not starting the full Colab run**; the orchestrator decides. After the fix the ML gates remain statable only for potato and tomato spoiled recall.
