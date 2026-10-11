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

---

# 2026-10-10 (final) - QA of PR #27 at head 11e76f7, data `mldata/fwr_data_v3` (rebased on main, A1 semi_fresh + pipeline in)

Rules applied: QA.md (#25, #28) plus the orchestrator's approved rulings: `--min-session-images 10` (eggplant/spoiled not measurable); apple/spoiled required via the 98-image session; train keeps >= 50% of every measurable cell; pooling of small groups with guards; pooling of complete small timestamped sessions approved; smaller held-out (813, VegQual 186) accepted. A `git log` read-only call slipped in once to check the head hash; no other git use, no feature code edited.

## Tool changes (ml/eval, mine)
- `leakage_check.py`: per-source 60/300 s rates, independent `imagehash` pHash-64/dHash-64 (Hamming <= 6, held-out originals vs train+val), numbered-series index check, and the new **pooled-unit / session assertion** `session_audit`: sessions are chained (gap <= 300 s, same source, over ALL splits); for every session holding a held-out image it asserts (1) it is not a fragment of a larger session (no train/val member) and (2) the min gap to any train/val image of that source is >= 300 s. Failure prints loudly, exits 1, and flips `criterion.timestamp_300s_zero` and `within_300s` in the JSON so the notebook gate stops. Without `imagehash` it warns and the pHash criterion is not met. 4 unit tests (`tests/test_leakage_check.py`: complete far session passes; fragment fails; 301 s passes, 300 s chains and fails; synthetic copies/other sources ignored).
- `stratification_check.py`: reads `cell_decisions` from the report and verifies them against disk and my own session reconstruction. FAILS unless: every required cell has held-out > 0 and train >= 50% (images AND boxes) and train > 0; every not-measurable cell is 0/0 in val/held-out; I also count < 2 sessions >= 10 images for each not-measurable cell; every cell >= 10 images absent from held-out is listed not-measurable; no timestamped session spans splits; report == manifest == disk (12+ checks). It also prints the val-missing and pooling-reliant cells and the single-source spoiled list. Its legacy `missing_from_heldout_required` key now follows the report decisions (what the notebook reads).
- `detection_metrics.py` (ML-18): `wilson_ci` (95%), `spoiled_recall_by_source` (per source and per source x class, real images only, with n_gt and CI), printed and written to JSON by the CLI when `--manifest` is given; `load_manifest` now carries `source`. Information only, not a gate. 3 tests with hand-derived Wilson values (0/10 -> [0, 0.2775], 10/10 -> [0.7225, 1], 50/100 -> [0.4038, 0.5962]) and a by-source test showing the synthetic copy does not add samples.

## ML-21 per source (v3, 813 held-out originals)
| Source | held-out | timestamped | within 60 s | within 300 s | min gap | pHash near-dup | pooled-unit assertion | verdict |
|---|---|---|---|---|---|---|---|---|
| vegqual | 186 | 186 (2 sessions) | 0 | 0 | 312 s | 0 (0%) | ok, no fragments | **PASS** |
| fridge_objects | 116 | 2 | 0 | 0 | 4.3e7 s | 0 (0%) | ok (2 complete 1-image sessions) | **PASS** |
| hien_fridge | 190 | 0 | 0 | 0 | n/a | 0 (0%) | n/a | **PASS** (pHash gate) |
| fresh_stale_fruits_veg | 321 | 214 (4 sessions) | 0 | 0 | 7,651 s | 0 (0%) | ok, no fragments | **PASS** |
Cross-kind check (epoch / compact / screenshot clocks merged per source): still 0 within 300 s. dHash (informational): vegqual 4.8%, fridge_objects 3.5%, Kaggle 2.8%, hien_fridge 33.7%. I viewed the flagged pairs: vegqual = potato vs a hub onion image on plain backgrounds (false positives); hien_fridge (8 more pairs here, 42 earlier) = same fixed camera/shelf with different contents, never the same shot; ML-27 stands (report hien_fridge separately, optimistic for a new fridge). The vegqual min gap (312 s) is only 12 s above the threshold, i.e. the two held-out sessions are legitimately close to a train session boundary but outside 300 s.

## Pooling: is pooling complete small timestamped sessions safe? **Yes.**
Argument and evidence: a session is a maximal chain with consecutive gaps <= 300 s, so a complete session has a gap > 300 s to the nearest same-source image on both sides; it cannot sit within 300 s of a train image. Empirically (my independent chain over all splits): the only pooled-size timestamped held-out units are 2 one-image fridge_objects sessions with a gap of ~4.3e7 s; vegqual and Kaggle held-out sessions are all >= 10 images, none is a fragment, min gaps 312 s / 7,651 s. The only residual weakness is clock-kind mixing (epoch vs compact vs screenshot): checked above, no clash. The assertion now enforces this on every run (negative-tested on a synthetic tree). Fragments (sessions < 10 images of a cell but part of a bigger session, e.g. apple/fresh 9+9, bell_pepper/fresh 7+7) are listed as `ignored_small_session_fragments` and stay with their session's split.
Audit of pooled units in `dataset_report.json`: per cell the report records big sessions, pool groups/images and units. Cells that rely on pooling alone (I count < 2 sessions of >= 10): avocado, bacon, butter, cheese, lemon (all fridge_objects, web-scraped untimestamped product photos, pools of 133-146 single-image groups, 209-414 images). For those, independence rests entirely on pHash <= 6 (0 near-dups, verified independently) and not on time. Report units agree with my session counts for the sessioned cells (e.g. milk 52 vs my 65, egg 25 vs 37: differences from my stem-based grouping; no decision depends on them). One generic-stem artefact (fridge_objects stems `Image`, `img`, `catalog_product_main` span splits) is a name collision, not a duplicate.

## Stratification (v3)
Result: **PASS** (`stratification_check.py`, 0 failures). Required cells (images train/val/held-out, train % images / boxes): apple/spoiled 151/0/97 (60.9 / 60.9), potato/spoiled 133/0/77 (63.3 / 68.3), bell_pepper/spoiled 385/153/44 (66.2 / 79.8), tomato/spoiled 257/65/66 (66.2 / 82.2), eggplant/fresh 402/137/27 (71.0 / 72.0), potato/fresh 656/0/82 (88.9 / 92.5), and the rest >= 74%. Minimum train share anywhere = 60.9%. No required cell has an empty held-out; no cell is held-out-only or val-only; eggplant/spoiled (372 images, 1 session >= 10) is entirely train = not measurable. The builder's quoted counts (potato/spoiled 166/0/77, bell_pepper/spoiled 778/158/45, ...) are **boxes** from `boxes_train_val_heldout`; images differ (near-duplicate drops removed 15 images). Not measurable (agreed): banana f+s, onion f+s, orange f+s, eggplant/spoiled.
**Thin val.** Required cells with no val image: **apple/spoiled, potato/fresh, potato/spoiled** (potato is absent from val entirely; VegQual potato has only 3 sessions: train, held-out, none for val). Val = 739 images (vegqual 137, Kaggle 299, hien 180, fridge_objects 123); val spoiled boxes only from bell_pepper (153) and tomato (65). Impact: val picks the best epoch and drives early stopping, so it cannot see potato (fresh or spoiled) or apple/spoiled; an overfit or collapse on those classes would be invisible until held-out. This does not affect the gates (held-out only) and is not a #28 failure, but it is a real weakness: new **ML-28 (medium)**. Mitigation: pick the epoch by held-out-free means (last epoch or a fixed schedule) or add a potato session to val.
**Spoiled recall is statable only here:** held-out original spoiled boxes by class/source: potato 77 (VegQual), apple 97 (Kaggle), tomato 66 (Kaggle), bell_pepper 44 (Kaggle, VegQual bell_pepper spoiled is not in held-out). No spoiled eggplant, onion, banana, orange (not measurable), and 9 classes have no spoiled data (lemon, egg, yogurt, bacon, milk, avocado, butter, cheese, soda). Spoiled sources: one source only for apple, banana, orange (Kaggle) and potato, eggplant, onion (VegQual). Held-out spoiled is 207 Kaggle boxes (3 classes) vs 77 VegQual boxes (1 class): report per source with the new Wilson CI (e.g. a 0.85 recall on n=44 has a 95% CI of roughly 0.71-0.92).

## Mapping, ML-24, suites, notebook, secrets
- Class mapping spot-check: 20 label files each from VegQual, fridge_objects, hien_fridge, Kaggle vs raw labels through my own tables: 80/80 correct on v3. Freshness codes are 0/1 only (no semi_fresh data present: `boxes_by_freshness` semi_fresh = 0).
- ML-24: report == manifest == disk (all checks equal; 813 originals, 2,081 manifest rows; per-source and by-lighting counts match).
- Suites (.venv-ml): ml/serve 14, ml/ocr 89, ml/yolo 35, ml/eval/tests 138 (was 74; now includes my 7 new tests plus the rebased ones), **pipeline CI command** (`pytest pipeline/tests -q -o python_files="test_*.py qa_*.py"`) **146 passed, 2 skipped**. No train.py/xcodebuild running.
- Notebook: valid JSON (nbformat 4, 7 cells); secrets only through Colab `userdata`; `imagehash` is now installed and imported in cell 1 (fails loudly), `REPO_URL` is set, fetch cell is real (ML-26 fixed; I did not execute it). Cell 4 asserts `split_grouping == session`, per-source `timestamp_300s_zero` and `phash_le_1pct is True`, no never-trained cells, report == disk, no required cell missing (set difference with the report's not-measurable list). My `session_audit` failure now flips the per-source `timestamp_300s_zero` flag, so the pooled-unit assertion is enforced by the notebook as it stands. Remaining gaps: `!python` does not stop on exit code 1, so the gate relies on the asserts reading the JSON; it does not read my `failures` list (50% rule, not-measurable consistency). Suggest adding `assert not st["failures"]`.
- Secret scan: nothing found.

## Bug status
| ID | Status |
|---|---|
| ML-21 | **fixed** on v3 (all 4 sources, with the pooled-unit assertion) |
| ML-23 | **fixed** per #28 + rulings (required cells present, >= 50% train, not-measurable list agreed) |
| ML-24, ML-26 | fixed |
| ML-18 | tooling done (Wilson CIs per source, tested); thin cells remain thin |
| ML-16 | open, quantified (6 classes with one-source spoiled; 9 with none; held-out spoiled = Kaggle 3 classes + VegQual potato) |
| ML-27 | open (hien_fridge single fixed camera) |
| ML-28 (new, medium) | val has no potato and no apple/spoiled; early-stopping blind to them |
| ML-15, 17, 19, 22, 25 | open / unchanged (smoke export not regenerated; real low/warm lighting still not measurable) |

## Verdict for #27
- **ML-21 (QA.md #25 + pooled-unit assertion): PASS for vegqual, fridge_objects, hien_fridge, fresh_stale_fruits_veg.**
- **Stratification / coverage (#28 + rulings): PASS.**
- Suites: PASS. Notebook: PASS with the two gaps above. Secrets: clean.
- **#27 = PASS** (dataset-readiness only; no YOLO metric exists yet). **The Colab gate can open**: leakage, pHash, pooled-unit and stratification checks all pass on v3 and the notebook asserts them. Conditions to carry into the metrics: report hien_fridge separately; report spoiled recall per source with CIs and only for potato, tomato, apple (Kaggle) and bell_pepper (Kaggle); real low/warm lighting stays not measurable.

---

# 2026-10-10 - QA of PR #33 (`chore/colab-last-pt`): Drive checkpointing + resume

Ultralytics 8.4.175 (`mldata/.venv-train`), device mps, yolo26n / yolo26n-cls, 62-image synthetic set (builder's fixture), `--epochs 3 --cls-epochs 3`, SIGKILL via a poller. Notebook cannot run here (no Colab); its restore/stamp logic was simulated in plain Python.

| # | Item | Result |
|---|---|---|
| 1 | Ultralytics semantics (source read) | **PASS**, with one refinement (ML-35) |
| 2 | Detector kill in epoch 2, resume | **PASS** |
| 3 | Classifier kill in epoch 2, resume (detector skipped) | **PASS** |
| 4 | Truncated `last.pt` -> `best.pt` -> fresh | **PASS** (duplicate-row side effect, ML-34) |
| 5 | Crash after last epoch, before `final_eval` | **PASS** |
| 6 | Notebook logic | **PASS with 1 medium finding (ML-33)** and a low one (ML-36) |
| 7 | Suites | **PASS** (serve 14, ocr 89, yolo 35, eval 138) |

## 1. Source claims (engine/model.py L877-886, trainer.py `check_resume` L1020, `resume_training` L1124, torch_utils `strip_optimizer` L897)
- Resume needs `epoch >= 0` and an optimizer: **confirmed** (`self.ckpt.get("epoch", -1) >= 0 and self.ckpt.get("optimizer") is not None`, else warning and `args["resume"] = False`).
- Finished run has `epoch == -1`: **confirmed** (`strip_optimizer`: `x["epoch"] = -1`, optimizer/ema/scaler = None; called by `final_eval` on last.pt and best.pt).
- results.csv appended: **confirmed** (`self.csv.unlink()` only `if not self.args.resume`; `save_metrics` opens with `"a"`).
- "Finished run raises if resumed": **only half true (ML-35).** Run empirically:
  - stripped checkpoint (`epoch == -1`): `WARNING ... is not a resumable training checkpoint ... Starting new training instead.` No exception, a brand-new training starts.
  - complete but unstripped (`epoch = epochs-1`, optimizer present): `AssertionError: ... training to 3 epochs is finished, nothing to resume.`
  - `train.py` handles both before calling `train(resume=True)`, so no impact; only the docstring/ML.md wording is wrong.
- Epoch indexing checked: ckpt `epoch` is the 0-based index just completed; `start_epoch = epoch + 1`; `ep + 1 >= total` in `ckpt_status` is the right "complete" test.

## 2. Detector kill/resume (PASS)
Kill at csv rows == 1 and `last.pt` present (`last.pt` epoch idx 0, optimizer True). Rerun:
```
[det] resuming .../runsA/det/weights/last.pt: last completed epoch 1 of 3
Resuming training ... from epoch 2 to 3 total epochs
det resumed; val on last: 0.2704...
```
results.csv epochs: `1,2,3` (no duplicates). Classifier trained fresh afterwards, export written.

## 3. Classifier kill/resume (PASS)
Finished detector copied in, cls killed after epoch 1 saved (`cls last epoch 0 opt True`, cls csv rows `1`). Rerun:
```
[det] already finished (...runsB/det/weights/last.pt); skipping training
det skipped; val on last: 0.2704...
[cls] resuming .../runsB/cls/weights/last.pt: last completed epoch 1 of 3
Resuming training ... from epoch 2 to 3 total epochs
cls resumed
```
cls results.csv: `1,2,3`.

## 4. Truncated last.pt (PASS)
- `head -c 1000 last.pt`, best.pt intact (epoch idx 0): `last.pt unreadable (RuntimeError: PytorchStreamReader failed reading zip archive...)`, `[det] last.pt unreadable, trying best.pt`, `[det] resuming ...: last completed epoch 1 of 3`, finishes, rc 0, no crash.
- Both last.pt and best.pt truncated: `[det] last.pt unreadable, trying best.pt` -> best.pt unreadable -> `[det] no usable checkpoint (corrupt); training from scratch`, `det fresh`, rc 0. The fresh run unlinks the old results.csv (rows 1,2,3 clean).
- **ML-34 (low):** the resumed run appends to results.csv even when the checkpoint is older than the csv. Reproduced twice: (a) kill landed after epoch 2's csv row but before its `last.pt` save (`save_metrics` runs before `save_model`), then resume redid epoch 2: csv `1,2,2,3`; (b) best.pt (epoch 1) used as fallback while csv already had epoch 2: `1,2,2,3`. Nothing in `ml/` or the export reads results.csv, so it is cosmetic, but ML.md 5a's "no duplicates" only holds when the kill falls between a completed save and the next csv write. Doc note suffices.

## 5. Crash between last epoch and final_eval (PASS)
Took a mid-training checkpoint, set `epoch = 2` (epochs=3) on both last.pt and best.pt, optimizer kept. Rerun: `[det] already finished (...); skipping training`, `det skipped; val on last: 0.189...`, classifier fresh, export written. After: `epoch -1 opt None` on last.pt (train.py stripped it). Confirms the reasoning that without this branch `train(resume=True)` would raise the AssertionError above.

## 6. Notebook (static review + simulation)
JSON valid (nbformat 4.5, 7 cells; all code cells parse as Python once `!`/`%` lines are stubbed; `nbformat` itself not installed).
- Drive required: PASS. `raise SystemExit("STOP: Google Drive is required ...")` on mount exception, plus a second check for `/content/drive/MyDrive`. Either way cell 2 would NameError on `DATA_ON_DRIVE`, so Run-all cannot proceed.
- RUN_ID field: PASS (`#@param`, placeholder -> today, regex `[A-Za-z0-9_.-]+`). Nit in ML-36: `.` and `..` match the regex.
- Stamp / commit marker (simulated with the notebook's own `sha_stamp` and `DATA_ON_DRIVE` expression on a fake Drive):
  - clean cache -> True, restore extracts 58/58 images
  - `.sha256` missing -> False (re-prepare)
  - tar truncated after commit -> False (size differs; re-prepare)
  - small `dataset_report.json` copy edited -> False
  - same-size bit flip in the tar -> True (the stamp does not detect it; accepted limitation, it would show up as a tar/gate error)
  - **tar creation fails midway and the notebook ignores the exit status -> True and the partial tar is restored (ML-33).**
- Gates run on the restored copy before training: PASS (the gate block in cell 4 is outside the `if DATA_ON_DRIVE`; both branches reach it; training only starts in cell 5). Training reads `/content/fwr_data` (local), not Drive. Cell 5 is `train.py --data /content/fwr_data ... --weights last --resume --project "{RUN_DIR}"`: PASS. Cell 6 zips from `{RUN_DIR}/export`: PASS.
- Partial restore vs. the gates (real v3 data, 38,931 files, hardlinked copy with 40% of the .jpg removed): `stratification_check.py` fails 17 "report vs manifest ... == disk" checks, so the notebook's `assert not st["failures"]` stops training. Good. But the gates only count `images/*`; `labels/`, `freshness/` and `cls/` are not counted, so a tar cut after `images/` passes (see ML-33).

## Bugs
- **ML-33 (medium) - notebook ignores `!tar` exit status; a partial tar can be committed and later restored.** Cell 4 `!tar ... -cf "{DRIVE_TAR}.part"` (disk full, Drive quota, Drive I/O error) does not raise; the next lines still `os.replace` the short `.part`, copy the small files and write a `.sha256` that matches the short tar (reproduced: tar rc 1, `DATA_ON_DRIVE -> True`, restore gave 12 of 58 images, `tar -xf` rc 1 also ignored). On the resumed run the gates catch missing images (counts) but not missing `labels/`, `freshness/` or `cls/` files, so a cut that spares `images/` trains on images with no labels. Fix: run tar with `subprocess.run(..., check=True)` (or `%%bash` with `set -e`) for both create and restore; verify the cache before writing the stamp (`tar -tf` succeeds, or store file count in the stamp and compare after extract); also have the gate block compare `labels/<split>` and `cls/` file counts with the report.
- **ML-34 (low)** - duplicate epoch rows in results.csv after resume from a stale checkpoint (above). Fix: doc note ("no duplicates" is not guaranteed), or dedupe csv by epoch after a resume.
- **ML-35 (low, doc)** - `ckpt_status` docstring and ML.md 5a say a finished run "raises" on resume. Stripped (`epoch == -1`) silently starts a new training with a warning; only complete-but-unstripped raises. Worth stating because it is the failure mode if `ckpt_status` is ever bypassed (silent retrain into the same folder, overwriting the finished weights).
- **ML-36 (low)** - (a) `r = !python leakage_check.py --json /content/leakage.json` ignores the exit code; if the check crashes on a re-run in the same VM, the previous run's json is read and the assert passes (same for `strat.json`). Delete both files before each check. (b) `RUN_ID` of `.` or `..` passes the regex and resolves RUN_DIR to `fwr_runs` or `MyDrive`; use `[A-Za-z0-9][A-Za-z0-9_.-]*` and reject `..`.

## Environment notes
`mldata/fwr_data_v3` disappeared while I was working (another session's data rebuild; `fwr_data_a2` remains). I only deleted hardlink copies inside my own scratch dir. Item-6 gate runs used v3 before it vanished. The builder's `resume_test/` is untouched.

## Verdict for #33
- Resume logic in `train.py`: **PASS** on all five scenarios (detector, classifier, truncated last, truncated both, crashed-before-final_eval) with no crash and no restart where a resume was possible.
- Notebook: **PASS conditional on ML-33.** It is a robustness hole (needs a failing tar), not a correctness bug on the happy path; recommend fixing it before the 3-4.5 h run, since this is the exact scenario (Drive trouble) the feature exists for. ML-34..36 are low and can be doc/one-line fixes.

## Re-verification of the ML-33..36 fixes (PR #33, same day)
Method: executed the notebook's own code (cell 1 helper functions, cell 4 restore and create blocks, extracted from the .ipynb and run against a fake Drive with `/content` redirected; a shadow `tar` on PATH injected the failures). My own cases, not the builder's `sim.py`.
| Case | Result |
|---|---|
| clean create then restore | PASS: stamp JSON `{counts{cls 33,freshness 86,images 86,labels 86}, report_sha256, tar_bytes, tar_members 316}`; `DATA_ON_DRIVE` True; restore re-count matches |
| tar exits non-zero after leaving a partial archive | PASS: `CalledProcessError`; `.part` removed, no tar, **no stamp** |
| archive silently cut after `images/` (rc 0) | PASS: `AssertionError: archive file counts {'images': 86, 'labels': 0, 'freshness': 0, 'cls': 0} differ from the dataset ...`; `.part` removed, no stamp |
| byte-truncated archive (rc 0) | PASS: `ReadError: unexpected end of data`, no stamp |
| stamp missing / old `hash:size` stamp | PASS: `DATA_ON_DRIVE` False |
| tar truncated after commit | PASS: size mismatch, False |
| same-size bit flip | accepted limitation: True, extract still succeeded (as before) |
| stamp counts tampered (restore mismatch) | PASS: `SystemExit: STOP: restored dataset does not match the Drive stamp ...`, stamp deleted |
| restore `tar -x` exits 2 | PASS: `CalledProcessError` (no longer ignored) |
- **ML-33: FIXED.** **ML-36: FIXED.** `run_check()` removes the json first and asserts exit code 0 and that the json exists (read in code; subprocess with `sys.executable`). `RUN_ID` regex `^[A-Za-z0-9][A-Za-z0-9_-]*$`: accepts `fwr_20261010`, `ok-1_2`; rejects `..`, `.`, empty, `a.b`, `-x`.
- **ML-35: FIXED** (train.py docstring and ML.md 5a now separate the unstripped-raises and stripped-silently-retrains cases). **ML-34: FIXED as documentation** (ML.md 5a caveat: duplicate epoch row after a kill between csv write and `last.pt` save or a `best.pt` fallback; dedupe by `epoch`).
- Notebook is valid JSON (all code cells still parse); `ml/yolo` tests 35 passed.

**Final verdict for #33: PASS.** (Open, accepted: a same-size bit flip inside the tar is not detected by the stamp.)

# 2026-10-10 (evening) - ML QA for PR A2 (`feat/semi-fresh-data`, draft #31): AgriFreshNET as 5th source

Tools (mine, `ml/eval/`): `leakage_check.py` (AgriFreshNET added to `SOURCES`; the compact-timestamp regex accepts the 3 millisecond digits of `IMG_YYYYMMDD_HHMMSSmmm`, which the first build's grouping missed); `stratification_check.py` is main's #27 version plus one change (freshness codes 0/1/2 map to fresh/spoiled/semi_fresh; it used to count code 2 as spoiled); **new `variant_dup_check.py`** (pHash of the 8 dihedral variants, min distance; held-out to train+val, val to train, within-set augmentation rate, specimen components) with `tests/test_variant_dup_check.py` (flip / rot90 / rot270 / flip+rot90 copies are caught; 5 cases, run by hand in qa-venv because venv-ml has no `imagehash`, so they skip in venv-ml). Hashing ran only while no `prepare_dataset` was running. **The dataset moved under me four times** (fwr_data_a2 built 19:35, 19:46, 19:51, 19:55; then fwr_data_a2b at 20:05); I re-ran every check on each build. **Final verdict is on `fwr_data_a2b`.**

## Build history (what the earlier builds got wrong, kept as the "before")
| build | finding |
|---|---|
| a2 #1 (spec grouping only, 13,879 AgriFreshNET originals) | **ML-21 FAIL on AgriFreshNET: 884 / 1,157 timestamped held-out images (76%) within 60 s of a train/val image, 887 within 300 s, min gap 0 s.** Cause: grouping was by pHash specimen, never by time, and `parse_capture_time` ignored milliseconds. Same original photo (same stamp, different `spec_` id) in train and held-out for 35 stems. Also **potato/spoiled train 6 / val 74 / held-out 123 images** (train not the majority) and papaya/semi_fresh forced all-to-train. |
| a2 #2 | potato/spoiled recut (train 133); time leak unchanged (887 within 300 s). |
| a2 #3 (session grouping across classes, 13,848 AgriFreshNET, aug_ copies still in) | ML-21 PASS (0 within 300 s, min gap 383 s, pHash 0.58%); stratification PASS. Variant-aware: **92.4% of AgriFreshNET images have a <= 6 near-duplicate (any split)**, 38 such pairs straddle splits. Cross-stage same-class <= 6: 4.9% vs 2.8% same-stage (held-out). |
| **a2b (final)** | below |

## fwr_data_a2b: per area
**1. Specimen grouping: PASS with caveats (cross-stage overlap is measured, not gated, per ruling A).**
- `aug_` files: **none.** All 4,754 staged AgriFreshNET files were checked by MD5 against the zip: 0 are only available under an `aug_` name (13 share bytes with an `aug_` name but also with an original). 4,674 AgriFreshNET originals reach the dataset.
- Cap (300 per class x freshness, ruling B): 24 cells, **max 298, min 45** (cucumber spoiled 45 and papaya semi_fresh 48 have fewer non-augmented files than the cap; bitter_melon semi 101, orange fresh 114, papaya fresh 114, pineapple semi 119 follow). 0 cells at exactly 300 (the 300 cap was applied before the pHash purge and the splits). Spread (my time-session count per cell, which includes every source in the cell): orange/semi_fresh 128 sessions, pineapple/semi_fresh 67, eggplant/semi_fresh 29, tomato/semi_fresh 22, banana/semi_fresh 10, bitter_melon/semi_fresh 9, cucumber/semi_fresh 8, papaya/semi_fresh 6. I did not verify the round-robin order itself, only that each cell spans several sessions and all three splits.
- Share of train: AgriFreshNET 3,539 of 10,385 (34.1%, down from about 60%).
- Augmentation duplicates: **within-set <= 6 variant rate 27.4%** (was 92.4% with aug_ copies in), 123 pairs straddle splits (see gate below); fridge_objects 5.6%, Kaggle 26.6%, hien_fridge 67.6% (same fixed fridge; all in-split, 0 straddle), vegqual 89.4% (stem-group series, 0 straddle).
- **Cross-stage specimen overlap (held-out and val vs train; same class; dihedral min distance):**

| | held-out <= 6 | <= 8 | <= 10 | val <= 6 | <= 8 | <= 10 |
|---|---|---|---|---|---|---|
| same class, any stage | 4.7% | 25.6% | 49.8% | 4.2% | 20.1% | 41.4% |
| same class, **other stage** than the query | 2.5% | 14.5% | 33.2% | 2.8% | 10.0% | 27.1% |
| same class, same stage | 2.7% | 17.4% | 39.3% | 2.2% | 14.5% | 31.5% |
| **different class (noise floor)** | 3.8% | 18.6% | 49.9% | 5.0% | 20.9% | 46.4% |

  The noise floor is as high as the same-class rate: at <= 10 pHash on this cloth-on-white background cannot tell a specimen from any other round fruit, so the "<= 10 across stages" figure is **saturated and not usable as an overlap rate** (it is what made the builder's giant components). The honest reading is that cross-stage overlap is **not detectable above noise** at the pHash level after the aug_ copies were removed (a2 #3 was 4.9% other-stage vs 4.3% floor, with the aug_ copies in). I eyeballed 8 same-class d <= 6 pairs and 8 d = 8 cross-stage pairs from a2b (side by side): **1 or 2 of 16 plausibly the same physical item** (a decaying bitter melon with the same curly stem, held-out rotten vs train semi); the rest are different specimens of the same produce (different tomatoes, different melons). The same exercise on a2 #1/#3 gave roughly half of pairs that look like the same specimen at two ages (papayas with the same ridge, an orange with identical dimples, a banana, a cucumber), so the aug_ exclusion and the cap did remove most of it. **Residual risk, not zero:** WhatsApp-named (`IMG-YYYYMMDD-WAnnnn`) and `Banana_3`-style files have no parseable time and fall back to pHash components at 4 to 8, which cannot link a fresh and a rotten photo of one item. Label every AgriFreshNET and semi_fresh metric "cross-stage specimen overlap possible".

**2. Leakage (ML-21), per source, a2b: PASS on the QA.md criterion as measured by `leakage_check.py`; the literal dihedral-variant gate does NOT pass (see ML-40).**

| source | held-out | with ts | within 60 s | within 300 s | min gap | pHash <= 6 (identity) | dHash (info) | **variant pHash <= 6** (held-out to train+val) | val to train |
|---|---|---|---|---|---|---|---|---|---|
| agrifreshnet | 633 | 398 | 0 | **0** | 383 s | 6 = **0.95%** (<= 1%) | 4.9% | **47 = 7.4%** | 8.6% |
| fresh_stale_fruits_veg | 313 | 199 | 0 | 0 | 7,651 s | 0 | 3.8% | 17 = 5.4% | 6.8% |
| fridge_objects | 114 | 1 | 0 | 0 | n/a | 0 | 3.5% | 0 | 0 |
| hien_fridge | 180 | 0 | 0 | 0 | n/a | 0 | 45.6% (same fridge, see ML-27) | 0 | 0 |
| vegqual | 216 | 216 | 0 | 0 | 312 s | 0 | 2.8% | 0 | 0 |

  The identity-hash AgriFreshNET margin is **0.95% against a 1% limit** (6 of 633), one image from failing. The variant gate (min over 8 dihedral variants, which makes 8 chances per pair) fails on AgriFreshNET and Kaggle. Cause: false positives from near-uniform backgrounds. In a2b the same-class rate at d <= 6 is 4.7% against 3.8% for different classes (a tomato "matching" a bitter melon is a false positive by construction), and 6 of the 8 same-class pairs I viewed were different objects. Kaggle's flags are the black 45-degree rotation padding (corners dominate the hash): of 8 pairs viewed on a2, about 5 were a green pepper vs a red tomato and 1 to 2 were the same pepper at two ages. I do **not** call this leakage, but I also cannot make the literal ruling pass; **orchestrator to rule** whether the variant gate should be same-class-only and/or computed on the central crop (ML-40). Within-set, 123 variant pairs <= 6 straddle splits for AgriFreshNET; I did not split these into same-class and cross-class, so treat them as an upper bound.

**3. semi_fresh (informational only, no gate). PASS (nothing held-out-only; one cell is thin).** images train / val / held-out (a2b), my own counts from disk and agreeing with the report:

| class/semi_fresh | train | val | held-out | sessions |
|---|---|---|---|---|
| banana | 154 | 21 | 17 | 10 |
| bitter_melon | 63 | 9 | 29 | 9 |
| cucumber | 206 | 6 | 11 | 8 |
| eggplant | 232 | 11 | 11 | 29 |
| orange | 217 | 41 | 40 | 128 |
| papaya | 29 | 2 | 17 | 6 |
| pineapple | 90 | 18 | 11 | 67 |
| tomato | 212 | 38 | 37 | 22 |

  No semi cell is held-out-only or val-only; every one has train. All 8 are "required" under the ruling (>= 10 images and >= 2 units) and all 8 have held-out images, so all are measurable, but five of them have <= 17 held-out images (banana 17, cucumber 11, eggplant 11, pineapple 11, papaya 17; papaya is also train-poor at 29): the precision/recall will be noisy. On the discarded a2 #3 (aug_ copies in) these cells were about 3 to 5 times larger; dropping aug_ copies and the cap is why they are small.

**4. Class mapping: PASS.** Not 20 but **all 4,674 AgriFreshNET originals**: each a2b image was matched to its staged file and then, by MD5, to its zip member; folder label to (class, freshness) was recomputed independently (`Fresh/Semi fresh/Semi_Fresh/Rotten` to fresh/semi_fresh/spoiled, `Bittermelon` to bitter_melon, cucumber maps to the existing `cucumber` class) and compared with the label file and the freshness sidecar: **4,674 / 4,674 correct** (also 13,879 / 13,879 on the earlier a2). Sidecar codes in the AgriFreshNET files (including synthetic copies) are exactly **{0, 1, 2}** (1,901 / 2,119 / 1,860). `class_names.json` has 21 ids (papaya 18, pineapple 19, bitter_melon 20 appended).

**5. ML-16 confound: still open, now partly mitigated.** Fresh AND spoiled come from AgriFreshNET plus another source for **banana (Kaggle), eggplant (VegQual), orange (Kaggle), tomato (VegQual, Kaggle, fridge_objects fresh_assumed)**. **semi_fresh comes only from AgriFreshNET for all 8 classes.** AgriFreshNET is the *only* source of fresh/spoiled for **bitter_melon, cucumber, papaya and pineapple**, so "spoiled" for those four is fully confounded with the source. Spoiled from one source only: pineapple, papaya, bitter_melon, cucumber (AgriFreshNET), apple (Kaggle), onion, potato (VegQual). No spoiled at all: lemon, butter, bacon, yogurt, milk, avocado, egg, cheese, soda. The binary YOLO gates therefore still can only be claimed per source, and any AgriFreshNET-only class is a studio-cloth domain.

**6. Licence and attribution: PASS.** CC BY 4.0, DOI 10.17632/42m5tb7yv9.1, authors, URL: in `pipeline/ingestion/agrifreshnet.py` (header + `LICENCE`, `URL`, `DOI`, `CITATION`), `docs/ML.md` (Attributions, and the sources table) and `docs/PIPELINE.md` (table + Attributions). `sources.json` has licence and url.

**7. Suites (rebased head): PASS.** venv-ml, from `ml/`: serve 14, ocr 89, yolo 56 (includes `test_capture_time.py`); `ml/eval/tests` from the root 138 passed, 1 skipped; pipeline CI command 164 passed, 2 skipped. **The 3 failures known from #27 are gone after the rebase** (I saw them on the pre-rebase tree: `test_no_group_straddles_splits`, `test_prepare_semi_fresh_class`, `test_variants_labels_and_counts`, empty val split). **Parser parity test** (`ml/yolo/tests/test_capture_time.py`) passes: 14 formats parsed by both parsers (including the millisecond forms), 5 non-time names ignored by both, and the gaps agree. It imports my `leakage_check.stamp`; it covers the regex change I made, so a future edit there must keep it green. Note both parsers still ignore `IMG-YYYYMMDD-WAnnnn`.

**8. Secret scan: clean** (only `FAKE_KEY = "AIzaSy-FAKE-KEY..."` in `backend/tests/test_gemini_usage.py`, a test sentinel).

**Stratification (main's checker + my 3-class fix): PASS, FAILURES none**, report-vs-manifest 0 mismatches. Not measurable: onion/fresh and onion/spoiled (one session, 234 / 177 images). Required cells with no val image: apple/spoiled, potato/fresh, potato/spoiled (info). Cells that rely on pooling rather than 2 sessions of >= 10: avocado, bacon, butter, cheese, lemon fresh, orange/spoiled, pineapple fresh/semi/spoiled (they have many tiny sessions; the pool rule counts them). No cell is present only outside train. potato/spoiled train is 133 of 207 images (64%).

## Bugs (ML-38..41; renumbered from QA's ML-33..36, which collided with #33's IDs)
| ID | Sev | Summary | Status |
|---|---|---|---|
| ML-38 | **high** | a2 #1/#2: AgriFreshNET held-out images within 300 s of train/val images (887 of 1,524 timestamped, min gap 0 s): specimen grouping ignores capture time and `parse_capture_time` ignored `IMG_..._HHMMSSmmm`. 35 original photo stems also straddled splits | **fixed in a2b** (0 within 300 s; parser parity test) |
| ML-39 | high | a2 #1: potato/spoiled train 6 / val 74 / held-out 123 images (train minority, model effectively untrained on it), papaya/semi_fresh sent all to train as "not measurable" despite 6 sessions | **fixed in a2b** (train 133 / val 0 / held-out 74; papaya semi measurable) |
| ML-40 | medium | The literal dihedral-variant pHash <= 6 gate fails on AgriFreshNET (7.4%) and Kaggle (5.4%) even after aug_ removal, because min-over-8-variants on plain / padded backgrounds yields false positives (cross-class floor 3.8%). Identity pHash for AgriFreshNET is 0.95% (limit 1%, thin margin). Needs a ruling: gate on same-class pairs and mask the Kaggle rotation padding, or accept identity hash + this report | **open, orchestrator** |
| ML-41 | low | semi_fresh held-out cells are small after the cap (11 to 40 images; banana 17, cucumber 11, eggplant 11, pineapple 11, papaya 17), potato fresh/spoiled and apple/spoiled have no val; metrics will be noisy | open (informational) |
| ML-37 | low | `stratification_check.py` (main) counted freshness code 2 (semi_fresh) as spoiled, merging semi into spoiled cells | **fixed** (3-class mapping in `ml/eval`) |
| ML-27 | medium | (unchanged) hien_fridge dHash 45.6%: same fridge, rearranged items | open |

## Verdict (fwr_data_a2b)
- **Specimen grouping: adequate for training and for informational reporting; not a clean guarantee.** Session grouping across classes removed the time leak; the aug_ exclusion and the cap removed the augmented-copy overlap; what is left is cross-stage specimen overlap on untimestamped (WhatsApp, `Banana_3`) files, which pHash cannot measure above the noise floor, and about 1 in 8 eyeballed borderline pairs looked like one item at two ages. It is **not** adequate on a2 #1/#3 (time leak and aug_ copies).
- **ML-21 on a2b:** timestamp and identity-pHash criteria **PASS for all 5 sources**; the literal dihedral-variant gate **FAIL** for AgriFreshNET (7.4%) and Kaggle (5.4%) on false positives (ML-40, needs a ruling). A model trained on a2b may be quoted per source with AgriFreshNET / semi_fresh labelled "cross-stage specimen overlap possible".
- **PASS:** class mapping, licence, suites, secret scan, stratification (main's check), semi_fresh cells present. **FAIL (pending ruling):** variant-aware gate (ML-40).

# 2026-10-10 (night) - ML QA for PR #31 (`feat/semi-fresh-data`): Colab dry run, semi_fresh training path, ML-40 reporting

Scope: the notebook changes (AgriFreshNET download + ingest, `DRY_RUN`, `make_subset.py`, `SEMI_FRESH_THRESHOLD`, cls assert), the dry-run training path on MPS, the suites, and my own `ml/eval` changes for the ML-40 ruling. Baseline for the notebook diff: **main's notebook predates #33** (no `run_check`, no stamp), so I diffed against the #33 notebook (`wt/colab`, which carries the #33 safety code) as well as against main.

## Part 1: results per item
| # | Item | Result |
|---|---|---|
| 1 | Notebook valid JSON, 7 cells, all code cells parse (with `!`/`%` stubbed). Against #33's notebook the diff is only: `DRY_RUN`, `CACHE_DIR`/`RUN_DIR` split, pipeline requirements, cell 3d, cls assert, `SEMI_FRESH_THRESHOLD`, dry branch of cells 5 and 6. **Nothing from #33 dropped:** `tar` create and extract are `subprocess.run(..., check=True)`; `.part` removed on any exception; archive re-read with `tar_counts` and compared with `dir_counts` before the stamp; stamp (`DRIVE_SHA`) written last; restore re-counts and compares the stamp and the report bytes, invalidating the stamp on mismatch; `run_check` deletes the json, asserts exit 0 and that the json exists; RUN_ID regex `^[A-Za-z0-9][A-Za-z0-9_-]*$`; Drive required. | **PASS** |
| 2 | Dry-run isolation. `CACHE_DIR = fwr_runs/<RUN_ID>` holds tar, stamp and small copies (shared); `RUN_DIR = CACHE_DIR + "_dry"` only when `DRY_RUN`, and it is the only thing passed to `--project`. Dry checkpoints therefore live in `<RUN_ID>_dry/`; a real run with the same RUN_ID has an empty `<RUN_ID>/det`, so `train_stage` goes "no usable checkpoint -> from scratch" (nothing to skip or resume). The dataset cache is found by the stamp (`DATA_ON_DRIVE`), so a dry run followed by a real run restores from Drive without re-downloading. **The gates (cell 4) are not conditional on `DRY_RUN`**: they run in both modes, on the freshly built or the restored copy, before the dry-run branch of cell 5. Real-mode cell 6 is unchanged. Weakness: ML-44 (`_dry` suffix collision). | **PASS** (ML-44 low) |
| 3 | The AgriFreshNET cell is inside `else:` of `if DATA_ON_DRIVE` (skipped on restore). The ingest uses `subprocess.run(..., check=True)`; the size assert (> 300 MB; real size 347,828,971) and the SHA-256 `assert` stop the run on a mismatch. The flags are right (`--data-root` before the sub-command, `--specimen-groups --exclude-source-augs --max-per-cell 300 --drop-raw`; `ingest_report.json` is written last, `source.json` before it, the `curation.before/after` keys exist, matching my local a2b staging with 4,754). **But the download itself fails: see ML-42.** The public API does return `sha256_hash` (`6607a48b...`) and the filename `Processed Data.zip` matches. | **FAIL** (ML-42) |
| 4 | `make_subset.py` on `fwr_data_a2b` (stride 20): two runs give identical stats and an identical symlink set. Subset: train 520, val 63, heldout 197 (of 10,385 / 1,243 / 3,938); cls/train fresh 308 / semi_fresh 61 / spoiled 280, cls/val 19 / 8 / 21 (3 classes in both); detector classes 21 of 21 in train, 20 of 20 in held-out. Every image has its label and freshness file with the same stem; all symlinks resolve; `heldout_gt.jsonl` (197 lines) and `heldout_manifest.csv` (197 rows) match the chosen held-out images exactly; freshness codes in the sidecars equal the `freshness` in the GT lines (0 mismatches of 197); `data.yaml` `path:` rewritten. Scratch dir deleted. | **PASS** |
| 5 | Dry-run training on MPS (yolo26n + yolo26n-cls from `mldata`, `--epochs 1 --cls-epochs 1 --batch 8 --resume --semi-fresh-threshold 0.4`, `.venv-train`): rc 0 in 55 s; classifier saw 649 train / 48 val images in **3 classes**; export has `detector.pt freshness.pt predictions.jsonl heldout_gt.jsonl heldout_manifest.csv class_names.json dataset_report.json`; **`predictions.jsonl` has 197 lines, 556 predictions: fresh 478, semi_fresh 75, spoiled 3** (the 1-epoch model, so the numbers mean nothing, but the threshold plumbing and the 3-class output work). A second invocation with the same project printed `[det] already finished ... skipping` / `[cls] already finished` and re-exported, as designed. No `train.py` was running before; the 32 MB scratch dir is deleted. | **PASS** |
| 6 | Suites: `ml/yolo` **60 passed**; `ml/serve` 14; `ml/ocr` 89; `ml/eval/tests` 143 passed, 1 skipped (the variant tests skip without `imagehash`; the 9 of them pass in `.venv-train`); pipeline CI command **164 passed, 2 skipped**. | **PASS** |

## Part 2: ML-40 eval reporting (my code, `ml/eval/`)
**`variant_dup_check.py` is now report only (always exit 0, no `criterion` field) and the notebook does not call it** (grep: 0 mentions in the notebook; the cell-4 gate is identity pHash <= 6 from `leakage_check.py`).
- Same-class only: the class comes from the YOLO label files (a pair counts when the two images share a class id; images without labels share the key `?`).
- Padding: black rotation padding (3 or 4 black corners and 2-60% black pixels) is filled with the mean colour of the rest of the image, then only the **central 80%** is hashed (`--crop`, `--no-mask`). Cache keyed on these settings.
- Noise floor next to each rate: the nearest different-class image from a random subset of different-class references **the same size** as that query's same-class reference set (seeded), plus the unmatched all-different-class rate, and the excess in points. A same-class rate that is equal to the floor is background similarity, not duplication.
- Tests (`tests/test_variant_dup_check.py`, 9): flip / rot90 / rot270 / flip+rot90 copies are caught as same-class; unrelated images not; a rotated copy in a different class is not a same-class hit but is the floor; padding masked (2 images) and an ordinary image untouched; crop size; CLI returns 0 on a 100% duplicate.

**Re-run on `fwr_data_a2b` (held-out -> train+val, T = 6, central 80%, padding masked, same class):**
| source | held-out | same-class <= 6 | different-class floor (size-matched) | floor (all different-class refs) | excess (points) | identity-only same class | padding masked | within-set same-class | within-set pairs straddling splits |
|---|---|---|---|---|---|---|---|---|---|
| agrifreshnet | 633 | **4.90% (31)** | 1.11% | 3.63% | **+3.79** | 1.74% | 0 | 17.4% | 79 |
| fresh_stale_fruits_veg (Kaggle) | 313 | **0.32% (1)** | 0.0% | 0.0% | +0.32 | 0.0% | 1,999 of the source's images | 21.0% | 7 |
| fridge_objects | 114 | 0.0% | 0.0% | 0.0% | 0 | 0.0% | 11 | 5.8% | 0 |
| hien_fridge | 180 | 5.56% (10) | 0.0% | 0.0% | +5.56 | 5.56% | 0 | 65.7% | 1 |
| vegqual | 216 | 1.85% (4) | 0.46% | 1.39% | +1.39 | 1.39% | 13 | 88.7% | 1 |
- **Kaggle: 5.4% (old, all-class, unmasked) -> 0.32%.** The flags were the rotation padding and cross-class matches, as I said in the a2b verdict (ML-40). Val -> train: Kaggle 1.0% against a floor of 0.0%.
- **AgriFreshNET is not noise: 4.9% against a size-matched floor of 1.1%** (val -> train 5.0% against 0.4%). I looked at 10 random same-class d <= 6 pairs: 3 look like the same item or the same shot (an orange, a green orange, a tomato from a slightly different angle), 7 are different specimens of the same produce in the same pose on the same cloth. So there is a real, small, same-class residual of roughly 10 held-out images that I cannot call clean, consistent with the "cross-stage specimen overlap possible" label (and the within-set number 17.4% shows how much of the source is still near-duplicate series). It stays reported, not gated, per the ruling. The gate itself is unchanged: identity pHash for AgriFreshNET was 0.95% (6 of 633) on the full image, still one image from the 1% limit; on the central 80% crop the same-class identity-only rate here is 1.74%, which is a different hash, not a gate result.
- hien_fridge 5.56% is its multi-object fixed-camera scenes (same class set, same fridge; ML-27/ML-32), as before. VegQual 1.85% is mostly stem-group series from the same plant.
- Raw output: `scratchpad/var2_a2b.json`.

**`detection_metrics.py` (semi_fresh Wilson CIs, information only, no gate):** each class in `freshness_3way` now carries `precision_ci95` and `recall_ci95` (Wilson on tp / n_pred and tp / n_gt, `[None, None]` when the denominator is 0); new `semi_fresh_by_source(...)` gives semi_fresh precision and recall with CIs overall and per source from `--manifest`, real images only (synthetic copies excluded, as for spoiled recall by source); `main` prints both with "NOT a gate". 6 new tests in `test_semi_fresh_eval.py` (hand-computed n = 2 interval 0.0945..0.9055, empty denominator, every class has CIs and the block serialises, per-source with the synthetic copy excluded, CLI prints and `check_thresholds` has no semi_fresh gate). `ml/eval/tests`: 143 passed.

## Bugs (continuing from ML-41)
| ID | Sev | Summary | Status |
|---|---|---|---|
| **ML-42** | **high (blocks the Colab run)** | Cell 3d cannot download AgriFreshNET: `urllib.request.urlopen("https://data.mendeley.com/public-api/datasets/42m5tb7yv9")` and `urlretrieve(download_url, ...)` use the default `Python-urllib` User-Agent, and Mendeley's Cloudflare answers **HTTP 403** to both (reproduced from this machine: the API call raises `HTTPError 403`; `curl -A Python-urllib` on the file URL gets 403, `-A Mozilla/5.0` gets a 302 to S3 and a 206 on a Range request). The notebook would stop loudly at cell 3 on the first dry run (so no wrong data, and it costs minutes, not hours), but the one-click run does not work. Colab's IP may be treated differently; do not rely on it. **Fix:** send a browser User-Agent for both calls, e.g. `H = {"User-Agent": "Mozilla/5.0"}`, `json.load(urllib.request.urlopen(urllib.request.Request(api, headers=H)))`, and download with `urllib.request.urlopen(Request(url, headers=H))` streamed to the file (or `!curl -sL -A "Mozilla/5.0" -o ...`). I verified this recipe returns the file metadata and a 206 with `Content-Range: bytes 0-999/347828971`; I did not download the 348 MB file. | **open (builder)** |
| ML-43 | low | (a) If the API stops publishing `sha256_hash`, `if want:` silently skips verification; make it `assert want`, or print a loud warning, since the size check alone (> 300 MB) is weak. (b) `fl = [...] or meta["files"][:1]` falls back to the first file when `Processed Data.zip` is missing, which could be a different archive; raise instead. (c) The gate cell's final print still says "dihedral-variant gate is pending ML-35"; it is now ML-40, ruled as reported only. (d) `docs/ML.md` line 28 and QA.md may still describe that gate as pending (not my files). | open (builder / orchestrator) |
| ML-44 | low | `RUN_DIR = CACHE_DIR + "_dry"` collides with a real RUN_ID that itself ends in `_dry` (the regex allows it): a real run with `RUN_ID=x_dry` has `RUN_DIR == fwr_runs/x_dry`, which is the dry-run folder of RUN_ID `x`, so it would see a finished 1-epoch checkpoint and skip training. Reject RUN_IDs ending in `_dry` in the regex cell. | open (builder) |
| ML-40 | medium | **Resolved by ruling:** variant check is report only, same-class, padding masked, central crop, floor shown (above). | **closed** (implemented in `ml/eval`) |
| ML-41 | low | semi_fresh cells small; now reported with Wilson CIs (informational). | open (informational) |

## Verdict for #31
- Items 1, 2, 4, 5, 6 **PASS**; Part 2 (ML-40 reporting, semi_fresh CIs) **done and tested**.
- Item 3 **FAIL: ML-42.** The dry run cannot start from a clean Colab VM until the download sends a User-Agent. Everything downstream of the download (ingest flags, subset, 3-class training, threshold plumbing, export) works on real data locally.
- **Overall: NOT READY TO MERGE; PASS conditional on ML-42** (a few-line fix; re-run item 3 after it: the notebook cell can be tested for the API + Range request without downloading the full file). ML-43 and ML-44 are low and can ride along.

---

## 2026-10-10 - Gemini receipt structuring (`feat/receipt-gemini-link`)

**Tests:** `ml/eval/tests/test_gemini_structuring.py` (62 cases; `urlopen` always monkeypatched, no real API call). Covers `_to_num` (numbers, `"3.48"`, `"$3.48"`, `"1,29"`, bools/garbage -> None), `clean_structured` (floats, nameless/non-dict lines dropped, quantity <= 0 -> None, non-dict / non-list `lines` -> None), `gemini_structure` (no key = no network; model = argument > `GEMINI_MODEL` > `gemini-flash-latest`, empty env falls back, never `gemini-2.5-flash`; key only in header; garbage bodies, HTTP/network errors -> None), and `/ocr` with `structure_with_gemini=True` (string answers become floats, fallback to deterministic parser on garbage / empty / error, request URL uses env model and the alias).

**Results:** `ml/eval/tests` 202 passed, 1 skipped, 3 xfailed (the bugs below, strict xfail so they flip when fixed). Builder suites: serve 14, ocr 89, yolo 63, all passed.

**Bugs**
| ID | Sev | Summary | Status |
|---|---|---|---|
| ML-45 | low | `_to_num("1,299.50")` returns 1.299 (comma treated as decimal; thousands separator not handled). Real receipts over $999 are rare, but the price silently shrinks 1000x. | open (builder) |
| ML-46 | low | `_to_num(float("nan"))` / `"nan"` / `"inf"` return non-finite floats; Flask `jsonify` would emit invalid JSON (`NaN`) to the backend. Reject with `math.isfinite`. | open (builder) |
| ML-47 | medium | `/ocr` and `receipt_from_image` use `g.get("total", parsed["total"])`; `clean_structured` always sets `total`, so when Gemini returns `total: null` the deterministic parser's total (7.77 in the test) is discarded and the response total is null. Use `g.get("total") if g.get("total") is not None else parsed["total"]`. | open (builder) |

**Verdict: PASS with caveats.** The change under test (model env/alias, numeric coercion, garbage fallback) behaves as specified; ML-47 is a real, small regression-in-waiting in the merge logic (outside the changed functions) and should be fixed before relying on totals; ML-45/46 are low.

### 2026-10-10 re-verification: ML-45, ML-46, ML-47 **fixed / verified**
xfail markers removed (now plain assertions) plus one added test for `"1,29"` and `"-1,299.50"`. `ml/eval/tests` 206 passed, 1 skipped; serve 14, ocr 89, yolo 63 passed. ML-45 (thousands separator), ML-46 (non-finite -> None) and ML-47 (Gemini null total keeps parser total) all closed. Note: `receipt_from_image` total merge was not separately tested (it needs a real OCR engine); the `/ocr` route is. **Verdict: PASS.**
