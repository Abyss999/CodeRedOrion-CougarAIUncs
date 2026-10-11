# ML (detection, spoilage, receipt OCR)

Owner: ML builder. Code: `ml/yolo/`, `ml/ocr/`, `ml/serve/`. Eval lives in `ml/eval/` (ML QA).
**Nothing here is trained or run on the VPS** (no GPU, ~2 GB free RAM). Training/inference happen on
Colab or a GPU box; everything is importable and unit-testable on the VPS with Pillow/numpy/Flask only.

## 0. What the owner clicks (Colab, `ml/yolo/train_colab.ipynb`)
**Gate: do not run it until ML QA has re-verified ML-21 on the session-grouped split** (the notebook also stops itself unless
`dataset_report.json` has `split_grouping: "session"` and `ml/eval/leakage_check.py` reports 0 held-out images within 300 s of a train/val image).
1. Runtime -> Change runtime type -> **T4 GPU**.
2. Add the 2 Colab Secrets (key icon, Notebook access on): `ROBOFLOW_API_KEY` (**the PRIVATE key** from Roboflow Settings -> API Keys; the `rf_`-prefixed publishable key cannot download) and `KAGGLE_API_TOKEN` (Kaggle access token, sent as a Bearer token; optional, without it the Kaggle source is skipped). AgriFreshNET, MeatScan and DaFiF need no secret.
3. **Dry run first.** Cell 1 has a checkbox `DRY_RUN` (**default on**) and the `RUN_ID` field. **Runtime -> Run all** with `DRY_RUN` on: download, prepare, all gates,
   Drive cache, then **1 epoch on a deterministic 5% subset** (`ml/yolo/make_subset.py`: every 20th file per split / class folder, symlinks; all three freshness
   classes kept) for detector and classifier, then the export, then it stops with **`DRY RUN OK`** (about 15 min). Its checkpoints go to `MyDrive/fwr_runs/<RUN_ID>/data_<DATA_VER>_dry/`,
   so the real run can never resume them. The dataset cache (`<RUN_ID>/data_<DATA_VER>/fwr_data.tar`) is shared. `DATA_VER` is the first 8 hex digits of the SHA-256 of
   `ml/yolo/sources.json`, so adding or editing a source always triggers a fresh download + prepare instead of reusing an older cached dataset. (Ultralytics' own `fraction=0.05` exists in 8.4.175 but takes the *first*
   5% of the sorted file list, i.e. one source or one class folder, which would not test the 3-class head.)
4. **Real run:** untick `DRY_RUN`, keep the **same `RUN_ID`**, **Runtime -> Run all**. The prepared dataset is restored from Drive (no downloads), the gates re-run, then
   training. **`FAST` (cell 1, default on): ~30 min on a T4** (section 5d); untick it for the full run (detector 80 ep + classifier 30 ep, ~4-5 h). Allow Drive access: **Drive is required** (cell 1 stops with a message if it is not mounted). Everything lives in `MyDrive/fwr_runs/<RUN_ID>/data_<DATA_VER>/`.
   **If you got disconnected: reconnect, keep the same `RUN_ID` and `DRY_RUN` setting, Runtime -> Run all; it resumes from the last epoch on Drive.**
   Write the `RUN_ID` down: left at the default it is today's date, so resuming after midnight needs it typed in.
5. Download `export.zip` from the last cell and hand it to the team. Cell 5 also has a `SEMI_FRESH_THRESHOLD` field (default 0.5), passed through
   `train.py --semi-fresh-threshold` (env `SEMI_FRESH_THRESHOLD`) to `export_predictions.py`, so predictions can be re-labelled without retraining.
The notebook downloads VegQual (figshare), every non-pending Roboflow set with a pinned version (API), raghavrpotdar (if Kaggle creds exist), **MeatScan** (cell 3e: `python -m pipeline fetch-meatscan` range-reads 450 originals per class from the 25.4 GB Zenodo RAR, then `ingest-dataset --adapter meatscan --max-per-cell 300`; needs `unrar-cffi`, installed in cell 1), **DaFiF fish** (cell 3f: `fetch-dafif` then `ingest-dataset --adapter dafif --max-per-cell 300`; see `docs/PIPELINE.md` for both) and **AgriFreshNET from the public Mendeley release**
(file selected by name from `data.mendeley.com/public-api/datasets/42m5tb7yv9`; both requests send a browser-like `User-Agent` because Mendeley returns 403 to urllib's default; the zip is always verified against the hardcoded SHA-256 `6607a48b...3f11`; a `RUN_ID` ending in `_dry` is rejected), ingests it with `python -m pipeline --data-root /content/pipeline_data
ingest-dataset --adapter agrifreshnet --specimen-groups --exclude-source-augs --max-per-cell 300` (4,754 images, same as the local a2b run), derives a
`sources.colab.json` from the repo's `sources.json` with `/content/...` roots, runs `prepare_dataset.py`, the gates, `train.py --device auto --resume` (FAST: yolo26n 512 px 30 ep on
the capped detector train set + classifier 10 ep; full: yolo26s 80 ep + classifier 30 ep) and the export. Gates: split_grouping session, `leakage_check.py` (identity pHash <= 1% per source, 0 held-out within 300 s, agrifreshnet included),
`stratification_check.py` (3-class mapping) and a check that `cls/{train,val}` has `fresh`, `semi_fresh` and `spoiled`. The gate is identity pHash <= 6 and <= 1% per source; the
dihedral-variant near-duplicate check is **reported only** (same-class, masked padding, ML-40), not a gate in the notebook (ML-35 ruling). Expect ~30 min on a free T4 for the real run with `FAST` (estimate, section 5d), ~4-5 h without.

## 1. YOLO version decision (verified 2026-10-10)
- PyPI `ultralytics` latest = **8.4.175** (`pip index versions ultralytics`). Pinned in `ml/yolo/requirements.txt`.
- Ultralytics docs (docs.ultralytics.com/models) say: "Start with **YOLO26** for a new project"; YOLO11 is the
  mature alternative; YOLO27 has no released weights. **Decision: YOLO26.** Detector `yolo26s.pt`
  (small: good accuracy/latency on a Colab T4; bump to `yolo26m.pt` via `--det-model` if mAP is short),
  freshness classifier `yolo26n-cls.pt`. Weight names are from the docs family naming; if the download
  404s on Colab, check the docs model table for the exact filename. **Unverified until run on a GPU.**
- **Licence: Ultralytics is AGPL-3.0.** Fine for a public hackathon repo; if the service is ever offered
  over a network in a closed-source product, AGPL obligations (or an Ultralytics enterprise licence) apply.
- Also record in `docs/DECISIONS.md` (orchestrator-owned): "YOLO26 via ultralytics==8.4.175, AGPL-3.0".

## 2. Datasets
Licences, class lists and sizes verified **2026-10-10** (figshare API for VegQual, Roboflow pages for the two
fridge sets, Kaggle API for the Kaggle sets). `ml/yolo/sources.json` (committed, no secrets) holds the class maps;
raw data lives outside the repo (`mldata/raw/<name>`). `prepare_dataset.py` skips sources marked `"pending": true` (only `food_hvk7g` now)
or whose root is missing, drops unmapped labels (listed in `dataset_report.json`), and supports
`drop_image_if_label` (drops a whole image that contains an unmodelled object).

| Role | Dataset | Licence | Size / classes | Status |
|---|---|---|---|---|
| fresh vs defective produce (boxes) | VegQual, figshare article 30596084 (= Roboflow rakib151p/vegmining-i6j82 v6) | **CC BY 4.0** | 4,831 images (train 4,221 / valid 406 / test 204), 14 classes: `defected_/fresh_` x potato, bitter_gourd, brinjal, capsicum, onion, pointed_gourd, tomato (7 defected + 7 fresh; see mapping) | **downloaded** (212 MB) |
| fridge/pantry items | Fridge objects (wajeeha-workspace) https://universe.roboflow.com/wajeeha-workspace/fridge-objects-mtmmo | **CC BY 4.0** | ~963 imgs; lemon, milk, cheese, avocado, butter, pepper, yogurt, bacon, eggs, tomatoes | downloaded: v1 (963), see Status below |
| fridge/pantry items | Hien_Fridge (gracelearning) https://universe.roboflow.com/gracelearning/hien_fridge-tathx | **CC BY 4.0** | 1,912 imgs (v12); apple, egg, milk_carton, others, soda_can, yogurt_container (`others` dropped) | downloaded: v12 |
| fresh vs stale fruit/veg (whole image) | raghavrpotdar/fresh-and-stale-images-of-fruits-and-vegetables (Kaggle) | **CC0** | ~1.5 GB, 14,683 files; fresh_/stale_ x apple, banana, bitter_gourd, capsicum, orange, tomato | downloaded; replaces sriramr |
| fresh vs spoiled **cow meat** (whole image) | MeatScan, Zenodo 16764338 (Data in Brief 2025) | **CC BY 4.0** | 6,995 originals (3,487 fresh / 3,508 spoiled) + 4,005 author augmentations, one 25.4 GB RAR | enabled 2026-10-10 (`meatscan`): originals only, range-read, 300 per cell. First non-produce freshness source (ML-16) |
| fresh vs spoiled **fish** (whole image) | DaFiF, Mendeley vx4ptwk3pb v1 (Data in Brief 57, 2024) | **CC BY 4.0** | 2,536 photos of mackerel, tilapia, tuna over 11 days on ice | enabled 2026-10-10 (`dafif`): days 1-3 fresh, 9-11 spoiled, 4-8 dropped (owner rule), 300 per cell |
| fresh vs spoiled produce (polygons -> boxes) | Roboflow food-monitoring/food-spoilage-status-ds1sc **v1** | **CC BY 4.0** | 276 imgs; fresh/spoiled x apple, banana, capsicum, orange, potato, bitter gourd | enabled 2026-10-10 (`food_spoilage_status`) |
| bananas / oranges (boxes) | Roboflow fruit-and-vegetable-objection-by-yolo/food-hvk7g | **CC BY 4.0** | 696 imgs; `2`, orange, oranges, Platano; **no freshness labels** | **pending**: 0 generated versions (not downloadable until forked into our workspace) |

**Dropped: `sriramr/fruits-fresh-and-rotten-for-classification`** - the Kaggle API reports its licence as
"Unknown", so it is not usable. Replacement is the CC0 raghavrpotdar set above.

**VegQual mapping.** `defected_X` -> `X:spoiled`, `fresh_X` -> `X:fresh` (the code does not treat "defected" as a
spoiled word, so the map is explicit); brinjal -> `eggplant`, capsicum -> `bell_pepper`. **Bitter gourd and pointed
gourd are not taxonomy classes.** Dropping only their labels would leave real, unlabeled objects in images, which the
detector learns as background. 1,615 images are gourd-only (they end up with no boxes and are skipped automatically);
only 6 images mix gourds with other vegetables, and those are removed entirely via `drop_image_if_label`. Net: no
unlabeled gourds in the training data.

Also seen, not wired in: Roboflow "Fridge food detection" (greeshannotate, 114 imgs, CC BY 4.0, too small);
Mendeley fresh/rotten tomatoes (CC BY 4.0 via Roboflow). Add as extra `sources` entries if class coverage is thin.
Honest expectation: public fridge sets are small and non-US; fresh-vs-rotten sets are mostly isolated
produce on clean backgrounds. Expect a domain gap on real fridge photos (see limitations); the Gemini fallback exists for that.
VegQual alone only covers 5 detector classes (potato, eggplant, bell_pepper, onion, tomato) - the fridge sets are
needed for dairy/eggs/meat.

### Attributions (CC BY 4.0)
All changes below: relabelled into our own taxonomy (`ml/yolo/taxonomy.py`); fresh/spoiled split out of the
detector classes into a separate crop classifier; merged with the other sources; images re-encoded to JPEG and split
into train/val/heldout (plus synthetic low/warm-light copies of held-out images).
- **VegQual: A Multiclass Dataset for Real-Time Fresh and Defective Vegetables** - figshare article 30596084,
  https://figshare.com/articles/dataset/A_Multiclass_Dataset_for_Real-Time_Fresh_and_Defective_Vegetables/30596084
  (also Roboflow `rakib151p/vegmining-i6j82` v6, workspace rakib151p). Licence CC BY 4.0. Dropped: bitter gourd and
  pointed gourd classes (and the 6 images mixing them with other vegetables).
- **Fridge objects** - Roboflow Universe, workspace `wajeeha-workspace`,
  https://universe.roboflow.com/wajeeha-workspace/fridge-objects-mtmmo . Licence CC BY 4.0. Dropped: none planned
  (`pepper` mapped to `bell_pepper`, `tomatoes` to `tomato`, `eggs` to `egg`).
- **Hien_Fridge** - Roboflow Universe, workspace `gracelearning`,
  https://universe.roboflow.com/gracelearning/hien_fridge-tathx . Licence CC BY 4.0. Dropped: the `others` class.
- **AgriFreshNET Freshness and Shelf-Life Image Dataset** - Risdin, Salauddin, Tufa, Hossain; Mendeley Data,
  v1, DOI 10.17632/42m5tb7yv9.1, https://data.mendeley.com/datasets/42m5tb7yv9 . Licence CC BY 4.0. Changes:
  relabelled into our taxonomy (bitter melon -> `bitter_melon`; cucumber, papaya, pineapple, banana, orange, tomato,
  eggplant), semi-fresh stage kept as `semi_fresh`, day-range suffixes dropped, re-split by inferred specimen.
  Ingestion code ported from @LemurTech22's pipeline (#21 -> #26).
- **MeatScan: An image dataset for machine learning-based classification of fresh and spoiled cow meat** - Mensah Gyening,
  Akoto, Owusu-Agyemang, Amoako-Banning, Takyi, Appiahene (Zenodo creator list, checked 2026-10-11); Data in Brief
  (2025), doi 10.1016/j.dib.2025.112045; Zenodo, doi 10.5281/zenodo.16764338. Licence CC BY 4.0. Changes: only the
  authors' originals (augmented copies excluded), subsampled per class, downscaled to 1280 px, relabelled `beef`.
- **Food Spoilage Status** - Roboflow Universe, workspace `food-monitoring`,
  https://universe.roboflow.com/food-monitoring/food-spoilage-status-ds1sc (v1). Licence CC BY 4.0. Changes: polygons
  converted to boxes, relabelled into our taxonomy (capsicum -> `bell_pepper`, bitter gourd -> `bitter_melon`).
- **DaFiF: Dataset for Fish's Freshness Problems** - Prasetyo, Suciati, Sutramiani, Adi Ananda, Dewi; Mendeley Data v1,
  doi 10.17632/vx4ptwk3pb.1 (article: Data in Brief 57 (2024) 111016). Licence CC BY 4.0. Changes: labelled fresh/spoiled
  from the storage day (days 1-3 / 9-11; 4-8 dropped), subsampled, downscaled to 1280 px, relabelled `fish`.

**Status 2026-10-11: eight sources are enabled** (`food_hvk7g` stays `pending`). The first five are under `mldata/raw/`;
MeatScan, DaFiF and Food Spoilage Status are in the table in section 2 and `docs/PIPELINE.md`:
| Source | Version / format | Images | Licence | Notes |
|---|---|---|---|---|
| `vegqual` | figshare 30596084 (= Roboflow v6) | 4,831 (3,207 kept) | CC BY 4.0 | |
| `fridge_objects` | Roboflow **v1**, exported yolov5pytorch (YOLO txt) | 963 (731/125/107) | CC BY 4.0 | names avocado, bacon, butter, cheese, eggs, lemon, milk, pepper, tomatoes, yogurt match the class_map; all boxes assumed fresh |
| `hien_fridge` | Roboflow **v12**, yolov8 | 1,912 (1378/363/171; 1,763 kept) | CC BY 4.0 | names apple, egg, milk_carton, others, soda_can, yogurt_container match; `others` dropped; assumed fresh |
| `fresh_stale_fruits_veg` | Kaggle raghavrpotdar (no version number; downloaded 2026-10-10) | 14,683 files, folder-per-class | **CC0 1.0** | stale -> spoiled, capsicum -> bell_pepper, bitter_gourd dropped (whole image); **`max_per_class: 250`** images per class x freshness (about 2,500 kept, so it does not swamp VegQual 3.2k / fridge 2.9k; chosen by a deterministic hash). Files are augmentations (`name.jpg_0_1039.jpg`) of far fewer originals; `Screen Shot <date> at <time>` names give capture times. |
| `agrifreshnet` | Mendeley Data **v1**, DOI 10.17632/42m5tb7yv9.1 (`Processed Data.zip`, 348 MB, downloaded 2026-10-10) | 14,160 files (24 folders x 590: 8 produce x fresh / semi_fresh / rotten). **After curation: 4,754 staged** (see below) | CC BY 4.0 | Ingested with `python -m pipeline ingest-dataset --adapter agrifreshnet --specimen-groups --exclude-source-augs --max-per-cell 300`. Cucumber, papaya, pineapple and bitter_melon are taxonomy classes (nothing dropped); `semi_fresh` is kept as its own label. **Heavily augmented**: 63% of the files are the authors' `aug_<n>_<original>` copies and 92% of all images (78-98% per class) have a flip/rotation-aware pHash <= 6 near-duplicate elsewhere in their class (some are look-alike backgrounds, not true copies). **Curation (orchestrator ruling B):** (1) all 8,943 `aug_` files are excluded (augmentation is our pipeline's job), leaving 5,174 originals after label-conflict and duplicate removal; (2) each class x freshness cell is capped at **300**, picked round-robin over split units (session / specimen) with a seeded hash order, not the first 300: 5 cells were above the cap (tomato/fresh 590, orange/semi_fresh 397, papaya/spoiled 332, banana/spoiled 301, ...) and 420 images were dropped, so 5,174 -> 4,754 staged (before/after per cell in `source.json` -> `curation` and in `dataset_report.json` -> `source_curation`; share of train in `train_share_by_source`). **Grouping (ruling A, used for this run):** timestamped files are grouped by 300 s capture session, untimestamped files by cross-stage specimen component (variant-aware pHash, <= 10, tightened per class to 6/4); the specimen+session union chains into 54% of the curated set, so it was not used. **AgriFreshNET and semi_fresh metrics must be labelled "cross-stage specimen overlap possible"**: a specimen photographed on different days in different stages can fall in different splits when its files are timestamped. Details: `docs/PIPELINE.md`. |
Kaggle in the notebook uses the `KAGGLE_API_TOKEN` secret as a Bearer token against the Kaggle REST API
(`/api/v1/datasets/download/<owner>/<dataset>`).

## 3. Label design (decision)
**Two-stage: detector for item NAME + separate crop classifier for fresh/semi_fresh/spoiled.**
- Detector classes = ~50 canonical food names (`ml/yolo/taxonomy.py`, id order = `data.yaml`, append-only).
  No `rotten_apple` classes.
- Freshness = `yolo26n-cls` trained on crops (`cls/{train,val}/{fresh,semi_fresh,spoiled}/`), applied to each detected box.
  **Three classes since 2026-10-10** (`fresh | semi_fresh | spoiled`, `taxonomy.FRESHNESS`): AgriFreshNET labels a middle
  "semi fresh" stage, which maps to a "use soon" signal in the app. Decision rule in `infer.TwoStage.label`: `spoiled` if
  p(spoiled) >= `SPOILED_THRESHOLD`, else `semi_fresh` if p(semi_fresh) >= `SEMI_FRESH_THRESHOLD`, else `fresh` (spoiled is
  checked first because a missed spoiled item is the costly error). Old 2-class weights still work and never emit `semi_fresh`.
  The serve layer coerces any other freshness value from a backend to `fresh` and logs a warning.
  YOLO QA gates stay binary (spoiled vs not-spoiled); see `docs/QA.md`.
  New detector classes `papaya`, `pineapple`, `bitter_melon` (AgriFreshNET) are appended to `taxonomy.py`
  (`bitter_gourd` now aliases to `bitter_melon`); all three are `produce_leafy` (short-life, 5 d in `expiry.py`) with food groups fruit/fruit/veggies.
- Why: (1) fresh/spoiled sources are labelled per-class-per-fruit (`rotten_apple`) and don't cover most fridge
  foods; a fused 2xN-class detector would have spoiled examples for only a few items and learn "apple => spoiled
  variants exist". (2) Spoilage is texture/colour on a crop and is the costly error (QA: spoiled recall >= 0.85);
  an independent head lets us tune `SPOILED_THRESHOLD` (lower = more recall) without retraining the detector.
  (3) Every fresh/rotten dataset also feeds the detector (name only) so nothing is wasted.
- Sources with no freshness info (fridge sets) get `freshness_default: fresh` -> flagged `known=false`;
  they are used for the detector and ground-truth only, **not** for classifier crops (unless
  `--include-assumed-fresh-crops`). **Consequence: held-out spoiled labels only exist where a source had them
  (mostly produce); QA spoiled-recall is therefore a produce-only statement.**
- Backend category mapping: each class -> one of `produce_leafy, produce_hardy, dairy, meat, seafood, bakery,
  eggs, leftovers, pantry_dry, frozen, other` in `taxonomy.CLASS_CATEGORY` (soft produce such as tomato,
  banana, berries counts as `produce_leafy` = short-life bucket; apple/citrus/root veg as `produce_hardy`).

## 4. Held-out split + lighting manifest (QA consumes this)
`prepare_dataset.py --sources sources.json --out DIR` writes:
```
DIR/data.yaml                  train: images/train  val: images/val  test: images/heldout
DIR/images|labels/{train,val,heldout}/   YOLO txt (class xc yc w h, normalised)
DIR/freshness/<split>/<stem>.txt   one line per label line: 0 = fresh, 1 = spoiled, 2 = semi_fresh
DIR/cls/{train,val}/{fresh,semi_fresh,spoiled}/*.jpg   classifier crops
DIR/heldout_gt.jsonl           ground truth (below)
DIR/heldout_manifest.csv       per-image metadata (below)
DIR/dataset_report.json        counts, dropped source labels, classes with no data
DIR/class_names.json           trained class id -> canonical taxonomy name (only classes that have data)
```
**ML-16: only classes with data are trained.** `data.yaml` lists the *active* classes (taxonomy order, contiguous ids
0..k-1) and `dataset_report.json` has `active_classes`. The weights carry those names, `infer.TwoStage` reads `r.names`
and maps each name through `taxonomy.category_for`, so inference/serve need no id translation (`ml/serve` unchanged).
`taxonomy.py` is untouched and still provides the canonical names and categories; a name added later appears
automatically once a source maps to it. Do not mix weights trained on the old 57-class ids with the new ones in the
same eval without reading `class_names.json`.
`dataset_report.json` (ML-20) also has: `dropped_images` split by reason (`only_unmodelled_objects`,
`mixed_with_unmodelled_object`, `all_boxes_unmapped`, `empty_label_file`), `empty_label_images`, `source_by_split`,
`heldout_images_by_lighting_method` and `heldout_boxes_by_lighting_method_class` (key `lighting/method`, then
`class/freshness`; report `synthetic` separately from `auto`/`manual`), and `crops` (expected/written/missing with reason).
- Split (ML-21), in three layers; groups are indivisible and are then assigned to splits:
  1. **Series / augmentation stem**: filename stem without `.rf.<hash>`, the Kaggle `_0_1039` tail, a `<cls>__<fresh>__`
     prefix and `Copy of `; trailing digits are stripped so numbered series (`Defected_begun_3`, `_4`) join one group.
  2. **Capture session**: capture time is *searched* in the name (`IMG20250926100615`, `IMG_20251004_163630`,
     `20250101_123456`, the same with a hyphen (`IMG-20250101-123456`) or trailing milliseconds (`IMG_20251102_075610660`, AgriFreshNET; the ms digits are ignored), 13-digit epoch ms in 2014-2033, `Screen Shot 2018-06-08 at 4.59.36 PM`), also in staged PR-B names such as
     `banana__fresh__IMG_20250101_123456.rf.<sha>.jpg`. Per source and clock format, photos <= `--session-gap` seconds
     (default **300**) apart are chained into one session. **No span cap** (the old 120 s cap cut sessions and leaked).
  3. **Perceptual near-duplicates**: 64-bit pHash (`dedup.py`, numpy only; agrees with `imagehash.phash` to <= 2 bits and
     gives identical "<= 6" decisions on 44,850 test pairs) with Hamming <= `--phash-threshold` (default 6), across all
     sources, merges groups. A merged component larger than `--max-unit-images` (600) is not stratified; it is forced into
     train (reported in `grouping.near_duplicates.images_forced_to_train_by_source`).
  Groups (sessions / series / merged near-duplicate clusters) are indivisible and are assigned by **greedy stratified
  balancing** on class x freshness (+ source + image count). Rules (orchestrator ruling, final):
  - A cell is **required in held-out** if it has >= 10 images and >= 2 independent units: sessions with >=
    `--min-session-images` (default **10**) images of the cell, or a pool of >= 2 smaller groups (independent single photos,
    e.g. web images). One whole session is then placed in held-out (least collateral first, then the largest session that
    leaves train at least as many images of the cell as were moved: apple/spoiled sessions 26/125/98/1 -> the 98 session is
    held out), while train keeps at least one session. Moves and collateral are listed in `required_cell_moves` and
    `heldout_session_upgrades`.
  - **Pooling (explicit interpretation, recorded per cell as `cell_decisions[cell].units`):** web photos are each their own
    1-image group, so counting only sessions would make every fridge cell non-measurable. Therefore groups that are
    *themselves small* (< `--min-session-images` images in total: a web photo or a complete one-shot session) and not part
    of a pHash-chained component are **pooled**; a pool of >= 2 such groups with >= 10 images of the cell counts as 2 units.
    A few images of a cell inside a LARGE session are *fragments* and are never pooled (reported as
    `ignored_small_session_fragments`, e.g. eggplant/spoiled's 3-image fragment). `units` lists `sessions_ge_min`,
    `pool_groups`, `pool_images`. Pooled groups are pHash-distinct (near-duplicates were merged into one group beforehand);
    the leakage gates run after pooling on the written files.
  - **Train keeps >= 50% of every measurable cell.** A violating cell is re-cut at session level by searching all
    train/val/held-out assignments of its (<= 7) movable sessions, scored jointly over every cell those sessions contain
    (potato/spoiled 160/77/6 coupled to potato/fresh: train 166 / held-out 77); if no cut works the whole cell goes to
    train and is marked not measurable. Actions are in `stratification.train_majority_actions`.
  - Otherwise the cell is **not measurable on held-out** and goes ENTIRELY to train (e.g. eggplant/spoiled 369 + 3 images,
    single-session cells banana, onion, orange). `stratification.cell_decisions` records, for every cell, the image and
    session counts, the session sizes, the decision, the reason and the train/val/held-out box counts.
  - No cell may exist only outside train (asserted; unit test `test_no_cell_exists_only_outside_train`).
  - Near-duplicates: groups whose images have pHash-64 Hamming <= 6 are merged, EXCEPT components larger than
    `--max-unit-images` (600) - look-alike white-background fruit photos chain into one 1,751-image component - which are
    left as separate capture groups; afterwards the (few) held-out/val images that still have a near-duplicate in another
    split are **dropped** (not moved), counted in `grouping.near_duplicate_drops`.
  The checks in `ml/eval/stratification_check.py` follow the same rules: the timestamped-session span rule now fires (ML-59), and the pHash merge keeps timestamped sessions as sessions and is capped like prepare's 600 (ML-60); a cross-split pHash pair is a warning, while `leakage_check.py`'s identity pHash <= 1% per source stays the gate. Roboflow rotations / crop tiles of one photo share a group (ML-50, `parent_stem`), and a cell demoted to not-measurable moves wholly to train (ML-53/56).
  `dataset_report.json.leakage_by_source` reports, per source, held-out originals with a train/val timestamp neighbour
  within 60 s / 300 s and pHash and (independent, coarser) dHash near-duplicates. **Reproducibility parameters** (all defaults): `--seed 42`, `--session-gap 300`, `--phash-threshold 6`, `--max-unit-images 600`,
`--min-session-images 10`, `--heldout 0.10 --val 0.10`, Kaggle `max_per_class: 250` per class x freshness (images picked by SHA1
of `seed:path`). Same sources + parameters give identical splits; QA copies live in `mldata/fwr_data_v2` / `fwr_data_v3`. `--session-gap 0` disables sessions. **Series grouping is a per-source option** (`"series_grouping": true` in sources.json: vegqual, hien_fridge, fresh_stale_fruits_veg); sources without it (the pipeline's staged sources, fridge_objects) get one group per original photo (the stem before `.rf.`, class prefix kept). All split/crop/freshness directories are always created, even when a split is empty. Fractions are image-count targets, but
  because sessions are big the real held-out share is lumpy (see the report).
- **Lighting tag**: auto from mean luma (<70 => `low`) and mean R/B (>1.35 => `warm`), else `normal`
  (`lighting_method=auto`; hand-correct via `--lighting-overrides file.csv` with columns `image,lighting` ->
  `manual`). Because public sets are mostly normal light, every `normal` held-out image also gets a
  **synthetic** `low` (x0.35 + noise) and `warm` (R x1.25, B x0.7) copy (`lighting_method=synthetic`,
  `variant_of=<original>`); disable with `--no-synth-lighting`. Report synthetic and real separately - synthetic
  tends to be easier than a real dim fridge.
- `heldout_manifest.csv` columns: `image` (path relative to DIR), `lighting` (normal|low|warm),
  `lighting_method` (auto|manual|synthetic), `source`, `group`, `n_boxes`, `n_spoiled`, `width`, `height`, `variant_of`.

### Eval JSONL formats (agreed with ML QA)
One JSON object per line, one line per image; `image` is identical in both files.
```json
{"image": "images/heldout/x.jpg", "lighting": "normal",
 "predictions": [{"name": "apple", "category": "produce_hardy", "freshness": "spoiled",
                  "confidence": 0.83, "bbox": [x1, y1, x2, y2]}]}
```
Ground truth (`heldout_gt.jsonl`) has the same shape with `"labels"` instead of `"predictions"` (`confidence`=1.0).
`bbox` is absolute pixels `[x1,y1,x2,y2]`. `predictions.jsonl` is produced with `--conf 0.10` (low floor so QA can
sweep thresholds) by `export_predictions.py`, or at the end of `train.py`.

## 5. Training on Colab (step by step)
1. Colab -> GPU runtime. Open `ml/yolo/train_colab.ipynb` (or clone the repo and `cd ml/yolo`).
   (Quick path: section 0. The steps below are the manual equivalent.)
2. `pip install -r requirements.txt` (ultralytics==8.4.175). Never paste API keys into cells; use Colab Secrets.
3. Download the sources into `/content/raw/<name>` (Roboflow: YOLO export at the versions in `sources.json`; Kaggle REST with `KAGGLE_API_TOKEN`) and ingest AgriFreshNET (`python -m pipeline ingest-dataset ... --specimen-groups --exclude-source-augs --max-per-cell 300`, see section 2). Copy
   use the repo's `sources.json` with the roots rewritten (the notebook does this).
4. `python prepare_dataset.py --sources sources.json --out /content/fwr_data`; read `dataset_report.json`
   (classes with no data, dropped labels). Fix mapping before training.
5. `python train.py --data /content/fwr_data --project <RUN_DIR> --resume` (detector 80 ep, classifier 30 ep, then exports; `--semi-fresh-threshold` sets the semi_fresh cut-off of the exported predictions). Exports
   **`last.pt` by default** (`--weights last`): val has no potato and no apple/spoiled (ML-28), so val-picked
   `best.pt` would be blind to them. Fixed epochs; all metrics come from the held-out split.
6. Collect `runs/export/`: `detector.pt`, `freshness.pt`, `predictions.jsonl`, `heldout_gt.jsonl`, `heldout_manifest.csv`.
   Give the last three to ML QA (`ml/eval/`); weights are gitignored - share via Drive/release and link here.
CLI equivalent of the notebook: `train.py`. Same code path: `infer.TwoStage` is used for export and serving.

### 5a. Surviving Colab disconnects (checkpoints on Drive + auto resume)
- **Layout** (`RUN_DIR = /content/drive/MyDrive/fwr_runs/<RUN_ID>/data_<DATA_VER>` (+`_dry` for the dry run), passed as `train.py --project`): `det/weights/{last,best}.pt`,
  `cls/weights/{last,best}.pt`, `det/results.csv`, `export/`, plus `fwr_data.tar` (prepared dataset), `fwr_data/` (small readable copy of
  `dataset_report.json`, `data.yaml`, `class_names.json`, `heldout_manifest.csv`) and `fwr_data.sha256`.
- **Per-epoch save cost.** Ultralytics writes `last.pt` every epoch (`trainer.save_model`, `engine/trainer.py` ~L780-835) and `best.pt` when
  fitness improves. Measured on MPS with yolo26n: mid-training `last.pt` = 21 MB (EMA weights + AdamW state, fp16), final stripped file 5.4 MB.
  Scaling by size (yolo26s.pt is 20 MB stripped, ~3.7x n) puts an in-training yolo26s `last.pt` at roughly 60-80 MB. At Drive-mount
  write speeds (order of 10-30 MB/s) that is a few seconds per epoch against minutes of compute per epoch, so **`save_period` is not
  used**: it would only add `epochN.pt` files (more Drive space, no resume benefit). Residual risk: the write is not atomic, so a VM death
  in the middle of the write can leave a truncated `last.pt`; `train.py --resume` detects an unreadable `last.pt` and falls back to `best.pt`
  (also a full checkpoint during training), else restarts that stage.
- **Resume semantics, verified in ultralytics 8.4.175 source** (`site-packages/ultralytics/`):
  - `YOLO.train(resume=True)` (`engine/model.py` L877-886) uses the loaded checkpoint as the resume point only if
    `ckpt["epoch"] >= 0` and it still has `optimizer`; otherwise it logs a warning and **silently starts a new training**.
  - `BaseTrainer.check_resume` (`engine/trainer.py` L1020-1065) reloads `ckpt.train_args` as the run's args, so epochs, imgsz, optimizer,
    lr, project/name etc. come from the checkpoint. Only `imgsz, batch, device, close_mosaic, save_period, workers, cache, patience, time, freeze, val, plots, ...`
    can be overridden (other differing args only produce a warning); `data` is overridden by the one passed in. `train.py` passes `data, device, batch, imgsz`.
  - `resume_training` (L1124-1132) asserts `0 < ckpt.epoch + 1 < epochs`, else **raises "training to N epochs is finished, nothing to resume"**.
    That only happens for a complete but still *unstripped* checkpoint. A *stripped* finished one (`epoch == -1`) never reaches the assert:
    `model.py` L877-886 just warns and **silently starts a new training**. The skip logic in `train.py` (`ckpt_status`) is what prevents that silent retrain.
    A resumed run continues at epoch `ckpt.epoch + 2` (1-based) and appends to the same `results.csv` (L218: only unlinked when not resuming).
    Caveat: `results.csv` is written before `last.pt` is saved, so a kill in between (or a fallback to `best.pt`) leaves a duplicate epoch row after the
    resume. Nothing reads `results.csv` for decisions; dedupe by `epoch` if you plot it.
  - Completion marker: at the end of training `final_eval` (L1001-1010) calls `strip_optimizer(last.pt)` (`utils/torch_utils.py` L897-960), which
    sets `epoch = -1`, `optimizer = None`. So `ckpt["epoch"] == -1` means **finished**. If the process dies between the last epoch and `final_eval`,
    `epoch + 1 >= epochs` with the optimizer still present: `train.py` strips it itself and treats the stage as finished.
  - `train.py` therefore decides per stage (`ckpt_status` / `train_stage`): no checkpoint -> train fresh; `epoch == -1` (or `epoch+1 >= epochs`) ->
    skip training; otherwise `YOLO(last.pt).train(resume=True, ...)`. Detector and classifier are handled independently, and the
    `--weights last|best` selection, `det.val`, export and `export_predictions` run after a resumed or skipped stage exactly as after a fresh one.
    If `--epochs` differs from the finished checkpoint's epochs it prints a note (use a new `RUN_ID` to retrain).
- **Dataset reuse.** Cell 4 builds the dataset, runs the gates, then caches it on Drive. The tar is created with `subprocess.run(..., check=True)`
  into `fwr_data.tar.part`, the whole archive is re-read (`tarfile`, fails on truncation) and its file counts for `images/labels/freshness/cls`
  must equal the local dataset, then it is renamed and the small files are copied. `fwr_data.sha256` (JSON: sha256 of `dataset_report.json`, tar bytes,
  member count, per-dir file counts) is written **last** as the commit marker; any failure removes the `.part` and leaves no stamp. Ultralytics' `*.cache`
  files are excluded from the tar and the counts. On resume the stamp matches, cells 2-3 skip secrets and downloads, and cell 4 untars (`check=True`) to the local
  `/content/fwr_data` (a tar because the set is ~39k small files; copying them one by one through the Drive mount is far slower, and training
  straight from Drive images would stall the data loader). The restored per-dir counts and `dataset_report.json` must equal the stamp, otherwise cell 4 deletes
  the stamp and stops (Run all again rebuilds). Then **every gate re-runs on the restored copy**; the leakage and stratification checks delete their JSON
  first and must exit 0, so a crashed check can never reuse a stale result.
  Change sources or code -> use a new `RUN_ID` (the cache is keyed by run, not by code). `RUN_ID` must match `^[A-Za-z0-9][A-Za-z0-9_-]*$`.
- **Determinism of `prepare_dataset.py`:** `--seed` default 42 feeds sha1-based per-image/per-group ordering (`group_hash`, `collect`), traversal is
  `sorted(...)`, and the synthetic low/warm variants use `np.random.default_rng(seed)` (`lighting.py`). Same pinned inputs -> same split. The inputs are
  pinned for VegQual (figshare file id) and Roboflow (versions) but **not for the Kaggle dataset** (latest download), so a fresh prepare could differ;
  that is another reason a resume reuses the cached copy instead of rebuilding.
- **Local verification (MPS, 2026-10-10):** tiny synthetic dataset, `train.py --epochs 3 --cls-epochs 2 --det-model yolo26n.pt --device mps --resume`;
  killed (SIGKILL) after detector epoch 1 was saved, rerun resumed "from epoch 2 to 3" and finished (results.csv rows 1,2,3, no duplicates), classifier trained
  fresh, export written; a third run skipped both trainings and only exported.

## 5b. Training on Apple Silicon (MPS), measured 2026-10-10
`train.py --device auto|mps|cuda-index|cpu` (default auto: cuda, then mps, then cpu). Venv and data live outside
the repo in `mldata/` (`.venv-train`, `fwr_data`, `runs/`). Weights `yolo26n.pt`, `yolo26s.pt`, `yolo26n-cls.pt` downloaded fine.
Smoke runs used **VegQual only** (3,207 images after dropping gourd images: train 2,493 / val 346 / heldout 368;
cls crops train 6,299 / val 768), imgsz 640, batch 16:
| Run | s/epoch |
|---|---|
| yolo26n det, MPS | ~105-116 (epoch 1 incl. val 116) |
| yolo26s det, MPS | ~173 (1 epoch incl. val) |
| yolo26n-cls, MPS, 224px, batch 64 | ~22-26 |
These are VegQual-only timings. Estimate for the full merged run (yolo26s, 80 epochs, ~4.7k train images with the two
Roboflow sets): ~5.5 min/epoch -> **~7.5 h** (range 6.5-9 h) + ~15 min classifier. Scales linearly with images; assumes MPS
throughput stays constant (no thermal throttling) and similar boxes per image.

### 5c. C4 plumbing check (2026-10-10): contaminated (ML-25), pipeline check only
`export_predictions.py --device mps` was run with the yolo26n smoke weights (trained on the OLD split, 57-class ids,
VegQual only) over the new 4-source held-out set into `mldata/runs/smoke_export/` (predictions.jsonl, heldout_gt.jsonl,
heldout_manifest.csv, class_names.json, dataset_report.json). These predictions are **contaminated (ML-25)**: the smoke
model saw many of these images, and has never seen the fridge/Kaggle classes. Use them to test the metric plumbing only; do not
quote any number from them.

## 5d. FAST profile (data-owner ruling, 2026-10-11)
The full run (yolo26s, 640 px, 80 epochs on 11,777 train images) takes ~4-5 h on a free T4, longer when Colab's 2 vCPUs can't keep up with
decoding + mosaic. The owner asked for ~30 min, so cell 1's `FAST` checkbox (default **on**) runs:

| | FAST | full |
|---|---|---|
| detector | `yolo26n.pt`, 512 px, batch 32, **30 epochs** | `yolo26s.pt`, 640 px, batch 16, 80 epochs |
| detector train set | **capped**: <= `DET_CAP` (400) boxes per food, `ml/yolo/cap_detector.py` (~4.9k of 11.8k images) | all |
| classifier | `yolo26n-cls`, 224 px, batch 128, **10 epochs**, all crops | same model, batch 64, 30 epochs |
| cache / val | `--cache ram`, `--no-epoch-val` (Ultralytics still validates the last epoch) | no cache, val every epoch |
| checkpoints | `data_<DATA_VER>_fast[_dry]/` | `data_<DATA_VER>[_dry]/` |

- **Why the cap is safe for freshness:** the detector only learns food names; fresh / semi_fresh / spoiled comes from the crop classifier,
  which still trains on every crop. The cap is a symlink view of the train split only: val, held-out (incl. synthetic lighting copies),
  `heldout_gt.jsonl` / manifest and `cls/` are the full set, so the leakage / stratification gates and every held-out metric are unchanged
  and comparable with a full run. Foods with <= 400 boxes (butter, bacon, cheese, lemon, cucumber, papaya, ...) keep all of them.
  Selection is round-robin over (food, freshness, source) cells, multi-object images first, then a stable hash order (no RNG); on the local
  rebuild it kept 4,881 of 11,777 images with boxes 69% fresh / 25% spoiled / 6% semi_fresh (full set 66 / 29 / 5). `cap_report.json`
  in the view lists kept/total boxes per food.
- **Cost:** a nano detector at 512 px is less accurate than yolo26s at 640, mostly on small objects in fridge-shelf photos. If the
  held-out detector gates in `docs/QA.md` come up short, untick `FAST` (or raise `DET_CAP` / pass `--det-model yolo26s.pt`) for the next run.
- **Time is an estimate, not measured on a T4**: ~4.9k images/epoch, CPU-bound at roughly 120-150 img/s with RAM cache -> ~35-40 s per
  epoch -> ~20 min detector, ~5 min classifier, ~3 min export. The Ultralytics progress bar shows the real s/epoch; record it here after the
  first run.
- Don't train on `pipeline augment-lighting` output in FAST mode: it multiplies the train images (and see `docs/PIPELINE.md` for the lighting sign-off rule).

### 5e. Run log
**`fwr_20261011` (first real FAST run, Colab T4, 2026-10-11).** Data version `a4729025` (`sources.json` hash); Drive folder
`MyDrive/fwr_runs/fwr_20261011/data_a4729025_fast/`.

| Step | Result |
|---|---|
| Detector train set (`DET_CAP` 400) | 4,848 of 11,517 train images; boxes 6,052 fresh / 569 semi_fresh / 2,190 spoiled |
| Detector | `yolo26n`, 512 px, 30 epochs, ~26 min (10:54-11:20 UTC) |
| Classifier | first attempt OOM-killed at the start (ML-69, fixed in #88); rerun without the RAM cache: 10 epochs at ~100 s/epoch (~17 min), train loss 0.61 (epoch 1) -> 0.12 (epoch 8) |
| Export (11:58-12:01 UTC) | all 7 files. `detector.pt` 5.45 MB and `freshness.pt` 3.19 MB pass their zip CRC and load (23-class detector, 3-class fresh / semi_fresh / spoiled classifier); local copy `../mldata/models/fwr_fast_20261011` |
| Held-out predictions | **not scored.** `predictions.jsonl` on Drive (and the copy downloaded from it) is truncated by Drive sync: 582,423 NUL bytes, ~3.1k of 5,205 rows parse. **No metrics from this run may be quoted.** |
| Serving | weights served by `ml/serve` and checked end to end (photo -> `/items/from-photo` `source: "yolo"` -> Gemini enrichment -> `POST /items`). One fridge photo: names right, 2 of 3 fresh items called spoiled (an anecdote, not a metric; the photo may be in this build's train split) |

**Next:** re-export and score. Open the notebook from `main`, keep `RUN_ID=fwr_20261011`, `FAST` on, `DRY_RUN` off, Runtime ->
Run all: both stages are already finished on Drive, so they are skipped and only the export is rewritten (a few minutes). Take the
predictions from the `export.zip` that cell 6 downloads (or run `drive.flush_and_unmount()` before reading Drive), check that
`predictions.jsonl` has as many rows as `heldout_gt.jsonl`, then ML QA runs `ml/eval/detection_metrics.py` and `check_thresholds.py`.

## 6. Running the service on a GPU box
```
cd ml
pip install -r serve/requirements.txt        # torch CUDA build first
YOLO_WEIGHTS=/models/detector.pt FRESHNESS_WEIGHTS=/models/freshness.pt \
OCR_BACKEND=glm GEMINI_API_KEY=... \
gunicorn -w 1 --threads 4 -t 120 -b 127.0.0.1:8000 serve.wsgi:app
# or: docker build -f serve/Dockerfile -t fwr-ml ml/ && docker run --gpus all -p 127.0.0.1:8000:8000 -v /models:/models --env-file .env fwr-ml
```
Backend env: `ML_SERVICE_URL=http://<gpu-host>:8000` (tunnel/VPN; the service has **no auth** - never expose publicly).
Env knobs: `DETECTOR_BACKEND=fake|yolo` (default yolo if `YOLO_WEIGHTS` set else fake), `OCR_BACKEND=fake|glm`
(default fake), `YOLO_CONF` (0.25), `SPOILED_THRESHOLD` (0.5), `SEMI_FRESH_THRESHOLD` (0.5), `YOLO_DEVICE`, `GLM_OCR_MODEL`, `GEMINI_API_KEY`
(optional; enables Gemini structuring of OCR text, else the deterministic parser alone), `GEMINI_MODEL` (the same
value as the backend's, see `docs/DECISIONS.md`; unset falls back to Google's `gemini-flash-latest` alias, never a
pinned old id), `MAX_UPLOAD_MB` (12). Gemini's structured answer is validated by `clean_structured()` before it is
returned: numbers given as strings (`"$3.48"`, `"1,29"`) are parsed, nameless lines dropped, a non-positive quantity
becomes `null`, so `/ocr` always returns real numbers to the backend.
Without `FRESHNESS_WEIGHTS` every item reports `freshness: "fresh"` - set it for real use.
Models load on first request (first call is slow); a failed load returns 500 `inference_failed`, which the backend
should treat as "fall back to Gemini vision" (docs/ARCHITECTURE.md).

Contract: `POST /detect` (multipart `image`, form `mode`=fridge|single; default fridge) ->
`{"candidates":[{name,category,food_group,confidence,freshness: fresh|semi_fresh|spoiled,bbox|null}],"model"}` (single = top-1 only; an empty list means
nothing detected); `POST /ocr` -> `{"lines":[{name,quantity,price}],"total","raw_text"}`; `GET /health`.
Errors `{"error":{"code","message"}}`: 400 `missing_image|invalid_image|invalid_mode`, 413 oversize, 500 `inference_failed`.

## 7. Receipt OCR
GLM-OCR (`zai-org/GLM-OCR`, MIT; pipeline also uses Apache-2.0 PP-DocLayoutV3 in the official SDK, not used here)
loaded per its model card: `AutoTokenizer` + `AutoModelForMultimodalLM`, chat template with image + prompt
`"Text Recognition:"`. Then `parse_receipt_text` (deterministic): item+price, `N @ unit`, `N x unit`, weighted
`1.23 lb @ $2.99/lb`, name-line/price-line splits, leading store item numbers (e.g. `E 1234567`) and UPC/PLU codes before or after the name stripped, qty-first `3 @ 1.25  NAME  3.75` lines, any "... Total" summary line (Merchandise Total etc.) excluded, `SUMME`/`GESAMT` totals and comma decimals accepted, OCR-spaced `4 .29` repaired, trailing tax flags dropped, markdown tables
tolerated; **voids** (`VOID`/`VOIDED`/`** VOID **`/`ITEM VOID` + name and/or price) delete the latest earlier item with the same price and a similar name, and are silently dropped if nothing matches; **multi-buy** `N @ M/$X.XX` and `N @ M for $X.XX` give quantity N and the printed line price (or N/M*X if absent); SUBTOTAL/TAX/payment/coupon/discount/negative lines excluded (**skip words are structural**: unambiguous phrases like `INSTANT SAVINGS`, `CHANGE DUE`, card masks skip anywhere; ordinary words like instant/credit/coupon/discount/promo/change/cash/member only skip a line when the amount is negative or the word ends the label, so `INSTANT OATMEAL` or `Credit Card Cookies` stay items); `total` (case-insensitive) from TOTAL/GRAND TOTAL/ORDER TOTAL/BALANCE DUE/BALANCE TO PAY/AMOUNT DUE/TOTAL DUE/YOU PAY (Subtotal, Merchandise/Item Total, Total Savings, Total Tax never count)
(never invented; `null` if absent). Abbreviations are kept as-is (the backend/Gemini expands them).

## 8. Known limitations / not verified
- **Not run here:** any training, YOLO inference, GLM-OCR loading, or Docker build. Only the fakes, parser, dataset
  prep (on synthetic images) and the Flask contract are tested. Ultralytics/transformers API usage in `infer.py`,
  `train.py`, `GlmOcrEngine` is written against docs and unexecuted - expect small fixes on first GPU run
  (notably the GLM-OCR image input via a temp file path and its required transformers version).
- Eight sources are enabled (see section 2); `food_hvk7g` is pending. Named data risks (beef train-only and scene-confounded, fish tray colour tracks the label, fish held-out is one unseen batch) are in `docs/PIPELINE.md`; report spoiled recall per source with Wilson CIs.
- Domain gap: clean-background produce vs cluttered fridge shelves; small fridge sets; ~50 classes will be
  uneven (see `classes_with_no_data`). Freshness has training signal only for produce, beef (MeatScan) and fish (DaFiF); milk, eggs and other dairy have none.
- `semi_fresh` training signal exists only for AgriFreshNET's 8 produce types (MeatScan, DaFiF and Food Spoilage Status are fresh/spoiled only); QA reports its precision/recall but does not gate it.
- Synthetic lighting is an approximation of real low/warm light. Auto lighting tags can misfire on red/orange-heavy scenes.
- Parser is heuristic: receipts with item names that look like prices/keywords (e.g. an item containing "CASH" or "TAX")
  or multi-line wrapped names can be dropped or split. Real-receipt accuracy needs ML QA's >=20-receipt set.
- Service is unauthenticated, single-worker.
