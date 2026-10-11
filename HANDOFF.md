# Handoff

_The app is **BiteDown** (owner, 2026-10-10; see `docs/DECISIONS.md`). Internal names such as `FoodWasteReducer` stay._

_Last updated: 2026-10-11 (checkpoint 7). **`food-main` (VPS) orchestrates**: it plans, rules, reviews and merges,
and owns the canvas and the orchestrator docs. **`food-main-mac` (the Mac) does all the building**: builder + QA
sub-agents (Sonnet, owner preference), Xcode and simulators, Docker and every test run, plus any
`.github/workflows` push. The owner has also let the Mac merge a PR directly when it judges it ready (#62, #66).
Both update this file and the affected `docs/` at every checkpoint (`CLAUDE.md` Rules). Rules: [`CLAUDE.md`](CLAUDE.md)._

## Current status
**On `main`:** backend (all three backend PRs plus requests and tips), the iOS foundation, receipts, the 8-source
ML dataset, the design (22 screens, the feedback round and dark-mode artboards) and the docs. **Open:** #64
(Fridge + removal), finishing final iOS QA. Photo add still uses the Gemini fallback until the teammate's
model lands.

| Area | State | Evidence |
|---|---|---|
| Backend: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | full suite 1533 passed / 98% (#66) |
| Items wave 2: stored freshness, share on items, restore, `DELETE /auth/me` | merged (#50) | BE-8 fixed |
| Insights wave 2: impact split, reasons, previous period, 6-week series; recipe `servings` + `uses_items` + cache; `remove-batch` / `restore-batch` | merged (#57) | BE-9, BE-10, BE-13 fixed |
| Google sign-in, `user_identities` (migration 0005) | merged (#60) | 1411 passed / 98%; BE-15, BE-16 fixed |
| gunicorn `gthread` (1 worker, 4 threads, `GUNICORN_THREADS`) | merged (#63) | real-gunicorn concurrency test; the Mac compose api runs it |
| Multi-audience requests (migration 0006), tips as one-line observations (30 days), `hd` must equal the email domain | merged (#66) | 1533 passed / 98% |
| Receipts → full candidates, Gemini guide + retry (Jose) | merged (#54) | BE-11–14 fixed (total/coupon tail rule) |
| iOS foundation: tokens, Outfit, APIClient Live/Mock, Keychain, glass tab bar, states, motion, Undo toast, BiteDown display name | merged (#47) | 17 Pro + SE AX5 PASS; IOS-4..11 fixed |
| **Fridge + removal (+ Undo)** | **#64 open**, head 63619fa, CI running | final iOS QA PASS on the review-fix head: 17 Pro + SE AX5, unit 146 / UI 51; IOS-12 fixed, IOS-13 open (low) |
| ML data: 8 sources (VegQual, fridge_objects, hien_fridge, Kaggle fresh/stale, AgriFreshNET, MeatScan, DaFiF, Food Spoilage Status) | merged (#62) | independent QA PASS on the full build: leakage ML-21 PASS, stratification PASS, parent_sibling 0 |
| ML training, YOLO gate, `ml/serve` weights, GLM-OCR | **teammate LemurTech22's track**; Colab can run now | don't schedule agents for it unless the owner asks |
| Design | 22 screens plus dark artboards; canvas is the source | `docs/design/` |
| Demo connectivity | merged | `scripts/demo_tunnel.sh` |

## Next steps
1. **#64 Fridge + removal:** QA PASS and pushed (63619fa). Waiting on CI, then merge.
2. **Fridge polish** (`feat/ios-fridge-polish`), from the 2026-10-11 feedback:
   - one status per row; the meta line shows quantity only; spoiled reads "Looks off"
   - estimated expiry ranges (2–3 days … 3+ weeks)
   - RemoveSheet: "Used it" / "Shared it" or "Gave it to <first name>" / "Threw it away"; no captions; a listing badge on the icon
   - RemoveReason: titles only
   - deferred #64 review items:
     - a refresh during restore re-inserts the row
     - per-item ops are serialised
     - the Remove a11y action container (with IOS-13)
     - prune the tracking sets
     - `expiryPhrase` keyed on the badge enum
3. **Then the screens, one PR each** (iOS QA, light/dark screenshots against the light and dark artboards, a motion clip, a Design delta):
   1. Add + photo review: a "Looks spoiled" section with inline Toss it / Keep it; Toss = create, then remove `thrown_out`/`expired`.
   2. Item detail: tappable rows, "Check again", "What to look for"; IOS-13; photo history deferred.
   3. Home: units follow Settings (lb/oz); a profile toolbar button; a one-line dismissible tip; `Recipe.usesItems` object shape.
   4. Impact.
   5. Recipes + detail ("I made this"), which brings the `remove-batch` / `restore-batch` client methods.
   6. Social (pantry, a RequestComposer checklist for multi-audience requests, connect, group).
   7. Auth (email + Google; big mark, tagline, value titles).
   8. Settings.
4. **Owner:** create the Google OAuth iOS client (steps in `docs/SETUP.md`) and put the client id in `.env` and `ios/Local.xcconfig`.
5. **Teammate (LemurTech22):** run Colab on the 8-source data. Spoiled recall is reported per source with Wilson CIs. VegQual spoiled is N/A on held-out (ML-62), and beef is train-only (ML-52, PL-5).
6. **Wave 4, integration QA:** the demo path on the full stack, then on the phone through the tunnel.
7. **Wave 5, UI review** (Impeccable critique and polish, web-design-guidelines) once the UI is feature-complete. Then iOS QA re-runs everything.

## In flight on the Mac (pick up here)
| Item | Branch / PR | Worktree | Next action |
|---|---|---|---|
| Fridge + removal | `feat/ios-fridge`, **#64** | `wt/ios-fridge` | Pushed at 63619fa with QA PASS. On green CI, merge (ping `food-main`), then remove the worktree |
| Fridge polish | `feat/ios-fridge-polish` (not started) | - | Starts after #64 merges; scope is in Next steps 2 |
| `docs/ML.md` attribution | - | - | Add the MeatScan creators and fix "Adi Ananda" (DaFiF). Jose's path: ported fix or hand it to him (owner's call) |

**Mac notes:**
- **Worktrees** are in `../wt/<name>` next to the main checkout. Remove merged ones with `git worktree remove`, and only the ones this project created.
- **Data stays outside git** in `../mldata/` (`raw/` with all 8 sources, `pipeline_data/staged/`, `full62/` = the 8-source build from #62 and `full62_qa/` = its gate outputs, `fwr_data_a2b/` = the old 5-source build, `.venv-train` with ultralytics 8.4.175 and imagehash). About 17 GB is free. **`fwr_data_a2b` has a real held-out leak** (fridge_objects, two WhatsApp photos 13 s apart, train vs held-out). Don't quote metrics from it; use `full62`. Colab's `export.zip` goes to `mldata/runs/colab_<RUN_ID>/`.
- **Venvs:**
  - `.venv`: backend.
  - `.venv-ml`: light ML and eval tests.
  - The pipeline CI replay needs a scratch venv with `-r pipeline/requirements.txt flask` (plus `unrar-cffi==0.2.2` for `fetch-meatscan`).
- **Heavy runs** (xcodebuild, full backend suites, Docker builds, dataset builds) take a shared lock: `mkdir <scratchpad>/heavy.lock`, write the owner name, `rm -r` it right after. The owner let the #62 data QA run outside it.
- **Compose:** the running stack is project `items-wave2` (api 5055, db 5433 with `fwr_test`). Rebuild the api only, keeping the db volume: `docker compose -p items-wave2 up -d --build --no-deps api`.
- **Roboflow** downloads need the private key `ROBOFLOW_API_KEY_SECRET_KEY` in `.env`; the publishable `ROBOFLOW_API_KEY` is rejected.
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
  - The 2026-10-11 feedback round (DESIGN_SYSTEM Principles; DECISIONS 2026-10-11): one status per item, expiry ranges, no helper captions, units follow Settings, inline choices over chained alerts. Toss in photo review counts as waste.
  - Google linking: gmail/googlemail, or `hd` equal to the email domain; otherwise 409 `account_exists_use_password`. One Google identity per user (409 `identity_conflict`). A `created` flag goes in the body.
  - Requests: multi-audience with union visibility; the legacy `group_id` is deprecated for one release; leaving a group drops only that audience. Tips: one-line observations over 30 days.
  - Fridge: a claimed listing goes to the claimer (no "Someone else"); the row collapses at the tap; a failed remove plays `.error`.
  - #62 data: keep the new sources with named risks (ML-51/52/55, ML-62). PL-5 won't fix (beef train-only). In `stratification_check`, cross-split pHash pairs are a warning (leakage_check's ≤ 1% is the gate).
  - A teammate's branch takes `main` merged in, never a rebase or force-push.
- **Open owner items:**
  - the Google OAuth client
  - `docs/ML.md` attribution fix: ported, or Jose does it
  - nothing else blocking
- **Watch for:**
  - Home must switch `Recipe.usesItems` to the object shape (#57).
  - The batch client methods (`remove-batch` / `restore-batch`) go in with Recipes "I made this".
  - IOS-13 (low): the food-group icon's asset name is visible to XCUITest. It needs a real-VoiceOver device check in the Item detail PR.
  - IOS-2/3: glass tab bar inactive colours accepted as system.
  - The Impact screen scrolls (its waste-reasons section is below the fold).
  - Jose's (LemurTech22) optional answers on closed #21.

## QA status
- **Backend:** PASS on `main` after #66 (1533 passed, 98%). BE-8 through BE-16 fixed. Open: BE-7 (info).
- **ML / pipeline:** the 8-source dataset is an independent PASS (#62). ML-57/59/60/61 and PL-8 are fixed. PL-5 is won't-fix. ML-51/52/55/62 are named risks. YOLO is not evaluated yet (the teammate's Colab run). Open: ML-11–14, ML-28, ML-32, ML-40.
- **Design / motion:** motion demos PASS (two rounds).
- **iOS:** the foundation is PASS (#47; IOS-4..11 fixed). Fridge (#64): final PASS on the review-fix head (unit 146 / UI 51 on both devices); IOS-12 is fixed; IOS-13 is open (low).
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
