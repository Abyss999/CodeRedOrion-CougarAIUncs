# Handoff

_Last updated: 2026-10-10 (checkpoint 4b). **`food-main` (VPS) is the orchestrator**: it plans, rules,
reviews and merges. `mobile-food` and the first Mac builder session `food-waste` have handed off because
their context was full. **Mac-only work** (Xcode, simulators, the Mac's Docker stack, MPS, the Colab
`export.zip` gate, and pushing `.github/workflows`, which the VPS token can't do) needs **a fresh Mac
builder session**. That session starts from the "In flight on the Mac" table below and reports to
`food-main`. Backend-only PRs can also be built on the VPS. Rules: [`CLAUDE.md`](CLAUDE.md)._

## Current status
**Backend, the ML data pipeline, the full design (22 screens, with a motion spec tested by QA) and
all docs are merged on `main`. Open: #47 (iOS foundation, draft) and #50 (backend PR 1, QA PASS). iOS Wave 2 is underway on the Mac (foundation
first). The Colab training run is ready for the owner.**

| Area | State | Evidence |
|---|---|---|
| Backend on `main`: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | 523 tests, 96% coverage |
| Backend PR 1 `feat/items-wave2`: stored freshness and confidence, share on items, `POST /items/:id/restore`, `DELETE /auth/me` | **#50, QA PASS, ready to merge** | 680 passed / 97%; BE-8 fixed, BE-9 (low: huge `est_price` gives a 500) open, xfail-tracked |
| Backend PR 2 `feat/insights-wave2`: impact split, reasons, previous period, 6-week series; recipe servings + `uses_items` + per-user cache; **`remove-batch` and `restore-batch`** (approved) | queued after PR 1 | (none yet) |
| Backend PR 3 `feat/oauth`: **Google only**, generic `user_identities.provider` | queued after PR 1 | the owner creates the Google OAuth client (the Mac sends the steps) |
| iOS foundation `feat/ios-foundation`: tokens incl. `Theme.Motion`, Outfit, assets and glyphs, APIClient + Live/Mock, Keychain, glass tab bar, a11y IDs, states, Debug base URL, Xcode 26 CI | **draft #47**; final iOS QA re-verify pending | QA: unit 96 / UI 16 pass; IOS-4..10 then fixed by the builder |
| ML data (5 sources), pipeline, freshness `fresh/semi_fresh/spoiled` | merged | leakage and stratification gates PASS |
| ML training | **waiting for the owner's Colab run** | DRY_RUN, then the real run with the same RUN_ID |
| Design | 22 screens approved; canvas is the source | `docs/design/SCREENS.md`, `MOTION.md`, `DESIGN_SYSTEM.md` |
| Demo connectivity | merged | `scripts/demo_tunnel.sh` (Cloudflare quick tunnel, HTTP/2) |

## Next steps
1. **Owner: Colab run.** Open `ml/yolo/train_colab.ipynb` (T4) and add the Secrets `ROBOFLOW_API_KEY` (the private key) and `KAGGLE_API_TOKEN`. Do the **DRY_RUN** first, then the real run with the same RUN_ID. Hand `export.zip` to the Mac.
2. **Mac:** the iOS foundation and backend PR 1 to QA PASS, then review and merge. Then build the screens in this order, one PR each with iOS QA, screenshots, a motion recording and a Design delta:
   1. Fridge + removal (+ Undo)
   2. Add + photo review + text / barcode / receipt
   3. Item detail
   4. Home
   5. Impact
   6. Recipes + detail ("I made this")
   7. Social (pantry, composer, connect, group)
   8. Auth (email + Google)
   9. Settings
3. **Mac:** backend PR 2, then PR 3. **Owner:** the Google OAuth client.
4. **Mac:** the YOLO gate on `export.zip`, then `ml/serve` with the weights, then check from-photo end to end (`source: "yolo"`).
5. **Wave 4, integration QA:** the demo path on the full stack, then on the phone through the tunnel.
6. **Wave 5, UI review** (Impeccable critique and polish, web-design-guidelines) once the UI is feature-complete. Then iOS QA re-runs everything.

## In flight on the Mac (pick up here)
| Item | Branch / PR | Worktree | Next action |
|---|---|---|---|
| Backend PR 1 | `feat/items-wave2`, **#50** | `wt/items-wave2` | QA PASS recorded in `docs/qa/backend.md`. Check CI, merge, fold into `docs/QA.md`. Its compose stack (`items-wave2-*`, 5055/5433) is still up and holds `fwr_test`; reuse it or `docker compose down` there (keep the volume) |
| iOS foundation | `feat/ios-foundation`, **draft #47** | `wt/ios-foundation` | Spawn iOS QA to re-verify: update `MotionTests` to cap 6 (it asserts 8); skeleton tests now see one `<screen>.loading`; the debug error is a `Label`; re-run on iPhone 17 Pro and the **"iPhone SE QA"** simulator (UDID FFA5D7A9-…, AX5); toast and Reduce Motion UI tests via `-UITestShowToast` / `-UITestReduceMotion`; record a <2 MB motion clip; confirm IOS-4..10. Then un-draft, check CI on macos-26, merge |
| Backend PR 2 `feat/insights-wave2` | not started | - | After #50: `/impact` used/donated split, waste-reason breakdown, previous period, gap-filled **last 6 weeks**; recipes `servings` + `uses_items:[{item_id,name,predicted_expiry}]`; per-user suggestion cache (active-items hash, 6 h TTL, log hits); `POST /items/remove-batch {item_ids, outcome: used/donated}` and `POST /items/restore-batch` (atomic; impact exact after the pair); add both to `APIClient` + Mock |
| Backend PR 3 `feat/oauth` | not started | - | After #50: **Google only**. `POST /auth/oauth/google {id_token}` (JWKS, aud from `GOOGLE_IOS_CLIENT_IDS`, iss, exp, `email_verified`); generic `user_identities(provider, subject, user_id, email)`; nullable `password_hash`; link by verified email; `DELETE /auth/me` removes identities; tests stub JWKS with local RSA keys. Give the owner the Google OAuth iOS-client steps (bundle id from `Local.xcconfig`, reversed-client-id URL scheme) |
| Fridge + removal screen | not started | - | After #47 and #50: the first screen per `SCREENS.md` plus its `MOTION.md` row, with an iOS builder + iOS-frontend QA, Design delta, light/dark screenshots and a clip |

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
**Your job:** plan, rule, review and merge, and own the canvas and the orchestrator docs. Builds happen in builder sessions (a fresh Mac session for iOS and anything Mac-only), each running builder + QA sub-agent pairs.

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
  - the Colab run
  - the Google OAuth client
  - nothing else blocking
- **Watch for:**
  - BE-9.
  - IOS-2/3: glass tab bar inactive colours accepted as system.
  - The Impact screen scrolls (its waste-reasons section is below the fold).
  - Jose's (LemurTech22) optional answers on closed #21.

## QA status
- **Backend:** PASS on `main` (523 tests, 96%). PR 1 in QA. Open: BE-7 (info), BE-9 (low).
- **ML:** data, pipeline, parser and notebook PASS. YOLO not evaluated yet. Open: ML-11–14, ML-28, ML-32, ML-40.
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
