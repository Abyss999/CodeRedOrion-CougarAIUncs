# Handoff

_The app is **BiteDown** (owner, 2026-10-10; see `docs/DECISIONS.md`). Internal names such as `FoodWasteReducer` stay._

_Last updated: 2026-10-11 (checkpoint 8). **`food-main` (VPS) orchestrates**: it plans, rules, reviews and merges,
and owns the canvas and the orchestrator docs. **`food-main-mac` (the Mac) does all the building**: builder + QA
sub-agents (**Sonnet**, owner preference), Xcode and simulators, Docker and every test run, plus any
`.github/workflows` push. The owner also lets the Mac merge a PR when it judges it ready, and edit the canvas when
the owner asks (round 3 of wedwqc's comments is the Mac's). Both update this file and the affected `docs/` at
every checkpoint (`CLAUDE.md` Rules). Rules: [`CLAUDE.md`](CLAUDE.md)._

## Current status
**Building the whole UI into the iOS app** (owner, 2026-10-11): wire it to the live backend and stub only what
isn't done (see the honesty list). The design gate is closed (canvas v51 = #75); the backend gaps the UI needs are
merged (#74, #76). **PR0 "shared foundation"** is in its bug-fix round; the screen PRs build on it.

| Area | State | Evidence |
|---|---|---|
| Backend: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | full suite 1708 passed / 98% (#76) |
| Items wave 2 (#50), insights wave 2 + batch remove/restore (#57), Google sign-in (#60), gthread (#63), multi-audience requests + tips (#66) | merged | BE-8 … BE-16 fixed |
| **Given to** recipient: `recipient_id` omitted / null / user on remove and remove-batch; self → 400 | merged (#74) | 1642 passed / 98%; BE-17 fixed |
| UI gaps: `GET /requests?mine=1`, owner `share.audience`, `GET /auth/me`, `GET /people/reachable` | merged (#76) | 1708 passed / 98% |
| Receipts → candidates, Gemini guide + retry (Jose) | merged (#54) | BE-11–14 fixed |
| iOS foundation (#47) and **Fridge + removal + Undo** (#64) | merged | Fridge: 17 Pro + SE AX5 unit 146 / UI 51; IOS-12 fixed; IOS-13 open (low); two CI flakes fixed in tests |
| ML data, 8 sources (#62), Colab unrar build fix (#73, Jose) | merged | independent QA PASS on both; ML-64 (low) + ML-65 (info) open for Jose |
| ML training, YOLO gate, `ml/serve` weights, GLM-OCR | **teammate LemurTech22's track**; Colab can run | don't schedule agents for it unless the owner asks |
| Design | 38 screens (22 + the gap audit's 16, incl. FulfilConfirm) + dark artboards; canvas v51, mirrored in #75 | `docs/design/` |
| Open PR not from the Mac | **#79** "Gemini photo enrichment" (FrankinstyLe, backend only) | needs independent backend QA before merge |

## Next steps
1. **PR0 `feat/ios-shared`** (branched from #64's head; merge `main` in before pushing):
   - **Done:** every client method, models, Mock, fixtures, `BannerView`, `WeightFormatter`, `FormField`, `PermissionCard`, `AudienceChecklist`, flags, per-tab entry views, GoogleSignIn 9.2.0 (hidden until the client id exists), `onForestChip`.
   - **QA:** PASS WITH OPEN BUGS: IOS-14 (medium; `item.share.audience` not decoded) and IOS-15…18 (low). A builder is fixing them; re-run, then commit, merge main, push and open the PR.
2. **Fridge polish** (`feat/ios-fridge-polish`, branched from PR0), build notes in "Screen build notes" below.
3. **The parallel group once PR0 lands:** Add (2a photo, 2b text/barcode/receipt), Home, Impact, Auth; Recipes after Home. **Then sequential:** Item detail → Social (7a pantry + requests, 7b connect + groups) → Settings. One PR each, with iOS QA, light/dark screenshots against the artboards, a motion clip and a Design delta.
4. **Canvas round 3** (wedwqc 08:28–08:46): being applied on the Mac (lights only, darks via `mkdark.py`), then a design QA against wedwqc's text and a mirror PR with SCREENS / DESIGN_SYSTEM / DECISIONS.
5. **#79** (FrankinstyLe): independent backend QA before merge.
6. **Owner:** create the Google OAuth iOS client (`docs/SETUP.md`).
7. **Teammate (LemurTech22):** Colab on the 8-source data. ML-64 and ML-65 go to Jose via `food-main`.
8. **Wave 4**, integration QA on the full stack and phone; **Wave 5**, the UI review.

## Screen build notes (carry into each brief)
- **All screens:**
  - **A11y:** 44 pt via `contentShape` (steppers, chips, checkboxes, text links); native `Picker(.segmented)`; badges never wrap.
  - **AX5 layouts:** PhotoReview rows stack, Social notes 1 column, Pantry widget + MacroStrip 2×2, Home pill below the greeting, FridgeSelect bar buttons stack.
  - **Units:** `WeightFormatter` (kg → lb/oz per Settings; the API stays metric).
- **Recipient rule (#78):** send `recipient_id` only on an explicit pick. The claimer default omits the key (`.default`). "Someone not on BiteDown" sends `null` (`.none`). Batch "Shared them" always omits it.
- **Fridge polish:**
  - **Rows and badges:** one status per row, quantity-only meta, the badge "Check" → "Looks off", estimated expiry ranges (2–3 days … 3+ weeks).
  - **RemoveSheet:** "Used it" / **"Shared it"** (relabel RemoveOutcomeTile.swift:7, RemoveSheet.swift:110) + the **Given to** menu from `GET /people/reachable` (claimer first, "Someone not on BiteDown") / "Threw it away"; no captions.
  - **RemoveReason:** a grouped list "Why was it thrown out?".
  - **Fridge:** the swipe action is a forest take-out icon. The header "Select" → FridgeSelect / BatchUndo (rows 33–34). The search button is removed (round 3).
  - **Toast:** keyed by item id, not name. The ProgressView track is a Theme token.
  - **Deferred #64 items:** refresh-during-restore re-insert, per-item op serialisation, the Remove a11y container + IOS-13, prune tracking sets, `expiryPhrase` on the enum.
- **Add:**
  - **Rows:** one `DetectedItemRow` shared by PhotoReview, AddText and ReceiptReview.
  - **Gemini fallback:** no `bbox` → hide the box overlay; "Not sure" only when `confidence` is present.
  - **States:** PhotoAnalyzing, PhotoReviewError, CameraDenied. Toss = create + remove (on failure the item stays "Looks off" with a banner).
  - **Receipt tile:** shows unavailable while OCR isn't live.
  - **Sheet:** a shorter hero, "Boxes, cans, jars".
- **Item detail:**
  - **Freshness:** "Check again" PATCHes only `freshness` (+ `confidence`, `freshness_checked_at`); nothing is stored. "What to look for" is static.
  - **ItemShared:** the audience from `share.audience`; Remove → the sheet with Given to = the claimer. IOS-13 VoiceOver device check.
- **Home:**
  - **Layout:** the tip at the TOP (one line, observation only, dismissible); the **settings gear** replaces the profile button (round 3).
  - **Data:** the pill uses `range=month`; `Recipe.usesItems` objects.
  - **States:** HomeEmpty, ServerError (its "Change" → Settings › Debug "Server address").
- **Impact:** ImpactRange is the canonical layout (week/month/all, "vs previous", used/donated) led by lb saved; round 3 copy ("carbon emissions", waste rate alone + a compare widget, "19 used" / "4 donated" on two lines).
- **Recipes:**
  - **Filters:** "Only what I have" is on by default (client-side `missing_items` empty; request 10); its empty state offers recipes needing a few things.
  - **"I made this":** with Undo, via remove-batch / restore-batch.
  - **RecipeDetail:** a bold "Ingredients" list + serving size in grams (round 3).
- **Social:**
  - **Requests:** Offer → FulfilConfirm → fulfil. "Yours" → MyRequests (`?mine=1`). Notes clamp to 4 lines + "more" (280 kept).
  - **Pantry and audiences:** the Pantry widget links to FoodPantry. RequestComposer is a multi-audience checklist. The header "+" only ("Post one" removed).
  - **Connect (round 3):** requests on top → Friends + Add friend → Groups → Create / Join a group (expands to the code).
  - **GroupDetail:** more room, invite code lower.
- **Auth:** Launch / SessionExpired / GoogleSignInError. Google is below the email form (round 3) and hidden by a flag until the client id exists (the SDK dark button in dark mode). A global 401 → SessionExpired; the Launch check uses `GET /auth/me`.
- **Settings:** units, default storage, currency (on device); Debug "Server address"; Delete account.

## Honesty list (what the demo fakes; say so in the demo script)
- **Photo detection:** the Gemini fallback (`source: "gemini"`) until the teammate's YOLO lands. "Check again" works the same way.
- **Receipt OCR:** no OCR service, so live returns 502. The demo uses Mock, or shows the receipt tile as unavailable.
- **Barcode:**
  - **Scanner:** `DataScannerViewController` doesn't run on the Simulator, so the Simulator uses a DEBUG manual-code field.
  - **Lookup:** Open Food Facts is real.
- **Google sign-in:** hidden until the owner's OAuth client id exists.
- **Gemini-generated:** recipes, tips' wording and macros are labelled estimates.
- **Static content:** spoilage signs ("What to look for").
- **Client-side:** lb/oz conversion. Units, default storage and currency are on-device only.
- **`-UITestMockAPI` / `-UITestSeed` runs** show Mock data (friends, groups, requests).

## In flight on the Mac (pick up here)
| Item | Branch / PR | Worktree | Next action |
|---|---|---|---|
| PR0 shared foundation | `feat/ios-shared` (from #64's head) | `wt/ios-shared` | A builder is fixing IOS-14…18. Then QA re-run on the 17 Pro, commit, merge `main`, push, open the PR |
| Fridge polish | `feat/ios-fridge-polish` (not started) | - | Branch from PR0 once it's committed; notes above |
| Canvas round 3 | canvas only (then a `design/` mirror PR) | scratchpad `canvas3/` | A design agent is editing lights; then `mkdark.py` (main), a design QA vs wedwqc's text, publish, mirror PR |
| `docs/checkpoint-8` | this PR | `wt/checkpoint-8` | `food-main` reviews and merges |

**Mac notes:**
- **Worktrees** are in `../wt/<name>` next to the main checkout. Remove merged ones with `git worktree remove`, and only the ones this project created. The owner kept `api-migrate`, `fg-followups`, `food-group`, `colab`, `semi-data` and `pr21`: their ignored files (`.env` variants, YOLO runs) exist nowhere else.
- **Data stays outside git** in `../mldata/`:
  - `raw/`: all 8 sources.
  - `pipeline_data/staged/`.
  - `full62/`: the 8-source build. `full62_qa/`: its gate outputs.
  - `fwr_data_a2b/`: the old 5-source build. **It has a real held-out leak, so never quote metrics from it.**
  - `.venv-train`: ultralytics 8.4.175 + imagehash.
  - About 17 GB is free.
- **Venvs:**
  - `.venv` for the backend.
  - `.venv-ml` for light ML/eval tests (no imagehash or unrar).
  - The pipeline replay runs in a scratch venv with `-r pipeline/requirements.txt flask unrar-cffi==0.2.2`.
- **Heavy runs** (xcodebuild, full backend suites, Docker builds, dataset builds) take the shared lock `<scratchpad>/heavy.lock`: write the owner's name and `rm -r` it after. Targeted single-file pytest is fine alongside xcodebuild, but never two runs on `fwr_test` at once.
- **UI tests:** uninstall the stale runner `com.coderedorion.FoodWasteReducerUITests.xctrunner` before `test-without-building`. Time-based UI assertions need generous windows (the CI runner takes 1–1.5 s per query): use `-UITestUndoWindow`.
- **Compose:** project `items-wave2` (api 5055, db 5433 with `fwr_test`). Rebuild only the api: `docker compose -p items-wave2 up -d --build --no-deps api`.
- **Canvas:** edit LIGHT artboards only. Generate darks with `python3 docs/design/tools/mkdark.py <lights> <out>` from `main` (it fails on any untagged colour), then the href sed (`href="X.dc.html"` → `href="X.dark.dc.html"`). Read live files before editing, and publish only the changed files.
- **`.env`:** `ROBOFLOW_API_KEY_SECRET_KEY` (private; the publishable key is rejected), `KAGGLE_API_TOKEN`, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.8-flash`, `GOOGLE_IOS_CLIENT_IDS` (empty until the owner's client exists). Never print them.
- **QA briefs that worked:**
  - **iOS-frontend QA:** HIG and native components; XCUITest per flow; VoiceOver, AX5, 44 pt, Reduce Motion on and off; light and dark screenshots against the artboards; empty, skeleton and error states.
  - **Backend QA:** impact before and after every mutation, N+1 query-count checks, and rollback on forced failure.
  - **Teammate PRs** get an independent QA whose verdict supersedes self-sign-offs.

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
  - Fridge: "Shared it" picks the recipient in a Given-to menu (defaults to the claimer, else "Someone not on BiteDown"; DECISIONS 2026-10-11 round 2); the row collapses at the tap; a failed remove plays `.error`.
  - Design QA gate (2026-10-11): READY WITH FIXES, fixes applied in `design/qa-gate-fixes`. `mkdark.py` now fails on any unmapped light token. iOS notes: add `onForestChip` to Theme.swift; one `DetectedItemRow` for all add-review lists; MyRequests "Done" waits on `GET /requests?mine=1` (G1); receipt review stays mocked until OCR lands; the photo overlay draws only when `bbox` is present.
  - #62 data: keep the new sources with named risks (ML-51/52/55, ML-62). PL-5 won't fix (beef train-only). In `stratification_check`, cross-split pHash pairs are a warning (leakage_check's ≤ 1% is the gate).
  - A teammate's branch takes `main` merged in, never a rebase or force-push.
- **Open owner items:**
  - the Google OAuth client
  - nothing else blocking
- **Watch for:**
  - Home must switch `Recipe.usesItems` to the object shape (#57).
  - The batch client methods (`remove-batch` / `restore-batch`) go in with Recipes "I made this".
  - IOS-13 (low): the food-group icon's asset name is visible to XCUITest. It needs a real-VoiceOver device check in the Item detail PR.
  - IOS-2/3: glass tab bar inactive colours accepted as system.
  - The Impact screen scrolls (its waste-reasons section is below the fold).
  - Jose's (LemurTech22) optional answers on closed #21.

## QA status
- **Backend:** PASS on `main` after #76 (1708 passed, 98%). BE-8 … BE-17 fixed. Open: BE-7 (info).
- **ML / pipeline:** the 8-source dataset (#62) and #73 are independent PASSes. ML-57/59/60/61/63 and PL-8 fixed; PL-5 won't-fix; ML-51/52/55/62 named risks. Open: ML-11–14, ML-28, ML-32, ML-40, ML-64 (low), ML-65 (info). YOLO not evaluated yet.
- **Design:** the full-canvas UI/UX gate passed with fixes (v51). Round 3 is in progress.
- **iOS:** the foundation (#47) and Fridge (#64) PASS. PR0 is PASS WITH OPEN BUGS (IOS-14 medium, IOS-15…18 low; being fixed). IOS-13 open (low).
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
