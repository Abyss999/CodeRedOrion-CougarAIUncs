# Data pipeline

Owner: Pipeline builder (`pipeline/**` except `pipeline/tests/`). QA: Pipeline QA (`pipeline/tests/`, `docs/qa/pipeline.md`).

The pipeline gets new data into a shape the ML code already understands, and runs incoming receipts through OCR in batches.
It **reuses** `ml/yolo/taxonomy.py`, `ml/yolo/prepare_dataset.py` and `ml/ocr/receipt_pipeline.py` by import. Nothing is copied, so
there is still one taxonomy and one receipt parser. Everything runs on CPU with Pillow and numpy except the real GLM-OCR engine. The receipt cleanup also loads
`backend/app/services/food_group.py` **by file path** (it is stdlib-only; importing it as `app.services.food_group`
would run `backend/app/__init__.py` and pull in Flask and SQLAlchemy), so the abbreviation table and the name-only
food-group heuristic exist once.

**Taxonomy compatibility.** The pipeline is written against `ml/yolo/taxonomy.py` as it is on `main`: two freshness
classes (`fresh`, `spoiled`) and no `papaya` / `pineapple` / `bitter_melon` classes. It reads
`getattr(taxonomy, "FRESHNESS", ("fresh", "spoiled"))` and works unchanged once the `semi_fresh` PR lands: nothing here
needs editing then, and the tests that assume a third class (marked `needs_semi` / `needs_class`) switch on by themselves.

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
.venv/bin/python -m pipeline augment-lighting --per-image 2   # -> pipeline/data/augmented (cool,bright,shadow,spot)
.venv/bin/python -m pipeline augment-lighting --presets all    # opt in to low/warm/mixed too: read "Lighting augmentation"
.venv/bin/python -m pipeline preview-lighting --image some.jpg --out sheet.jpg
.venv/bin/python -m pipeline ingest-receipts --engine service  # or glm (GPU) / fake; add --watch 30 to poll
.venv/bin/python -m pipeline run-all --zip FILE --name NAME --adapter agrifreshnet
```
`run-all` = ingest, prepare **and** `augment-lighting` with the default presets (`cool,bright,shadow,spot`, never low/warm/mixed); to train without augmentation point `train.py` at `pipeline/data/prepared` instead.
Then train: `python ml/yolo/train.py --data pipeline/data/augmented` (on the GPU box; see `docs/ML.md` §5).
Data lives under `pipeline/data/`, which is gitignored. Override it with `--data-root` or `$PIPELINE_DATA`.

| Dir | Contents |
|---|---|
| `raw/<name>/` | Extracted archive, nested zips unpacked. A `.extracted` marker skips re-extraction. |
| `staged/<name>/` | `<canonical>__<freshness>/<group>.rf.<sha>.jpg` (`<group>` keeps the full capture timestamp, e.g. `banana__fresh__IMG_20250101_123456.rf.<sha>.jpg`), `manifest.csv`, `source.json`, `ingest_report.json` |
| `staged/ledger.sqlite` | sha1 of every staged image, so re-runs only add new files |
| `prepared/` | Output of `prepare_dataset.py` (layout in `docs/ML.md` §4) |
| `augmented/` | `prepared/` hard-linked, plus `*__lt_<preset>` variants, `augment_manifest.csv`, `augment_report.json` |
| `incoming/receipts/` | Drop receipt images here (`.jpg/.png/.webp/.bmp`) |
| `processed/` | `receipts/<id>.json`, `receipts.jsonl`, `receipt_lines.csv`, `archive/`, `duplicates/`, `ledger.sqlite` |
| `quarantine/` | Files that failed, each with an `.error.json` (`unsupported_format`, `invalid_image`, `ocr_timeout`, `ocr_failed`) |

## Dataset ingestion
- **Adapters** live in `pipeline/ingestion/`:
  - `agrifreshnet` reads folder names like `Semi fresh Pineapple (15-25)`.
  - `folders` is generic: any folder-per-class drop whose folder names `taxonomy.split_freshness` can read (the `(a-b)` day range is stripped first).
  - **Semi-fresh folders** (`Semi fresh ...`, `Semi_Fresh ...`) keep a `semi_fresh` label only if the taxonomy has that class. On a 2-class taxonomy they are staged as **`fresh`**, never dropped: the manifest keeps the original label in `source_freshness`, the ingest report counts them as `semi_fresh_mapped_to_fresh` and adds a `notes` entry. Fresh/Semi-fresh duplicates are still judged on the source labels, so they stay label conflicts.
  - **Produce the taxonomy has no class for** (papaya, pineapple and bitter melon until the `semi_fresh` PR adds them) is not staged. Those folders are listed under `unmapped_dirs` with their image counts.
  - To add a dataset with odd naming, write a module with `parse_dir()`, `group_of()`, `LICENCE` and `URL`, and register it in `datasets.ADAPTERS`.
- **Safety:** extraction rejects paths that escape the target folder ("zip slip") and archives that declare more than `PIPELINE_MAX_EXTRACT_GB` (20 GB). Nested zips can go at most 3 levels deep. Every image is opened before staging. JPEG/RGB files are copied byte for byte; anything else is re-encoded to JPEG.
- **Duplicates and label conflicts:**
  - Identical files within one class are staged once (`duplicates_in_drop`).
  - **Identical files filed under two different classes are dropped entirely** and listed in `label_conflict_files`. AgriFreshNET has 17 such pairs between `Fresh Orange` and `Semi fresh Orange`.
  - If a **later** drop contains bytes that an earlier run already staged under a different class, the earlier copy is kept (it's already in `prepared/`). The new file is skipped and listed in `label_conflicts_cross_drop_files` for a human to resolve.
- **Leakage guard:**
  - The staged filename is `<group>.rf.<sha>.jpg`. `prepare_dataset.group_key()` keeps everything before `.rf.` in one split.
  - For AgriFreshNET, a group is the original photo plus the authors' `aug_<n>_<original>` copies and their `_HDR` / `_AE` variants.
  - **The full original capture timestamp stays in the group** (`IMG_YYYYMMDD_HHMMSS`, `IMG2025...`, a 13-digit epoch in ms, or a bare `YYYYMMDD_HHMMSS`), e.g. `banana__fresh__IMG_20250101_123456.rf.<sha>.jpg`. Long names are cut to 80 characters, but the timestamp is always kept whole. This is what the session grouping on `feat/ml-full-data` (`parse_capture_time`, ML-21) reads, with a `re.search` so a non-leading token is fine, to put shots taken seconds apart into one split.
  - **Until that branch is merged**, a burst of phone shots taken within the same minute but at different seconds is no longer one group (the old adapter truncated the stamp to the minute, which hid it from the time grouping). `prepare_dataset` on `main` only has stem grouping, so bursts can straddle splits until the session grouping lands. The authors' own `aug_` copies, HDR/AE variants and exact duplicates are still one group.
  - **Specimen grouping (opt-in, `PIPELINE_SPECIMEN_GROUPS=1` or `ingest(..., specimen_groups=True)`; AgriFreshNET).** The default owner assumption is conservative: the same physical specimens appear in Fresh, Semi fresh and Rotten, and the authors' augmentations may be flipped or rotated. `ingestion/specimens.py` therefore clusters each produce class **across all three stages**:
    1. pHash-64 (`ml/yolo/dedup.py` method) of the 8 dihedral variants of every image (identity, 3 rotations, and the same four after a flip).
    2. Variant-aware distance = minimum Hamming distance between one image's plain hash and the other's 8 variant hashes, so a flipped or rotated copy lands at about 0.
    3. Connected components at distance <= 10 are the split units. **Giant-component guard:** if the largest component holds more than 30% of the class, the threshold is tightened for that class (10, 8, 6, 4) until it does not. Plain backgrounds make the loose threshold chain: at 10 the largest component was 63-91% of the class for 7 of 8 classes, so only pineapple kept 10.
    4. **Capture sessions.** `prepare_dataset.parse_capture_time` does not read AgriFreshNET's `IMG_YYYYMMDD_HHMMSSmmm` names (9-digit time, milliseconds), so its session grouping sees none of them, while ML QA's leakage check (ML-21: 0 held-out images within 300 s of a train/val image of the same source) does. `specimens.py` therefore builds the sessions itself: shots <= 300 s apart, across all classes, no span cap. Its first choice is the union of specimen components and sessions, but cross-day specimen links chain sessions into one unit (44% of the dataset, 86-100% of six classes), so the fallback is used: timestamped files take their session as the unit, untimestamped files their specimen component. Cross-stage grouping therefore holds only for untimestamped files; for timestamped ones a specimen's Fresh and Rotten photos (days apart) can land in different splits. Splitting by session was judged preferable to a single giant unit that would make the class unmeasurable.
    5. The unit is encoded in the staged name: `<class>__spec_<id>.rf.<sha16>_<original stem>.jpg` or `sess_<id>.rf.<sha16>_<original stem>.jpg`. `prepare_dataset.group_key()` keeps everything before `.rf.` together, so `prepare_dataset` needed no change.
    6. Curation flags on `ingest-dataset`: `--specimen-groups` (same as `PIPELINE_SPECIMEN_GROUPS=1`), `--exclude-source-augs` (skip `aug_<n>_<original>`), `--max-per-cell N` (cap per class x freshness, round-robin over units; before/after in the ingest report `curation` block). With the augmentations excluded, the 5,174 remaining originals have far fewer near-duplicates (3-44% per class at variant-aware <= 6).
    7. Off by default because it changes staged file names (the existing tests pin the `<cls>__<stem>` form). The ingest report gets a `specimen_grouping` block with the stats below.

  - **Not caught by name/time alone:** the same physical fruit photographed on different days in different freshness classes. The dataset gives no specimen id, so the specimen grouping above (pHash) is the only link, and it can miss a specimen whose appearance changed enough with age.
- **Manifest columns:** `image, source_dir, source_file, item, canonical, freshness, category, age_days_min, age_days_max, group, is_source_aug, sha1, width, height, licence`.
  The age range (days since purchase/harvest, read from the folder name) is kept for later expiry modelling and isn't used yet.

### AgriFreshNET (ingested 2026-10-10)
| | |
|---|---|
| Source | `AgriFreshNET Freshness and Shelf-Life Image Dataset` (zip in a zip, "Processed Data") |
| Licence | **CC BY 4.0** (Mendeley Data, DOI [10.17632/42m5tb7yv9.1](https://doi.org/10.17632/42m5tb7yv9.1), v1). Authors Risdin, Salauddin, Tufa, Hossain. <https://data.mendeley.com/datasets/42m5tb7yv9>. Attribution required: see "Attributions". |
| Content | 8 produce types (banana, bitter melon, cucumber, eggplant, orange, papaya, pineapple, tomato) × fresh / semi_fresh / rotten, 512×512 single-item photos on cloth |
| Result (3-class taxonomy, run on the original `feat/data-pipeline` before the take-over) | 14,103 staged (fresh 4,693 · semi_fresh 4,693 · spoiled 4,717), 34 conflict files dropped, 23 duplicates collapsed, 0 bad images, 1,718 groups; 8,929 are the authors' own augmentations. prepare: train 11,060 · val 1,569 · heldout 1,474 (+ synthetic low/warm copies). These numbers are **not reproduced** on `main`'s 2-class taxonomy, see below. |
| On a 2-class taxonomy | `semi_fresh` images are staged as `fresh` and reported; papaya, pineapple and bitter melon (3 of the 8 produce types) are listed as `unmapped_dirs` and skipped. Re-ingest after the `semi_fresh` PR for the full set (delete `staged/<name>` and the ledger entry first, or use a new `--name`). |
| Re-ingest 2026-10-10 (`feat/semi-fresh-data`, A2, specimen grouping on) | 14,160 files (24 x 590, not 591), 14,103 staged (same counts as above), 893 split units (specimen+session fallback; 4,096 pure specimen components). 63% of staged files are `aug_` copies and 92% have a flip/rotation-aware pHash <= 6 near-duplicate elsewhere in their class: **the set is heavily augmented**, so its effective sample size is the group count, not 14k. Cucumber is a taxonomy class (no mapping needed). |
| Caveat | Clean backgrounds, one item per photo, whole-frame boxes. It teaches **freshness**; it doesn't teach detection in fridge scenes. The same source supplies every `semi_fresh` image, so a model could learn the source's look. |

**AgriFreshNET specimen grouping, per class** (variant-aware pHash components across Fresh / Semi fresh / Rotten):

| class | images | threshold used | components | singletons | largest (share) | near-dup <= 6 in class | specimen+session union, largest share |
|---|---|---|---|---|---|---|---|
| banana | 1762 | 6 (tightened) | 510 | 101 | 208 (11.8%) | 93.9% | 95% |
| bitter_melon | 1767 | 4 (tightened) | 490 | 76 | 42 (2.4%) | 97.4% | 100% |
| cucumber | 1769 | 6 (tightened) | 274 | 39 | 369 (20.9%) | 97.8% | 99% |
| eggplant | 1770 | 6 (tightened) | 463 | 93 | 386 (21.8%) | 94.6% | 96% |
| orange | 1732 | 6 (tightened) | 563 | 203 | 172 (9.9%) | 88.1% | 40% |
| papaya | 1766 | 4 (tightened) | 451 | 149 | 89 (5.0%) | 94.0% | 100% |
| pineapple | 1769 | 10 | 446 | 60 | 246 (13.9%) | 95.6% | 35% |
| tomato | 1768 | 4 (tightened) | 899 | 539 | 223 (12.6%) | 77.6% | 86% |

Dataset-wide capture sessions (<= 300 s, milliseconds read): 11471 timestamped files in 73 sessions, largest 569. Union of specimen components and sessions: largest unit 6227 files (44% of the dataset; 86-100% of six classes), so the fallback applies: **timestamped files are grouped by session (`sess_<id>`), untimestamped files (WhatsApp `IMG-YYYYMMDD-WA`, `Banana (3).jpeg`, 11471 of 14,103 are timestamped) by specimen component**. Final: 893 units, largest 569 files (4.0%).

## Receipt inbox
- **Engines:**
  - `glm`: `GlmOcrEngine` (`zai-org/GLM-OCR`) runs inside a persistent worker process. It needs a GPU, torch and transformers.
  - `service`: POSTs to `ML_SERVICE_URL/ocr`. Use this when the GLM model runs on the GPU box behind `ml/serve`.
  - `fake`: returns the image's sidecar `<name>.txt`. Used for tests and CPU dry runs.
- **Timeout:**
  - `OCR_TIMEOUT_S` (default 180 s) applies per image. `generate()` can't be interrupted, so on a hang the worker process is killed and restarted, and the file is quarantined as `ocr_timeout`.
  - The first image after a (re)start gets an extra `load_grace_s` (600 s) to load the model.
  - With `service`, the HTTP timeout is the deadline.
- **Output per line:** `name, quantity, price` from the deterministic parser (or from the service, which may also use Gemini), plus `canonical, category, food_group, match` from `pipeline/category_cleanup/names.py`.
  `food_group` is `taxonomy.food_group_for(canonical)` when the line maps to a detector class, otherwise the backend's name-only heuristic `food_group.derive_from_name` (tried on the raw text first, then on the pipeline-expanded tokens). So `orange juice` is `other` (class `juice`), and `granola bars` is `pantry` (no class).
  `match` is `exact`, `alias` (after abbreviation expansion), `keyword` (a category without a detector class, such as cereal → pantry_dry) or `none` (→ `other`).
  Abbreviations come from **two tables, never duplicated**: first the backend's `food_group.ABBREVIATIONS`, then the extras in `category_cleanup/abbreviations.json` (`expand`, plus the noise-word, compound-phrase and keyword tables). `expand` holds only keys the backend table lacks, and `pipeline/tests/test_category_cleanup.py` fails if a key appears in both or if shared keys disagree. Where the backend expands to a word that is not a detector class (`mozz` -> `mozzarella`), the extras map that word onward (`mozzarella` -> `cheese`).
- **ML service down:** with `--engine service`, an unreachable service stops the pass and leaves every remaining file in the inbox. The service being down isn't the file's fault, so nothing is quarantined. An HTTP error from a reachable service quarantines that one file as `ocr_failed`.
- **Re-runs:** a file whose content was already processed goes to `processed/duplicates/`. A quarantined file is retried if it is dropped into the inbox again.
- `HEIC` and `PDF` are quarantined as `unsupported_format`. Convert them to JPEG first.

## Lighting augmentation (separate step, opt-in)
Public produce photos are mostly evenly lit. A fridge photo is often dim, lit by a warm bulb or an LED, or half in shadow.
`augment-lighting` adds photometric variants to **train and val only**. It is never part of default training: you run it, and train on `augmented/` on purpose.
The parameter ranges are in `pipeline/shots/presets.json`, and every variant is seeded so runs are reproducible:

| Preset | What it simulates | In the default set |
|---|---|---|
| `low` | dim fridge: gain 0.25-0.5, gamma, sensor noise | **no, opt-in** |
| `warm` | tungsten, 2600-3600 K (black-body gains, partial strength) | **no, opt-in** |
| `mixed` | dim plus a warm or cool cast plus noise | **no, opt-in** |
| `cool` | LED/fluorescent, 7500-10000 K, slight green | yes |
| `bright` | overexposure, gain 1.3-1.8 with clipping | yes |
| `shadow` | shelf or door shadow, a soft linear gradient at a random angle | yes |
| `spot` | top interior light, radial falloff | yes |

**Why `low`, `warm` and `mixed` are not on by default.** `ml/yolo/lighting.synth` builds the synthetic `low` and `warm` copies of the held-out rows that ML QA's lighting gates score. Training on the same families and then scoring on those copies is train-on-test-family: the lighting numbers would go up because the model has seen that kind of edit, not because it handles a real dim or warm fridge (ML-17, ML-22). `mixed` is dim plus a warm/cool cast, so it overlaps both. The default set (`cool,bright,shadow,spot`) adds light variety without touching those families. `--presets all` or `--presets low,warm,...` still works for experiments.

**Sign-off rule.** A model trained on `augmented/` with `low`, `warm` or `mixed` gets **no lighting sign-off from the synthetic held-out rows**. Only real low-light and warm-light photos count. `augment_report.json` records this: `heldout_family_presets_used` lists the opt-in presets that were used, and `lighting_signoff` says `none ...` or `n/a ...` accordingly. Even with the default set, the synthetic rows are a smoke test, not evidence for real fridges.

- `--per-image K` picks K different presets per image (default 2, at most the number of presets selected). Crops in `cls/` get the same treatment, so the freshness classifier sees varied light too.
- Labels and freshness sidecars are copied unchanged, because the edits are photometric only.
- **Heldout is hard-linked unchanged**, so ML QA's normal/low/warm gates (built with `ml/yolo/lighting.synth`) stay comparable across runs.
- Colour casts are moderate on purpose. Freshness is partly a colour cue, and a heavy cast would make the label wrong.
- `augment_manifest.csv` records the preset and parameters of every variant. If a preset hurts heldout freshness precision, drop it with `--presets`.

## Known limitations
- Real GLM-OCR has **not been run** from this pipeline: there's no GPU on the VPS. The `glm` engine path is the same `GlmOcrEngine` that `docs/ML.md` §8 lists as unexecuted.
- On a 2-class taxonomy, AgriFreshNET's semi-fresh images are folded into `fresh` and three of its eight produce types are skipped (see above). Both go away when the `semi_fresh` PR lands.
- Burst grouping by time only works once `prepare_dataset` has the session grouping from `feat/ml-full-data` (see "Leakage guard").
- The category cleanup is a lookup table. Unknown brand abbreviations come out as `match: none` / `other` until they're added to `abbreviations.json`. The backend and Gemini do their own expansion when items are added.

## Attributions
- **AgriFreshNET Freshness and Shelf-Life Image Dataset**: Risdin, Salauddin, Tufa, Hossain. Mendeley Data, v1, DOI [10.17632/42m5tb7yv9.1](https://doi.org/10.17632/42m5tb7yv9.1), <https://data.mendeley.com/datasets/42m5tb7yv9>. Licensed **CC BY 4.0**. Any model or result built on it must credit it. The adapter writes the licence into every `manifest.csv` row and `source.json`. `docs/ML.md`'s Attributions section needs the same entry.

## Abbreviations moved to the backend table
Done in `feat/receipt-abbrevs`. The backend's `food_group.ABBREVIATIONS` now holds the plain receipt abbreviations that used to be pipeline-only extras, so receipts added through the API get them too, and `derive_from_name` sees them.

- **Moved to the backend table (and deleted from `abbreviations.json` `expand`):** `mlk` milk, `skm` skim, `whl` whole, `grk` greek, `brst` breast, `stk` steak, `prk` pork, `saus` sausage, `ched` cheddar, `parm` parmesan, `bttr` butter, `bred` bread, `tort` tortilla, `tom` tomato, `tmto` tomato, `onin` onion, `ltc` lettuce, `lett` lettuce, `broc` broccoli, `caul` cauliflower, `crt` carrot, `crts` carrots, `cuc` cucumber, `cuke` cucumber, `strawb` strawberry, `grps` grapes, `grp` grapes, `avoc` avocado, `appl` apple, `aple` apple, `orng` orange, `lmn` lemon, `lme` lime, `mshrm` mushroom, `mush` mushroom, `shrms` mushrooms, `pepr` pepper, `zuc` zucchini, `zucc` zucchini, `papya` papaya, `pnapl` pineapple, `pinapl` pineapple, `jce` juice, `oj` juice, `rce` rice, `slmn` salmon.
- **Onward mapping kept in the pipeline** where the backend word is not a detector class: `parmesan` -> `cheese` (`parm` used to map straight to `cheese`), `mushrooms` -> `mushroom`, `carrots` -> `carrot`. Pipeline output for every moved key is unchanged.
- **Effect on the backend:** the words `whole`, `skim`, `greek`, `breast` are in no keyword table, so those abbreviations change nothing alone (the other word on the line decides). Every other moved key now resolves to the group its expansion already had (`mlk` dairy, `oj`/`jce` pantry via the juice rule, `tort` grains, `tom` veggies, `orng` fruit, `slmn` protein, `rce` grains).
- **Known collision:** `tom` expands to tomato even when it is a name or brand (`TOM TURKEY` is protein in the backend because protein is checked before veggies, but the pipeline reads it as tomato). Accepted: receipts with a bare `TOM` token are overwhelmingly tomato.
- **Keep in the pipeline only (class mapping):** `bnnas`, `bananas`, `eggs`, `onions`, `carrots`, `toms`, `torts`, `pots` -> the class word; varieties `roma`, `russet`, `romaine`, `icebrg`, `gala`, `fuji`, `honeycrisp`; `mozzarella` -> `cheese`, `spaghetti` -> `pasta`, `tilapia` -> `fish`, `whlwht` -> `bread`; and the empty expansions that drop a token (`lg`, `xl`, `dz`, `dzn`, `yel`, `org`, `orgnc`, `organic`).
- **Too ambiguous to share (stay in the pipeline):** `gr`, `pot` (pot roast, pot pie), `pine`, `ban`, `straw`, `berr`, `grn`, `swt`, `wht`, `hvy`, `sda` (baking soda).
- **Entries both tables had earlier** (same expansion, deleted from the pipeline): `bnna chkn chk chix bf grnd bcn sausg chs chz ygrt yog yogrt crm brd spnch brocc strwb avo frz frzn shrmp btr`. Two differed, so the pipeline defers to the backend and maps onward: `mozz` (backend `mozzarella`, was `cheese`) and `spag` (backend `spaghetti`, was `pasta`).
