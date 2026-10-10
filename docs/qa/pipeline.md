# Pipeline QA log

Area: `pipeline/**` (branch `feat/data-pipeline`). Tests: `pipeline/tests/` (run from the repo root:
`.venv/bin/python -m pytest pipeline/tests -q`). All tests use pytest `tmp_path` data roots with small synthetic
images; `pipeline/data/` is never written. No torch/transformers; Flask is optional (`importorskip`, only the
ml/serve integration test uses it; the other service tests use a stdlib HTTP server).

## Result: **PASS** (no blocker/high/medium bugs; both low findings fixed and re-verified)

Final run after fixes: **92 passed, 0 xfailed, 20 s**. (First run: 90 passed, 1 xfailed, 23-25 s.) About 9 s of that is three tests that
kill a spawned OCR worker (timeout_s=1, load_grace_s=3).

## What was tested
| File | Covers |
|---|---|
| `test_ingestion.py` | Folder-name parsing (`Fresh Banana(1-4)`, `Semi fresh Pineapple (15-25)`, `Semi_Fresh eggplant(4-8)`, `Rotten Orange(20-35)`, `Semi Fresh Bittermelon ( 3-5)`) to canonical + freshness + age range; grouping (`aug_n_orig`, same-minute `IMG_` bursts, `_HDR`/`_AE`); nested-zip extraction; zip-slip rejection (also through `ingest_zip`); size cap; nesting > 3; staged layout, manifest columns, `source.json`, `ingest_report.json`; in-class duplicates, cross-class label conflicts dropped and listed, bad images, unmapped dirs; non-JPEG/RGBA re-encode; idempotent re-run (0 new files). |
| `test_prepare_augment.py` | `prepare`: semi_fresh crops in train/val, sidecar codes {0,1,2}, `boxes_by_freshness`, **no group straddles train/val/heldout** (checked per staged group, including source-aug copies), refuses non-empty out unless `--replace`, no staged data, duplicate source names. `augment`: prepared dir byte-identical before/after (hard-link safe), `data.yaml` path rewritten only in augmented, heldout files byte-identical and never given variants, labels/freshness sidecars identical to originals, crop variants in the right freshness dir, `--per-image K` gives K distinct presets, manifest/report consistent with files on disk, determinism per seed (and different seed differs), unknown preset / non-empty out / not-prepared rejected, `--replace`, per-image clamp, `--max-side` only shrinks larger inputs. Preset direction over 5 seeds: low darker, bright brighter, warm raises R/B, cool lowers R/B, mixed/shadow/spot darker; uint8, same size. Contact sheet. |
| `test_receipts.py` | Fake engine outputs (`receipts/<id>.json`, `receipts.jsonl`, `receipt_lines.csv` columns, archive incl. sidecar); duplicates; quarantine codes `unsupported_format` (.pdf/.heic/.heif/unknown/no ext/uppercase), `invalid_image`, `ocr_failed` (engine raised, missing sidecar), `ocr_timeout` (worker killed, restarted, next file processes; sidecar moves with file); quarantined content retried when re-dropped; same content twice in one pass; worker crash recovery; service engine: OK, multipart POST to `/ocr`, HTTP 500 -> `ocr_failed`, slow server -> `ocr_timeout`, **connection refused -> `counts["stopped"]`, files stay in inbox, nothing quarantined**, missing URL; real `ml/serve` Flask app with fake backends; all 24 `ml/eval/fixtures/receipts` rendered to images with `.txt` sidecars: inbox lines (name/qty/price) and total equal the parser alone for all 24, and the total equals ground truth for all 24. |
| `test_category_cleanup.py` | The required examples (`GV 2% MLK GAL`, `CHKN BRST`, `HONEY NUT CEREAL`, `JIF PEANUT BUTTER`, `XQZT 4411`), peanut butter vs butter, junk/unicode/empty/500-char input always yields one of the 11 `taxonomy.CATEGORIES` and a valid canonical, every `abbreviations.json` phrase/keyword target valid. |
| `test_cli.py` | `--help`, bad args, subprocess end-to-end `ingest-dataset` (twice, second stages 0) -> `prepare` (second refused) -> `augment-lighting` -> bad preset exit != 0 -> `preview-lighting`; `run-all`; `ingest-receipts` on an empty inbox. |

Real-data cross-check (read-only): `ingest_report.json` and `dataset_report.json` match `docs/PIPELINE.md`
(14,103 staged = 4,693 fresh + 4,693 semi_fresh + 4,717 spoiled; 34 conflict files; 23 duplicates; 0 bad; 24 classes;
prepare train 11,060 / val 1,569 / heldout 1,474; `boxes_by_freshness` equal to the staged counts).

## Bugs
| ID | Severity | Summary |
|---|---|---|
| PIPE-1 | low, **FIXED, verified** (stage.py redirects `P.main` stdout to stderr; xfail removed, test now a normal assertion) | `prepare` and `run-all` stdout is not a single JSON document. `prepare_dataset.main` prints its own one-line JSON first (`pipeline/transformation/stage.py:36`), then `cli.py` prints the report. Anything piping the output to `jq`/`json.loads` fails. Repro: `python -m pipeline --data-root X run-all ... | python -c 'import json,sys;json.load(sys.stdin)'` -> "Extra data". Expected: one JSON document (or the inner print redirected to stderr). Test: `test_cli.py::test_run_all_stdout_is_single_json` (xfail strict). |
| PIPE-2 | low, **FIXED, verified** (cross-drop conflicts counted in `label_conflicts_cross_drop` / `_files`, earlier copy kept; same-class re-drop stays `skipped_seen`; test `test_ingestion.py::test_cross_drop_conflict_and_same_class_redrop`) | Label-conflict detection only sees the current drop (`pipeline/ingestion/datasets.py`, conflict set built from `plan`). If a later drop contains bytes already staged under another class, that file is silently counted as `skipped_seen`; it is neither reported as a conflict nor does it remove the earlier staged copy, so the first label wins. Repro: ingest `Fresh Banana/x.jpg`, then a drop with the same bytes under `Rotten Banana`: second report has `skipped_seen: 1`, `label_conflict_files: []`. Expected: reported as a conflict (and ideally the staged copy dropped). No test (expected behaviour is a design decision). |

Observation (not a bug): after any worker restart the first image gets `timeout_s + load_grace_s` (default 180 + 600 s),
so a hanging receipt that follows a restart can stall the pass about 13 minutes before being quarantined.

## Not tested
- Real `glm` engine (needs GPU, torch, transformers); only the sidecar `fake` engine and the service path are covered.
- `--watch` polling loop (infinite loop), `--drop-raw`, `--extra-sources` with a real `ml/yolo/sources.json`.
- Full-size (512x512, 14k image) throughput; no performance assertions beyond the suite runtime.
- The real AgriFreshNET zip and the running augmentation in `pipeline/data/augmented` (deliberately untouched).
