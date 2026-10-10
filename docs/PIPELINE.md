# Data pipeline

Owner: Pipeline builder (`pipeline/**` except `pipeline/tests/`). QA: Pipeline QA (`pipeline/tests/`, `docs/qa/pipeline.md`).

The pipeline gets new data into a shape the ML code already understands, and runs incoming receipts through OCR in batches.
It **reuses** `ml/yolo/taxonomy.py`, `ml/yolo/prepare_dataset.py` and `ml/ocr/receipt_pipeline.py` by import. Nothing is copied, so
there is still one taxonomy and one receipt parser. Everything runs on CPU with Pillow and numpy except the real GLM-OCR engine.

```
 dataset zip ──ingest-dataset──▶ staged/<name>/ ──prepare──▶ prepared/ ──augment-lighting──▶ augmented/ ──▶ ml/yolo/train.py
                                  (adapter, dedupe,          (prepare_dataset.py:            (separate step:
                                   label conflicts,           splits, heldout lighting,       lighting variants of
                                   day ranges)                crops, freshness sidecar)       train/val only)

 receipt photo ─▶ incoming/receipts/ ──ingest-receipts──▶ processed/receipts.jsonl + receipt_lines.csv
                                         │ OCR: glm | service (ML_SERVICE_URL/ocr) | fake (sidecar .txt)
                                         │ per-file timeout (worker restart) → parse_receipt_text → category cleanup
                                         └─ failures ─▶ quarantine/<file> + <file>.error.json
```

## Commands
Run these from the repo root with the project venv (`.venv/bin/pip install -r pipeline/requirements.txt`).
```bash
.venv/bin/python -m pipeline ingest-dataset --zip "~/Downloads/AgriFreshNET ....zip" --name agrifreshnet --adapter agrifreshnet
.venv/bin/python -m pipeline prepare                     # all staged datasets -> pipeline/data/prepared
.venv/bin/python -m pipeline prepare --extra-sources ml/yolo/sources.json --replace   # + the Roboflow/Kaggle sets
.venv/bin/python -m pipeline augment-lighting --per-image 2   # -> pipeline/data/augmented
.venv/bin/python -m pipeline preview-lighting --image some.jpg --out sheet.jpg
.venv/bin/python -m pipeline ingest-receipts --engine service  # or glm (GPU) / fake; add --watch 30 to poll
.venv/bin/python -m pipeline run-all --zip FILE --name NAME --adapter agrifreshnet
```
Then train: `python ml/yolo/train.py --data pipeline/data/augmented` (on the GPU box; see `docs/ML.md` §5).
Data lives under `pipeline/data/`, which is gitignored. Override it with `--data-root` or `$PIPELINE_DATA`.

| Dir | Contents |
|---|---|
| `raw/<name>/` | Extracted archive, nested zips unpacked. A `.extracted` marker skips re-extraction. |
| `staged/<name>/` | `<canonical>__<freshness>/<group>.rf.<sha>.jpg`, `manifest.csv`, `source.json`, `ingest_report.json` |
| `staged/ledger.sqlite` | sha1 of every staged image, so re-runs only add new files |
| `prepared/` | Output of `prepare_dataset.py` (layout in `docs/ML.md` §4) |
| `augmented/` | `prepared/` hard-linked, plus `*__lt_<preset>` variants, `augment_manifest.csv`, `augment_report.json` |
| `incoming/receipts/` | Drop receipt images here (`.jpg/.png/.webp/.bmp`) |
| `processed/` | `receipts/<id>.json`, `receipts.jsonl`, `receipt_lines.csv`, `archive/`, `duplicates/`, `ledger.sqlite` |
| `quarantine/` | Files that failed, each with an `.error.json` (`unsupported_format`, `invalid_image`, `ocr_timeout`, `ocr_failed`) |

## Dataset ingestion
- **Adapters** live in `pipeline/ingestion/`:
  - `agrifreshnet` reads folder names like `Semi fresh Pineapple (15-25)`.
  - `folders` is generic: any folder-per-class drop whose folder names `taxonomy.split_freshness` can read.
  - To add a dataset with odd naming, write a module with `parse_dir()`, `group_of()`, `LICENCE` and `URL`, and register it in `datasets.ADAPTERS`.
- **Safety:** extraction rejects paths that escape the target folder ("zip slip") and archives that declare more than `PIPELINE_MAX_EXTRACT_GB` (20 GB). Nested zips can go at most 3 levels deep. Every image is opened before staging. JPEG/RGB files are copied byte for byte; anything else is re-encoded to JPEG.
- **Duplicates and label conflicts:**
  - Identical files within one class are staged once (`duplicates_in_drop`).
  - **Identical files filed under two different classes are dropped entirely** and listed in `label_conflict_files`. AgriFreshNET has 17 such pairs between `Fresh Orange` and `Semi fresh Orange`.
  - If a **later** drop contains bytes that an earlier run already staged under a different class, the earlier copy is kept (it's already in `prepared/`). The new file is skipped and listed in `label_conflicts_cross_drop_files` for a human to resolve.
- **Leakage guard:**
  - The staged filename is `<group>.rf.<sha>.jpg`. `prepare_dataset.group_key()` already keeps everything before `.rf.` in one split.
  - For AgriFreshNET, a group is the original photo plus the authors' `aug_<n>_<original>` copies, plus phone shots taken in the same minute (`IMG_YYYYMMDD_HHMM`).
  - **Not caught:** the same physical fruit photographed on different days in different freshness classes. The dataset gives no way to link them.
- **Manifest columns:** `image, source_dir, source_file, item, canonical, freshness, category, age_days_min, age_days_max, group, is_source_aug, sha1, width, height, licence`.
  The age range (days since purchase/harvest, read from the folder name) is kept for later expiry modelling and isn't used yet.

### AgriFreshNET (ingested 2026-10-10)
| | |
|---|---|
| Source | `AgriFreshNET Freshness and Shelf-Life Image Dataset` (zip in a zip, "Processed Data") |
| Licence | **Unverified.** Check the dataset page and record it here before publishing results. |
| Content | 8 produce types (banana, bitter melon, cucumber, eggplant, orange, papaya, pineapple, tomato) × fresh / semi_fresh / rotten, 512×512 single-item photos on cloth |
| Result | 14,103 staged (fresh 4,693 · semi_fresh 4,693 · spoiled 4,717), 34 conflict files dropped, 23 duplicates collapsed, 0 bad images, 1,718 groups; 8,929 are the authors' own augmentations |
| prepare | train 11,060 · val 1,569 · heldout 1,474 (+ synthetic low/warm copies) |
| Caveat | Clean backgrounds, one item per photo, whole-frame boxes. It teaches **freshness** and adds 3 detector classes (`papaya`, `pineapple`, `bitter_melon`), but doesn't teach detection in fridge scenes. |

## Receipt inbox
- **Engines:**
  - `glm`: `GlmOcrEngine` (`zai-org/GLM-OCR`) runs inside a persistent worker process. It needs a GPU, torch and transformers.
  - `service`: POSTs to `ML_SERVICE_URL/ocr`. Use this when the GLM model runs on the GPU box behind `ml/serve`.
  - `fake`: returns the image's sidecar `<name>.txt`. Used for tests and CPU dry runs.
- **Timeout:**
  - `OCR_TIMEOUT_S` (default 180 s) applies per image. `generate()` can't be interrupted, so on a hang the worker process is killed and restarted, and the file is quarantined as `ocr_timeout`.
  - The first image after a (re)start gets an extra `load_grace_s` (600 s) to load the model.
  - With `service`, the HTTP timeout is the deadline.
- **Output per line:** `name, quantity, price` from the deterministic parser (or from the service, which may also use Gemini), plus `canonical, category, match` from `pipeline/category_cleanup/names.py`.
  `match` is `exact`, `alias` (after abbreviation expansion), `keyword` (a category without a detector class, such as cereal → pantry_dry) or `none` (→ `other`).
  The abbreviation, noise-word, compound-phrase and keyword tables are in `category_cleanup/abbreviations.json`.
- **ML service down:** with `--engine service`, an unreachable service stops the pass and leaves every remaining file in the inbox. The service being down isn't the file's fault, so nothing is quarantined. An HTTP error from a reachable service quarantines that one file as `ocr_failed`.
- **Re-runs:** a file whose content was already processed goes to `processed/duplicates/`. A quarantined file is retried if it is dropped into the inbox again.
- `HEIC` and `PDF` are quarantined as `unsupported_format`. Convert them to JPEG first.

## Lighting augmentation (separate step)
Public produce photos are mostly evenly lit. A fridge photo is often dim, lit by a warm bulb or an LED, or half in shadow.
`augment-lighting` adds photometric variants to **train and val only**. The parameter ranges are in `pipeline/shots/presets.json`, and every variant is seeded so runs are reproducible:

| Preset | What it simulates |
|---|---|
| `low` | dim fridge: gain 0.25–0.5, gamma, sensor noise |
| `warm` | tungsten, 2600–3600 K (black-body gains, partial strength) |
| `cool` | LED/fluorescent, 7500–10000 K, slight green |
| `bright` | overexposure, gain 1.3–1.8 with clipping |
| `shadow` | shelf or door shadow, a soft linear gradient at a random angle |
| `spot` | top interior light, radial falloff |
| `mixed` | dim plus a warm or cool cast plus noise |

- `--per-image K` picks K different presets per image (default 2). Crops in `cls/` get the same treatment, so the freshness classifier sees varied light too.
- Labels and freshness sidecars are copied unchanged, because the edits are photometric only.
- **Heldout is hard-linked unchanged**, so ML QA's normal/low/warm gates (built with `ml/yolo/lighting.synth`) stay comparable across runs.
- Colour casts are moderate on purpose. Fresh vs semi_fresh is partly a colour cue, and a heavy cast would make the label wrong.
- `augment_manifest.csv` records the preset and parameters of every variant. If a preset hurts heldout freshness precision, drop it with `--presets`.

## Known limitations
- Real GLM-OCR has **not been run** from this pipeline: there's no GPU on the VPS. The `glm` engine path is the same `GlmOcrEngine` that `docs/ML.md` §8 lists as unexecuted.
- AgriFreshNET's licence is unverified (see above).
- The category cleanup is a lookup table. Unknown brand abbreviations come out as `match: none` / `other` until they're added to `abbreviations.json`. The backend and Gemini do their own expansion when items are added.
