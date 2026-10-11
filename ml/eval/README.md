# ml/eval — ML QA harness

Pure-stdlib metrics that run on **files**, so the same commands work here on fixtures and later on
real model output from Colab. Nothing here imports torch / ultralytics / transformers.

## Run the tests (VPS, light)
```
.venv/bin/python -m pytest ml/eval/tests -q
```
`test_builder_parser.py` / `test_builder_serve.py` skip until `ml/ocr` / `ml/serve` exist; override
discovery with `ML_PARSER=path/to/file.py:func` and `ML_SERVE_APP=path/to/app.py:factory`.

## Evaluate real YOLO output (from Colab)
1. Ground truth, one JSON line per held-out image:
   `{"image": "a.jpg", "lighting": "normal|low|warm", "labels": [{"name","category","freshness":"fresh|semi_fresh|spoiled","bbox":[x1,y1,x2,y2]}]}`
2. Run the model over the same images; one line each:
   `{"image": "a.jpg", "lighting": "...", "predictions": [{"name","category","freshness","confidence","bbox"}]}`
   Export with a LOW confidence floor (e.g. 0.001) so mAP sees the full PR curve; P/R use `--conf` (default 0.25).
3. ```
   python ml/eval/detection_metrics.py --gt gt.jsonl --pred pred.jsonl --json det.json [--conf 0.25] [--match-name]
   ```
2-class files (no `semi_fresh` anywhere) still work and give the same numbers as before.
A freshness value outside `fresh|semi_fresh|spoiled` is an error (ValueError), never silently dropped.

### Freshness: binary gates, 3-way report
Freshness has three values but **the gates are binary: spoiled vs not-spoiled** (docs/QA.md "Freshness gates").
- `semi_fresh` is folded into **not_spoiled** in both ground truth and predictions before the gated
  metrics (spoiled recall, per-class precision, lighting-drop). A fresh <-> semi_fresh confusion costs nothing there;
  a spoiled box called semi_fresh is a gated miss, and a semi_fresh box called spoiled is a gated false positive.
- **The "fresh precision" gate reads as NOT-SPOILED precision** (fresh + semi_fresh). `check_thresholds.py` prints it as
  `YOLO precision [not-spoiled]` and reads `freshness.not_spoiled` (falls back to the legacy `freshness.fresh` key for
  old metric files). In the metrics JSON `freshness.fresh` is an **alias of `not_spoiled`**, i.e. it means fresh+semi_fresh.
- **Information only, never gated:** `freshness_3way` holds the 3x3 confusion matrix (rows = ground truth, cols = prediction,
  plus a `missed` column and a `false_positive` row; matching is on localisation only) and per-class 3-way precision/recall,
  including `semi_fresh`. `recall_drop_points.<light>.semi_fresh` is also info only. Every `semi_fresh` label comes from one
  source (AgriFreshNET, ML-16), so the number can't be separated from the source. Revisit if a second source is added.

Definitions (IoU >= 0.5, greedy by confidence, all-point AP, lighting split) are in the module docstring.
A prediction row for an image absent from GT is an error; a GT image with no prediction row counts as all-missed.

## Evaluate receipt OCR
Ground truth per receipt `{"receipt","lines":[{"name","quantity","price"}],"total"}` (a directory of
`.json` files, or JSONL); predictions in the `/ocr` response shape plus a `receipt` id (directory or JSONL).
```
python ml/eval/ocr_metrics.py --gt fixtures/receipts --pred preds.jsonl --json ocr.json
```
Name match: lowercase, strip punctuation, collapse whitespace, `difflib` ratio >= 0.80, one-to-one greedy.
Price/total compared to the cent. Fixture conventions (what counts as an item, what `price` means) are in
`fixtures/build_receipts.py`; regenerate the 24 receipts with `python ml/eval/fixtures/build_receipts.py`.

## Check thresholds
```
python ml/eval/check_thresholds.py det.json ocr.json      # exit 1 on any FAIL; a missing metric is a FAIL
```
| Metric | Threshold |
|---|---|
| mAP@0.5 | >= 0.60 |
| Precision, **not-spoiled** (fresh + semi_fresh) and spoiled | >= 0.80 each |
| Recall, spoiled | >= 0.85 |
| Recall drop low / warm vs normal | <= 10 points (checked on overall AND spoiled recall; the semi_fresh drop is info only) |
| OCR line recall / price exact / total exact | >= 85% / 90% / 90% (and >= 20 receipts) |

## Generated outputs (gitignore these)
`ml/eval/results/` is written by the tests (`ocr_parser_metrics_original.json`, `ocr_parser_metrics_holdout.json`); it is generated, not source.
`ml/eval/fixtures/receipts_holdout/` is a blind set (`build_holdout.py`): never tune the parser against it; add new receipts instead.
