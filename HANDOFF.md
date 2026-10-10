# Handoff

_Last updated: 2026-10-10 (evening): data pipeline session on the Linux VPS, branch `feat/data-pipeline`. Checkpoint 1 notes below still apply._

## Current status
**The backend and ML are built, QA-signed and merged. The design is waiting for team approval. iOS hasn't started.**

Everything that could be built and verified without a Mac, a GPU or a Gemini key is done. Every
merged PR has a QA sign-off recorded in [`docs/QA.md`](docs/QA.md), and the orchestrator re-ran
each suite independently before merging.

| Area | State | Evidence |
|---|---|---|
| Backend core (auth, items, **removal flow**, events, impact, tips, AI endpoints) | merged #4 | 100 tests, 92% coverage |
| Backend social (friends, groups, group pantries, Food Pantry, requests) | merged #5 | 158 tests total, 94% coverage |
| ML: YOLO26 pipeline, receipt OCR, inference service, eval harness | merged #3, parser fixes #8 | parser 97.2 / 100 / 100 on blind set v2 (then 100% after ML-10); contract 14/14. **No model trained yet** |
| Design: 10 screens (incl. photo review + Recipes) + design system + `Theme.swift` | merged #2, #7 | **awaiting team approval**: https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx (private until the owner shares it) |
| iOS app | **not started**: only the tab shell + `Theme.swift` | needs Xcode, and design approval first |
| CI | **enabled** in `.github/workflows/` (backend, ML, iOS) | moved from the parked `ci/` folder on the Mac |
| **Data pipeline** (`pipeline/`): dataset ingestion, receipt inbox (GLM-OCR), category cleanup, lighting augmentation | branch `feat/data-pipeline`, PR pending | see "Data pipeline session" below |
| **Freshness: 3 classes** (`fresh / semi_fresh / spoiled`) | same branch | ML QA PASS: eval 109, serve 12, ocr 89, yolo 3 |

## Data pipeline session (2026-10-10, evening)
- **`pipeline/`** (`python -m pipeline`, docs in [`docs/PIPELINE.md`](docs/PIPELINE.md)):
  - `ingest-dataset`: safe nested-zip extraction, adapters, dedupe, label conflicts and leakage groups.
  - `prepare`: wraps `ml/yolo/prepare_dataset.py`.
  - `augment-lighting`: 7 presets on train and val only; heldout is left untouched.
  - `ingest-receipts`: a GLM-OCR inbox with `glm`, `service` and `fake` engines, a per-file timeout with worker restart, quarantine, and per-line category tagging.
- **AgriFreshNET** (from `~/Downloads`) is ingested:
  - 14,103 images, about 4.7k each of fresh, semi_fresh and spoiled.
  - 34 cross-class conflict files dropped.
  - Prepared into 11,060 train, 1,569 val and 1,474 heldout images. Augmented into 33,180 train and 4,707 val images.
  - The data lives in `pipeline/data/` on the VPS, which is gitignored. Re-create it with the commands in PIPELINE.md.
- **Freshness has a third class, `semi_fresh`.** It touches the taxonomy, prepare, infer (`SEMI_FRESH_THRESHOLD`), the serve contract, the Gemini hint and `docs/API.md`. The eval reports it but doesn't gate it.
- **New detector classes:** `papaya`, `pineapple` and `bitter_melon`, appended to the class list.
- **Not run:** real GLM-OCR (no GPU) and the backend suite (no Postgres on the VPS; CI runs it). `test_from_photo_passes_semi_fresh_through` was added but hasn't run yet.
- **Follow-ups:**
  - iOS needs a "use soon" badge for `semi_fresh`. It must go through design first.
  - Optionally, the backend could shorten predicted expiry for semi_fresh items, using AgriFreshNET's day ranges (kept in `manifest.csv`).
  - Train on `pipeline/data/augmented` on the GPU box.
  - Verify AgriFreshNET's licence.

## Done this session
- Bootstrap (#1): `CLAUDE.md`, the docs set, and the scaffold.
- Wave 1, run in parallel with paired QA agents: backend core (#4), ML (#3) and design (#2).
  - QA sent two failures back: **BE-1**, a 500 on `/impact` for new users, and the **OCR parser** at 84.9% line recall. Both were fixed and re-verified before merge.
  - ML QA added a **blind holdout** so the parser's numbers aren't overfit.
- Wave 3: backend social (#5), with a per-user visibility test matrix.
- After the checkpoint: photo-review and Recipes screens (#7), and receipt-parser fixes ML-7 to ML-10 (#8), verified on a new blind set.
- Checkpoint: `DECISIONS.md` (YOLO26, CO₂e factors, shelf-life table, design choices), QA results
  folded into `QA.md`, and updates to `SETUP`/`ARCHITECTURE`. `TEST_DATABASE_URL` was added to
  `.env.example` and CI, and an ML CI job was added.

## Next steps (on the Mac)
1. ~~**Enable CI.**~~ Done: workflows live in `.github/workflows/`.
2. **Set up** per `docs/SETUP.md`: `.env`, `.venv`, `docker compose up -d --build`, then
   `CREATE DATABASE fwr_test`, `flask db upgrade` and the backend suite. **First run of
   `docker compose up` and the first Swift compile both happen here**, because neither was
   possible on the VPS.
3. **Approve the design.** Review the canvas, request changes there, and record the approval in
   `docs/design/README.md`.
4. **Wave 2: iOS builder + iOS QA**, once the design is approved. Build SwiftUI from
   `docs/design/screens/` and `DESIGN_SYSTEM.md`, behind an `APIClient` protocol with a mock, then
   wire it to the real API. Bundle the Outfit font (see `DESIGN_SYSTEM.md`).
5. **ML on a GPU** (Colab): fill the dataset class maps (`ml/yolo/sources.example.json`, licences
   unverified), train per `docs/ML.md`, export predictions, and run `ml/eval` against the
   thresholds. Run `ml/serve` and point `ML_SERVICE_URL` at it.
6. **Gemini:** add `GEMINI_API_KEY` and a real `GEMINI_MODEL`, then run the live parse-text, recipes
   and photo-fallback calls once.
7. **Wave 4, integration QA:** the whole stack in Docker, walking the demo path (photo add →
   expiry → remove → dashboard).
8. **Wave 5, UI review:** Impeccable critique/polish and web-design-guidelines, only once the UI is
   feature-complete.

## Open questions / blockers
- **AgriFreshNET licence** is unverified. Check it before publishing any results.
- **`GEMINI_API_KEY`** and the model id.
- **Who uploads to TestFlight**, and which Apple Developer team and bundle id to use.
- **How the phone reaches the API** during the demo (same Wi-Fi as a laptop, a tunnel, or a hosted backend).
- **Design approval** from the team. The canvas is private, so share it from its Share menu.
- **Dataset licences and classes**: the agent's fetches were blocked, so a human has to check them.
- The original brainstorm doc was never attached. `docs/IDEA.md` was written from the brief.

## QA status
- **Backend:** PASS, 158/158 with 94% coverage. No open bugs.
- **ML:** parser, service contract and harness PASS. **YOLO is not evaluable yet.** Open bugs:
  ML-11 to ML-14, all low. Both holdouts have now been used for fixing, so the next parser change
  needs a fresh blind set v3.
- **iOS and integration:** not run yet.

The full log and bug list are in [`docs/QA.md`](docs/QA.md).

## How to run everything
Full detail is in `docs/SETUP.md`. The short version:
```bash
cp .env.example .env                                    # fill in
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
docker compose up -d --build && curl 127.0.0.1:5055/health
docker compose exec db psql -U fwr -d fwr -c 'CREATE DATABASE fwr_test'
(cd backend && ../.venv/bin/flask --app wsgi db upgrade && ../.venv/bin/pytest -q --cov=app)
(cd ios && xcodegen generate && open FoodWasteReducer.xcodeproj)
```
