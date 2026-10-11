# Handoff

_Last updated: 2026-10-10 (checkpoint 2). Work is now split across two sessions. The VPS session
(`mobile-food`) orchestrates: it reviews and merges PRs and owns `CLAUDE.md`, `HANDOFF.md`,
`docs/QA.md`, `docs/DECISIONS.md` and the design canvas. The Mac session (`food-waste`) does all
Mac and compute work as builder + QA pairs, and opens PRs without merging them._

## Current status
**Backend, ML pipeline and data are built, QA-signed and merged (PRs #1–#35, none open). The
first full model training run on Colab is ready for the owner. The design is waiting for final
approval, and the iOS screens (Wave 2) haven't started.**

| Area | State | Evidence |
|---|---|---|
| Backend: auth, items, **removal flow**, events, impact, tips, social, AI endpoints | merged | 523 tests, 96% coverage (#35) |
| Backend: `food_group` + recipe `macros`, receipt keywords and abbreviations, Gemini token/cost logging | merged #20, #22, #35 | live Gemini verified on `gemini-3.8-flash`; `scripts/gemini_cost.py` |
| Docker stack | **runs on the Mac** | from-scratch `compose up` works; migrations run on start (#13); db `start_period` (#14) |
| CI | live (`backend`, `ml`, `ios`, `pipeline`) | green on every merged PR |
| ML: receipt parser | merged | 100/100/100 on all fixture sets; ML-11–14 open (low) |
| ML: data (4 sources + AgriFreshNET) | merged #15, #27, #31 | leak-free split per `docs/QA.md` (session/pHash/stratification gates PASS) |
| ML: freshness `fresh / semi_fresh / spoiled` | merged #29, #31 | `semi_fresh` shows as **"Use soon"**; gates stay binary |
| ML: pipeline (port of LemurTech22's #21) | merged #26, #29, #31 | #21 closed with credit |
| ML: Colab training | **ready to run** (#33, #31) | DRY_RUN, Drive checkpoint + resume, data gates enforced in the notebook |
| ML: YOLO metrics | **not yet**, because no model has been trained | gate runs on the owner's `export.zip` |
| Design: 10 screens + design system (light + dark) | **approved 2026-10-10** (#37) | canvas https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx |
| iOS | tab shell + adaptive `Theme.swift` (dark mode, #12) | builds and tests pass on Xcode 26.6 / iOS 26.5 simulator |

## Decisions since checkpoint 1 (detail in `docs/DECISIONS.md` and `docs/QA.md`)
- **Native iOS 26 glass tab bar**, with **Add as a tab** that presents the Add sheet.
- **`semi_fresh`** ships as a "Use soon" badge. YOLO gates are spoiled vs not-spoiled, and the semi metrics are informational.
- **Food groups** (protein / veggies / fruit / …) with colourful icons. Recipes show macros. Photo review has quantity steppers.
- `gemini-3.8-flash`, costing $0.75 / $3.75 per 1M tokens until 2026-12-31.
- Full YOLO26s training runs **on Colab**, because it would take about 7.5 h on the M4 Pro (MPS).
- Held-out split rules (ML-21/23 and later): 300 s sessions, a 10-image minimum per session, train ≥ 50%, pooling only complete sessions, a pHash identity gate, and per-source spoiled recall with Wilson CIs.
- AgriFreshNET: its own `aug_` copies are excluded, it's capped at 300 per cell, and it's labelled "cross-stage specimen overlap possible".

## Next steps
1. **Owner: Colab run.** Open `ml/yolo/train_colab.ipynb` in Colab (T4). Add the Secrets `ROBOFLOW_API_KEY` (private key) and `KAGGLE_API_TOKEN`. Do the **DRY_RUN** first and note the RUN_ID, then do the real run with the same RUN_ID. If it disconnects, Run all again and it resumes. Hand `export.zip` to the Mac session.
2. **Mac: the YOLO gate** on `export.zip`: `detection_metrics --manifest`, `check_thresholds`, per-source CIs, and real vs synthetic lighting. Then load the weights in `ml/serve` from `mldata/`, never git, and check from-photo end to end (`source: "yolo"`).
3. **Wave 2: iOS (in progress).** iOS foundation PR, then builder + iOS QA: SwiftUI from `docs/design/screens/` + `DESIGN_SYSTEM.md`, with Simulator screenshots against the artboards, Dynamic Type and dark mode. IOS-3 (system label colours) gets fixed there.
4. **Wave 4, integration QA:** the demo path on the full stack: photo add → expiry → remove → dashboard.
5. **Wave 5, UI review** (Impeccable critique/polish, web-design-guidelines), only once the UI is feature-complete.

## Open questions / blockers
- ~~TestFlight~~: **not used** (no paid account). The demo runs on the owner's iPhone with a free Personal Team.
- ~~Phone to API~~: **Cloudflare quick tunnel** from the Mac (`scripts/demo_tunnel.sh`).
- Jose's answers on #21 (specimens across stages) would refine the AgriFreshNET split. Nothing is blocked on them.

## QA status
- **Backend:** PASS. 523 tests, 96% coverage. Open: BE-7 (info: juice is pantry in the backend, `other` in pipeline output).
- **ML:** data, pipeline, parser and notebook PASS. **YOLO not evaluated yet.** Open: ML-11–14 (low, parser), ML-28 (val lacks potato and apple/spoiled, so Colab uses `last.pt`), ML-32 (hien_fridge single camera), ML-40 (dihedral check reported only).
- **iOS:** first build PASS, dark theme PASS. Screens not built.
- **Integration:** not run yet.

The full log and bug list are in [`docs/QA.md`](docs/QA.md).

## How to run everything
Full detail is in `docs/SETUP.md`. The short version:
```bash
cp .env.example .env                                    # fill in; never commit
python3.12 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
docker compose up -d --build && curl 127.0.0.1:5055/health   # migrations run on start
docker compose exec db psql -U fwr -d fwr -c 'CREATE DATABASE fwr_test'
(cd backend && ../.venv/bin/pytest -q --cov=app)
(cd ios && xcodegen generate && open FoodWasteReducer.xcodeproj)
docker compose logs api | python3 scripts/gemini_cost.py     # Gemini spend
```
