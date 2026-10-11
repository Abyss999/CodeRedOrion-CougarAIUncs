# Handoff

_The app is **BiteDown** (owner, 2026-10-10; see `docs/DECISIONS.md`). Internal names such as `FoodWasteReducer` stay._

_Last updated: 2026-10-10 (checkpoint 6b). **`food-main` (VPS) only orchestrates**: it plans, rules,
reviews and merges, and owns the canvas and the orchestrator docs. **`food-main-mac` (the Mac) does all the
building** (owner decision): builder + QA sub-agents, Xcode and simulators, Docker and every test run,
backend included, plus any `.github/workflows` push (the VPS token can't). It starts from the "In flight on
the Mac" table below and reports to `food-main`. Nothing is built or tested on the VPS. `mobile-food` and
`food-waste` are retired. Rules: [`CLAUDE.md`](CLAUDE.md)._

## Current status
**Backend, the ML data pipeline, the full design (22 screens, with a motion spec tested by QA) and
all docs are merged on `main`. Backend PRs 1 and 2 merged (#50, #57). README/BiteDown merged (#49). #47 (iOS foundation) and #54 (receipt candidates) merged. Backend PR 3 (Google OAuth) merged (#60). gthread merged (#63). The Fridge + removal screen (#64) is fixing CI (Undo-toast UI tests on the slow runner). **Design feedback round and dark-mode artboards are on the canvas** (2026-10-11): see DECISIONS. iOS Wave 2 is underway on the Mac (foundation
first). **ML model work is paused (owner, 2026-10-10): a teammate owns it.** Photo add runs on the Gemini fallback until their model lands.**

| Area | State | Evidence |
|---|---|---|
| Backend on `main`: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | 965 passed / 98% after #57 |
| Backend PR 1 `feat/items-wave2`: stored freshness and confidence, share on items, `POST /items/:id/restore`, `DELETE /auth/me` | **merged (#50)** | 680 passed / 97%; BE-8 fixed |
| Backend PR 2 `feat/insights-wave2`: impact split, reasons, previous period, 6-week series; recipe servings + `uses_items` + per-user cache; **`remove-batch` and `restore-batch`** (approved) | **merged (#57)** | 965 passed / 98%; BE-9, BE-10, BE-13 fixed |
| Backend PR 3 `feat/oauth`: **Google only**, generic `user_identities.provider` | **merged (#60)**; 1411 passed / 98% | the owner creates the Google OAuth client (the Mac sends the steps) |
| iOS foundation `feat/ios-foundation`: tokens incl. `Theme.Motion`, Outfit, assets and glyphs, APIClient + Live/Mock, Keychain, glass tab bar, a11y IDs, states, Debug base URL, Xcode 26 CI | **merged (#47)** | QA: unit 96 / UI 16 pass; IOS-4..10 then fixed by the builder |
| ML data (5 sources), pipeline, freshness `fresh/semi_fresh/spoiled` | merged | leakage and stratification gates PASS |
| ML training, YOLO gate, `ml/serve` weights, GLM-OCR | **teammate LemurTech22 owns the data + model track.** The 8-source dataset passed independent QA (#62), so Colab can run (owner, 2026-10-10). Don't schedule agents for it unless the owner asks | the notebook is ready (DRY_RUN, then the real run with the same RUN_ID) |
| Receipts → full candidates (#54, Jose / LemurTech22) | **merged (#54)**; BE-11–14 fixed | ML check PASS (independent) |
| Design | 22 screens approved; canvas is the source (renamed BiteDown) | `docs/design/SCREENS.md`, `MOTION.md`, `DESIGN_SYSTEM.md` |
| Demo connectivity | merged | `scripts/demo_tunnel.sh` (Cloudflare quick tunnel, HTTP/2) |

## Next steps
1. **ML models: off the queue (owner decision, 2026-10-10).** A teammate is working on them. Don't schedule agents for any of these unless the owner asks:
   - the Colab run and the `export.zip` YOLO gate
   - weights in `ml/serve` and the from-photo `source: "yolo"` check
   - GLM-OCR on MPS
   - further `ml/yolo`, `ml/eval` or pipeline data work

   What's merged stays as it is. The photo flow uses the Gemini fallback.
2. **Mac (`food-main-mac`):** the iOS foundation (#47) re-verify, then merge. Then build the screens in this order, one PR each with iOS QA, screenshots, a motion recording and a Design delta:
   1. Fridge + removal (+ Undo)
   2. Add + photo review + text / barcode / receipt
   3. Item detail
   4. Home
   5. Impact
   6. Recipes + detail ("I made this")
   7. Social (pantry, composer, connect, group)
   8. Auth (email + Google)
   9. Settings
3. **Owner:** the Google OAuth client (steps in `docs/SETUP.md`). gthread is merged (#63). **Owner:** the Google OAuth client.
4. ~~The YOLO gate, `ml/serve` weights and the from-photo `source: "yolo"` check~~ are paused (see 1).
5. **Wave 4, integration QA:** the demo path on the full stack, then on the phone through the tunnel.
6. **Wave 5, UI review** (Impeccable critique and polish, web-design-guidelines) once the UI is feature-complete. Then iOS QA re-runs everything.

## In flight on the Mac (pick up here)
| Item | Branch / PR | Worktree | Next action |
|---|---|---|---|
| Fridge + removal screen | #64, CI fix | `wt/ios-fridge` | Then the Fridge polish PR per the 2026-10-11 feedback: the first screen per `SCREENS.md` plus its `MOTION.md` row, with an iOS builder + iOS-frontend QA, Design delta, light/dark screenshots and a clip |

**Mac notes:**
- **Worktrees** are in `../wt/<name>` next to the main checkout. Remove merged ones with `git worktree remove`, and only the ones this project created.
- **Data stays outside git** in `../mldata/` (`raw/`, `pipeline_data/`, `fwr_data_a2b/`, `.venv-train` with ultralytics 8.4.175 on MPS). About 6–7 GB is free. Colab's `export.zip` goes to `mldata/runs/colab_<RUN_ID>/`.
- **Venvs:**
  - `.venv`: backend.
  - `.venv-ml`: light ML and eval tests.
  - The pipeline CI replay needs a scratch venv with `-r pipeline/requirements.txt flask`.
- **`.env`** holds `ROBOFLOW_API_KEY` (private), `KAGGLE_API_TOKEN` (Bearer), `GEMINI_API_KEY` and `GEMINI_MODEL=gemini-3.8-flash`. Never print them.
- **QA briefs that worked:**
  - iOS-frontend QA: HIG and native components; XCUITest per flow; VoiceOver, AX5, 44 pt, Reduce Motion on and off; light and dark screenshots against the artboards; empty, skeleton and error states; one composite equals one animation; total ≤ 0.5 s.
  - Backend QA: impact before and after for every mutation, query-count N+1 checks, and rollback on forced failure.

## Orchestrator handoff (to `food-main`)
**Your job:** plan, rule, review and merge, and own the canvas and the orchestrator docs. **You never build or run tests.** All building happens in `food-main-mac` (the Mac), which runs builder + QA sub-agent pairs.

- **Reach the builder:** `SendMessage` to `food-main-mac` (over Remote Control). Delivery is unconfirmed, so check `gh pr list` if a report is late. Tell it when a PR merges.
- **Retired sessions:** `food-waste` and `mobile-food` are retired. Everything is in this file, `docs/` and the open PRs. CI workflow edits must be pushed from the Mac session.
- **Merge routine** for each PR:
  1. `gh pr view` to check mergeable, CI and files.
  2. Check that a QA PASS is recorded in `docs/qa/<area>.md`.
  3. Read the diff for anything outside the PR's scope.
  4. `gh pr merge --merge`.
  5. Fold the sign-off into `docs/QA.md` and record any ruling in `docs/QA.md` or `DECISIONS.md`.
  
  Never delete a branch an open PR targets.
- **Canvas:** https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx, an Artifact of the Design type, which you edit with the Artifact tool.
  - Its files are `project/canvas.json` plus `project/<Screen>.dc.html`, mirrored in `docs/design/screens/`.
  - Read the artboard first (Artifact `read` with `path`), edit locally, then publish only the changed files to the same `url`.
  - On iOS PRs with a **Design delta**, update the canvas and `screens/` to match.
  - Owner comments arrive as artifact comment threads: answer and resolve them with `ArtifactComments`.
- **Rulings already made**, so don't re-open them:
  - Google + email only.
  - Free Personal Team, no TestFlight, no capabilities a free team can't sign.
  - iOS 18 minimum.
  - Glass tab bar, with Add as a tab.
  - `semi_fresh` shown as "Use soon", with binary gates.
  - Freshness stored on items.
  - `remove-batch` / `restore-batch`.
  - Settings preferences stored on the device.
  - The Colab `last.pt` rule (ML-28).
  - The data split rules and pHash identity gate in `docs/QA.md`.
  - The motion values in `MOTION.md`.
- **Open owner items:**
  - the Google OAuth client
  - (the Colab run is paused: a teammate owns the models)
  - nothing else blocking
- **Watch for:**
  - The first screen that decodes recipes (Home) must switch `Recipe.usesItems` to the object shape (#57).
  - The batch client methods (`remove-batch` / `restore-batch`) go into the first iOS screen PR that uses them.
  - IOS-2/3: glass tab bar inactive colours accepted as system.
  - The Impact screen scrolls (its waste-reasons section is below the fold).
  - Jose's (LemurTech22) optional answers on closed #21.

## QA status
- **Backend:** PASS on `main` after #57 (965 passed, 98%). Open: BE-7 (info). BE-11, 12 and 14 are fixed on #54, pending merge.
- **ML:** data, pipeline, parser and notebook PASS. YOLO not evaluated (paused: a teammate owns the models). Open: ML-11–14, ML-28, ML-32, ML-40.
- **Design / motion:** motion demos PASS (two rounds).
- **iOS:** first build and dark theme PASS. Foundation in QA.
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
scripts/demo_tunnel.sh                                  # phone demo URL
docker compose logs api | python3 scripts/gemini_cost.py     # Gemini spend
```
