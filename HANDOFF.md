# Handoff

_Last updated: 2026-10-10 (checkpoint 4). **The orchestrator role moves to the `food-main`
session** (see "Orchestrator handoff" below). The Mac session `food-waste` builds with builder +
QA pairs and opens PRs. Rules: [`CLAUDE.md`](CLAUDE.md)._

## Current status
**Backend, the ML data pipeline, the full design (22 screens, with a motion spec tested by QA) and
all docs are merged on `main`. No PRs are open. iOS Wave 2 is underway on the Mac (foundation
first). The Colab training run is ready for the owner.**

| Area | State | Evidence |
|---|---|---|
| Backend on `main`: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | 523 tests, 96% coverage |
| Backend PR 1 `feat/items-wave2`: stored freshness and confidence, share on items, `POST /items/:id/restore`, `DELETE /auth/me` | **in QA on the Mac** | 661 tests; BE-8 fixed, BE-9 (low: huge `est_price` gives a 500) open |
| Backend PR 2 `feat/insights-wave2`: impact split, reasons, previous period, 6-week series; recipe servings + `uses_items` + per-user cache; **`remove-batch` and `restore-batch`** (approved) | queued after PR 1 | (none yet) |
| Backend PR 3 `feat/oauth`: **Google only**, generic `user_identities.provider` | queued after PR 1 | the owner creates the Google OAuth client (the Mac sends the steps) |
| iOS foundation `feat/ios-foundation`: tokens incl. `Theme.Motion`, Outfit, assets and glyphs, APIClient + Live/Mock, Keychain, glass tab bar, a11y IDs, states, Debug base URL, Xcode 26 CI | **in QA on the Mac** | runs in the Simulator |
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

## Orchestrator handoff (to `food-main`)
**Your job:** plan, rule, review, merge, and own the canvas and orchestrator docs. **You never build.**

- **Reach the builder:** `SendMessage` to `food-waste` (the Mac, over Remote Control). It reports back by message.
  - Delivery is "not confirmed read", so if a report is overdue, check GitHub (`gh pr list`) before assuming it's lost.
  - The owner can also talk to `food-waste` directly. Relay their decisions both ways.
- **Merge routine** for each PR:
  1. `gh pr view` to check mergeable, CI and files.
  2. Check that a QA PASS is recorded in `docs/qa/<area>.md`.
  3. Read the diff for anything outside the PR's scope.
  4. `gh pr merge --merge`.
  5. Fold the sign-off into `docs/QA.md` and record any ruling in `docs/QA.md` or `DECISIONS.md`.
  6. Tell `food-waste` it merged.
  
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
