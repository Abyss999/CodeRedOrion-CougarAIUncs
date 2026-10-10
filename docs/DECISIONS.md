# Decisions

Newest first. Each entry: date, decision, why, alternatives considered.

## 2026-10-10 — Data pipeline, AgriFreshNET, third freshness class
- **Freshness has three classes: `fresh | semi_fresh | spoiled`.** *Why:* AgriFreshNET labels a middle stage (with day ranges), and "use soon" is exactly the nudge that prevents waste. *How:* the crop classifier learns 3 folders; `spoiled` is decided first (`SPOILED_THRESHOLD`), then `semi_fresh` (`SEMI_FRESH_THRESHOLD`), else `fresh`, so spoiled recall is never traded for the new class. The `/detect` and `/items/from-photo` `freshness` field gains the value `semi_fresh`; the sidecar code is `2` so old `0/1` data stays valid. QA reports semi_fresh but does not gate it until a trained model gives a baseline. *Alternatives:* fold semi_fresh into fresh (loses the signal) or into spoiled (false alarms on edible food).
- **Data pipeline lives in `pipeline/`** and reuses `ml/yolo` and `ml/ocr` by import. *Why:* one taxonomy, one parser, one dataset builder; the pipeline only adds ingestion (adapters, dedupe, label conflicts, leakage groups), the receipt inbox (timeouts, quarantine, category cleanup) and lighting augmentation.
- **Lighting augmentation is a separate step that never touches heldout.** *Why:* keeps the ML QA lighting gates comparable; every variant is logged so a harmful preset can be dropped.
- **Identical images filed under two classes are dropped**, not resolved by first-seen. AgriFreshNET has 17 such Fresh/Semi-fresh orange pairs.
- **AgriFreshNET detector classes appended:** `papaya`, `pineapple`, `bitter_melon` (produce_leafy). `bittergourd` now maps to `bitter_melon` (it pointed at `other`, which silently dropped the label).

## 2026-10-10 — Wave 1 decisions (backend core, ML, design)
- **YOLO26 via `ultralytics==8.4.175`.** That was the latest on PyPI on 2026-10-10, and Ultralytics' docs recommend YOLO26 for new projects (YOLO11 is the mature fallback). It is **AGPL-3.0**: fine for this public repo, but it matters if the code is ever closed. Details are in `docs/ML.md`.
- **Two-stage vision.** The detector predicts food *names* (about 50 classes, `ml/yolo/taxonomy.py`), and a separate `yolo26n-cls` classifier labels each crop fresh or spoiled. *Why:* the fridge datasets have no freshness labels and the produce datasets have no fridge scenes. The consequence is that spoiled recall is effectively a produce-only number.
- **The receipt parser is deterministic.** It turns GLM-OCR text into lines and a total, with an optional Gemini structuring hook. *Why:* it can be tested on CPU, it costs nothing to run, and QA can gate it.
- **The backend calls the ML service and falls back to Gemini vision** when `ML_SERVICE_URL` is unset *or the service errors*. Receipts have no fallback and return 502.
- **`food_events` primary key is `(id, time)`.** A hypertable's unique keys must include the partition column.
- **CO₂e factors** (kg CO₂e per kg of food) are rounded category averages from Poore & Nemecek (2018, *Science* 360), via Our World in Data. They live in `backend/app/services/impact.py`:
  produce_leafy 0.5 · produce_hardy 0.7 · dairy 4.5 · meat 15.0 · seafood 6.0 · bakery 1.4 · eggs 4.7 · leftovers 3.0 · pantry_dry 1.5 · frozen 2.5 · other 2.0.
  Weight is converted from quantity and unit (kg, g, lb, oz, l, ml, gallon, cup, dozen). Anything else uses a per-category weight per piece.
- **Default shelf life** in days (fridge / pantry / freezer) is condensed from USDA FSIS FoodKeeper guidance and lives in `backend/app/services/expiry.py`:
  produce_leafy 5/2/240 · produce_hardy 21/7/300 · dairy 10/1/90 · meat 3/1/180 · seafood 2/1/120 · bakery 10/4/90 · eggs 28/7/120 · leftovers 4/1/90 · pantry_dry 180/365/365 · frozen 2/1/270 · other 7/30/90.
- **The final category list** is the 11 above. They are enforced by a CHECK on `items.category`.
- **Design was done on a Claude Design canvas**, the Artifact Design type at https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx, rather than through a separate "Claude Design MCP", which wasn't installed. The sources are mirrored in `docs/design/screens/`. Type is **Outfit** (display) with **SF Pro** (body). Every text color pair was checked for WCAG AA by computing the ratios, and the chart pair was checked for colorblind separation.

## 2026-10-10 — Bootstrap decisions
- **XcodeGen for the iOS project.** `ios/project.yml` is the source of truth; the `.xcodeproj` is
  generated and gitignored. *Why:* agents can't safely hand-edit `.pbxproj`, and it merges badly
  across parallel branches.
- **iOS builds and tests in CI on macOS runners** (`.github/workflows/ios.yml`), free for this
  public repo. Backend and ML tests run in CI too (`backend.yml`, `ml.yml`). *Why:* gives iOS QA a reproducible gate that doesn't depend on whose Mac is open.
- **ML training/inference runs off-box** (Colab / GPU), behind `ML_SERVICE_URL`, with a
  **Gemini-vision fallback** in the backend. *Why:* no GPU on the dev server; the demo must not
  depend on a GPU being up.
- **One Postgres database with TimescaleDB**; `food_events` is a hypertable, state lives in normal
  tables. *Why:* Tigerdata is the stack's time-series store and it's an extension, not a second DB.
  Image pinned to `timescale/timescaledb:2.17.2-pg16`.
- **Removal is a soft delete + an event in the same transaction**; impact numbers are always
  computed from events, never stored as totals. *Why:* one source of truth for the dashboard.
- **Flask + Flask-SQLAlchemy + Flask-Migrate**, JWT auth, gunicorn in Docker.
- **Ports bind to `127.0.0.1`** (API 5055, DB 5433).

## Open — to decide and record here
- **Gemini model id** (`GEMINI_MODEL`): pick the current Flash-class model once a key exists.
- **Dataset class maps:** `ml/yolo/sources.example.json` starts empty because Roboflow and figshare blocked the agent's fetches. Open each dataset page, confirm its licence and classes, and fill in the maps before training.
- **Demo connectivity:** how the phone reaches the API (same Wi-Fi as a laptop, a tunnel, or a hosted backend).
