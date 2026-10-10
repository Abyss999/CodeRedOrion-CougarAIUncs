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
| ML-7 | medium | `Balance to pay $23.83` (mixed-case, Trader Joe's style) is not recognised as the total: emitted as an item line, `total` is null | holdout `h01_traderjoes` | open |
| ML-8 | medium | Voided item: the `VOID ORGANIC KALE -2.49` line is dropped but the original `ORGANIC KALE 2.49` line stays, giving a phantom item (net charge was zero) | holdout `h10_voided` | open |
| ML-9 | low | Multi-buy line `3 @ 2/$5.00 GREEN ONIONS  7.50` is not parsed: name keeps `3 @ 2/$5.00`, quantity 1 instead of 3 | holdout `h12_whole_numbers_and_long` | open |

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
