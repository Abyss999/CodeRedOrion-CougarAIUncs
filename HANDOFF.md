# Handoff

## BiteUp branding and branch sync — 2026-10-10

- Merged `origin/main` into `Truc_branch`, retaining the current checkpoint, agent rules, and
  expanded design canvas from main while applying **BiteUp** branding.
- README tagline: **Use what you have. Share what you spare.** The iOS display name and sign-in
  mockup use BiteUp; internal Xcode target and scheme names remain `FoodWasteReducer`.
- Updated README QA references and signing instructions to match this checkpoint.
- Merge review: conflict-marker and whitespace checks, design JSON parsing, and local README
  link checks. No application tests or builds were run for this branding/documentation merge.

_Last updated: 2026-10-10 (checkpoint 3). The VPS session `mobile-food` orchestrates: it reviews,
merges, rules on disputes, and owns `docs/design/` and the canvas. The Mac session `food-waste`
builds with builder + QA pairs and opens PRs._

## Current status
**The backend, the ML data pipeline and the full design (22 screens) are merged. iOS Wave 2 is
underway, foundation first. The Colab training run is ready for the owner.**

| Area | State | Evidence |
|---|---|---|
| Backend: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | 523 tests, 96% coverage |
| Backend PR 1 `feat/items-wave2`: stored freshness, share on items, restore/undo, delete account | **in QA on the Mac** | 661 tests; BE-8 fixed, BE-9 (low) open |
| Backend PR 2 `feat/insights-wave2`: impact split / reasons / 6-week series, recipe servings + cache | queued after PR 1 | (none yet) |
| Backend PR 3 `feat/oauth`: **Google only** | queued after PR 1 | the owner must create the Google OAuth client (steps to come) |
| Docker stack and CI | runs on the Mac; CI live (backend, ml, ios on macOS 26 / Xcode 26, pipeline) | migrations run on start |
| ML data (5 sources incl. AgriFreshNET), pipeline (port of #21), freshness `fresh / semi_fresh / spoiled` | merged | leakage and stratification gates PASS (`docs/QA.md`) |
| ML training | **ready, waiting for the owner's Colab run** | DRY_RUN, Drive checkpoints and resume, data gates in the notebook |
| YOLO metrics | not yet | the gate runs on `export.zip` |
| Design | **22 screens**; approved, plus the auth and idea-audit additions | `docs/design/SCREENS.md`; canvas https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx |
| iOS foundation: tokens, fonts, assets, APIClient + mock, glass tab bar, a11y IDs, empty/loading/error states | **in QA on the Mac** | runs in the Simulator |
| Demo connectivity | merged (#41) | `scripts/demo_tunnel.sh`, verified live through the tunnel |

## Decisions (detail in `docs/DECISIONS.md`)
- Minimum iOS 18, built with Xcode 26. The demo runs on the owner's iPhone with a free Personal Team. No TestFlight.
- Sign-in is **email + Google**. No Apple sign-in, because it needs a paid team.
- Native glass tab bar; Add is a tab that presents a sheet.
- `semi_fresh` is shown as "Use soon". YOLO gates are spoiled vs not-spoiled.
- Food groups with colourful icons. Recipes show macros, and "I made this" marks the ingredients used.
- Full YOLO training runs on Colab. The model is `gemini-3.8-flash`.
- The data split rules (sessions, the pHash gate, stratification, per-source CIs) are in `docs/QA.md`.

## Next steps
1. **Owner: Colab run.** Open `ml/yolo/train_colab.ipynb` (T4) and add the Secrets `ROBOFLOW_API_KEY` (the private key) and `KAGGLE_API_TOKEN`. Do the **DRY_RUN** first, then the real run with the same RUN_ID. If it disconnects, Run all again and it resumes. Hand `export.zip` to the Mac.
2. **Mac:** merge-ready iOS foundation and backend PR 1. Then build the screens in this order, one PR per screen with iOS QA, screenshots and a Design delta:
   1. Fridge + removal
   2. Add + photo review (plus text, barcode and receipt)
   3. Item detail
   4. Home
   5. Impact
   6. Recipes + detail
   7. Social (pantry, composer, connect, group)
   8. Auth
   9. Settings
3. **Mac:** backend PR 2 (insights) and PR 3 (Google OAuth). The **owner** creates the Google OAuth client when the steps arrive.
4. **Mac:** the YOLO gate on `export.zip`, then load the weights in `ml/serve`, then check from-photo end to end.
5. **Wave 4, integration QA:** the demo path on the full stack, then on the phone through the tunnel.
6. **Wave 5, UI review** once the UI is feature-complete.

## Open questions / blockers
- The Colab run (owner).
- The Google OAuth client (owner, once PR 3 is underway).
- Jose's answers on #21 would refine the AgriFreshNET split. Nothing is blocked on them.

## QA status
- **Backend:** PASS on main (523 tests, 96%). PR 1 is in QA. Open: BE-7 (info), BE-9 (low).
- **ML:** data, pipeline, parser and notebook PASS. YOLO not evaluated yet. Open: ML-11–14, ML-28, ML-32, ML-40 (`docs/QA.md`).
- **iOS:** first build and dark theme PASS. The foundation is in QA; screens aren't built yet.
- **Integration:** not run yet.

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
