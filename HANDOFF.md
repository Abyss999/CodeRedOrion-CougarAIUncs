# Handoff

_The app is **BiteDown** (owner, 2026-10-10; see `docs/DECISIONS.md`). Internal names such as `FoodWasteReducer` stay._

_Last updated: 2026-10-11 (checkpoint 9). **`food-main` (VPS) orchestrates**: it plans, rules, reviews and merges,
and owns the canvas and the orchestrator docs. **`food-main-mac` (the Mac) does all the building**: builder + QA
sub-agents (**Sonnet**, owner preference), Xcode and simulators, Docker and every test run, plus any
`.github/workflows` push. The owner also lets the Mac merge a PR when it judges it ready, and edit the canvas when
the owner asks. **`food-orch`** (a second Mac session, since checkpoint 8) took over from `food-main-mac`: independent QA on
teammate PRs, canvas rounds when handed the canvas (round 3 is done, and the canvas is back with `food-main`) and this file at
checkpoints. All three update this file and the affected `docs/` at
every checkpoint (`CLAUDE.md` Rules). Rules: [`CLAUDE.md`](CLAUDE.md)._

## Current status
**Building the whole UI into the iOS app** (owner, 2026-10-11): wire it to the live backend and stub only what
isn't done (see the honesty list). The design gate is closed (canvas v51 = #75); the backend gaps the UI needs are
merged (#74, #76). **PR0 "shared foundation" is merged (#81)**, and the Fridge polish is building on it. Canvas round 3 is
merged (v53, #82). Gemini photo enrichment (#79) is merged, and its four QA bugs are re-verified (#84).

| Area | State | Evidence |
|---|---|---|
| Backend: auth, items, removal, events, impact, tips, social, AI endpoints, food groups, macros, Gemini cost logging | merged | full suite 2199 passed / 98% (#79) |
| Items wave 2 (#50), insights wave 2 + batch remove/restore (#57), Google sign-in (#60), gthread (#63), multi-audience requests + tips (#66) | merged | BE-8 … BE-16 fixed |
| **Given to** recipient: `recipient_id` omitted / null / user on remove and remove-batch; self → 400 | merged (#74) | 1642 passed / 98%; BE-17 fixed |
| UI gaps: `GET /requests?mine=1`, owner `share.audience`, `GET /auth/me`, `GET /people/reachable` | merged (#76) | 1708 passed / 98% |
| Receipts → candidates, Gemini guide + retry (Jose) | merged (#54) | BE-11–14 fixed |
| Gemini photo enrichment: `enrich=expiry,nutrition` on from-photo, `items.nutrition` (migration 0007), `item_ids` on `/recipes/suggest` (Truc) | merged (#79) | independent QA PASS WITH OPEN BUGS; BE-19/20/22 verified fixed, BE-21 accepted as documented (#84) |
| iOS foundation (#47), **Fridge + removal + Undo** (#64) and **PR0 shared foundation** (#81) | merged | Fridge: 17 Pro + SE AX5 unit 146 / UI 51; IOS-12 fixed; IOS-13 open (low); two CI flakes fixed in tests. PR0: 17 Pro unit 354 / UI 51, SE AX5 34/34, IOS-14–18 fixed |
| ML data, 8 sources (#62), Colab unrar build fix (#73, Jose) | merged | independent QA PASS on both; ML-64 (low) + ML-65 (info) open for Jose |
| ML training, YOLO gate, `ml/serve` weights, GLM-OCR | **teammate LemurTech22's track**; Colab can run | don't schedule agents for it unless the owner asks |
| Design | 38 screens (22 + the gap audit's 16, incl. FulfilConfirm) + dark artboards; canvas v53 (round 3), mirrored in #82 | `docs/design/`; design QA READY WITH FIXES, fixes applied |

## Next steps
1. **Fridge polish** (`feat/ios-fridge-polish`, from PR0 #81): in progress on the Mac; build notes in "Screen build notes" below.
2. **The parallel group (Add 2a, Home, Impact and Auth have started; see In flight):** Add (2a photo, 2b text/barcode/receipt), Home, Impact, Auth; Recipes after Home. **Then sequential:** Item detail → Social (7a pantry + requests, 7b connect + groups) → Settings. One PR each, with iOS QA, light/dark screenshots against the artboards, a motion clip and a Design delta.
3. **wedwqc's canvas threads** (round 3) are applied but still open on the canvas: they weren't sent to Claude, so a person with edit access must resolve them.
4. **Owner:** create the Google OAuth iOS client (`docs/SETUP.md`).
5. **Teammate (LemurTech22):** Colab on the 8-source data. ML-64 and ML-65 go to Jose via `food-main`.
6. **Wave 4**, integration QA on the full stack and phone; **Wave 5**, the UI review.

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
  - **Photo enrichment (#79), opt-in:**
    - send `enrich=expiry,nutrition` from Photo review, and raise the from-photo timeout above 60 s (worst case is detection + 25 s);
    - treat `enrichment.status: "partial"` as normal, because spoiled and low-confidence items are never sent;
    - `NewItem(candidate:)` must carry `nutrition`.
  - **PhotoReview (round 3):** the amount is a button that opens an inline editor (amount, unit, Done); steppers are 44 pt.
- **Item detail:**
  - **Freshness:** "Check again" PATCHes only `freshness` (+ `confidence`, `freshness_checked_at`); nothing is stored. "What to look for" is static.
  - **ItemShared:** the audience from `share.audience`; Remove → the sheet with Given to = the claimer. IOS-13 VoiceOver device check.
- **Home:**
  - **Layout:** the tip at the TOP (one line, observation only, dismissible); the **settings gear** replaces the profile button (round 3).
  - **Data:** the pill uses `range=month`; `Recipe.usesItems` objects.
  - **States:** HomeEmpty, ServerError (its "Change" → Settings › Debug "Server address").
- **Impact:** artboards are 1126 / 1416 tall. ImpactRange is the canonical layout (week/month/all, "vs previous", used/donated) led by lb saved; round 3 copy ("carbon emissions", waste rate alone with no "vs previous" badge, plus a compare widget, "19 used" / "4 donated" on two lines).
- **Recipes:**
  - **Filters:** "Only what I have" is on by default (client-side `missing_items` empty; request 10); its empty state offers recipes needing a few things.
  - **"I made this":** with Undo, via remove-batch / restore-batch.
  - **RecipeDetail:** a bold "Ingredients" list + serving size in grams (round 3).
  - **"Cook with this" (`item_ids`, #79):** the server doesn't enforce the focus items (BE-21), and the result can have non-empty `missing_items`. So for a focus request, fall back to the "needs a few things" state instead of an empty "Only what I have" list.
- **Social:**
  - **Requests:** Offer → FulfilConfirm → fulfil. "Yours" → MyRequests (`?mine=1`). Notes clamp to 4 lines + "more" (280 kept).
  - **Pantry and audiences:** the Pantry widget links to FoodPantry. RequestComposer is a multi-audience checklist. A green **+** beside "Requests" ("Ask for something") opens RequestComposer; "Post one" is removed. The header button is a person-plus icon ("Add friends or groups") → Connect. Offer is a small pill in a 44 pt hit area.
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
| Fridge polish (IOS-19…29) | `feat/ios-fridge-polish` (from #81) | `wt/ios-fridge-polish` | Builder + QA in progress, with the round 3 RemoveSheet and BatchUndo changes; then PR |
| Add 2a: photo (IOS-30…39) | `feat/ios-add-photo` (from 0329c6d) | `wt/ios-add-photo` | Builder + QA in progress, in parallel; includes the #79 enrichment follow-ups |
| Home (IOS-40…49) | `feat/ios-home` (from 0329c6d) | `wt/ios-home` | Builder + QA in progress, in parallel |
| Impact (IOS-50…59) | `feat/ios-impact` (from 0329c6d) | `wt/ios-impact` | Builder + QA in progress, in parallel |
| Auth (IOS-60…69) | `feat/ios-auth` (from 0329c6d) | `wt/ios-auth` | Builder + QA in progress, in parallel |
| Queued | - | - | Add 2b (text/barcode/receipt) after 2a; Recipes after Home; then Item detail → Social → Settings |
| `docs/checkpoint-9` | this PR | `wt/checkpoint-9` (`food-orch`) | `food-main` reviews and merges |

Each screen PR numbers its iOS bugs inside its own block (above), so parallel branches can't collide.

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
- **Canvas:** edit LIGHT artboards only. An element on a lime card that sets `background: transparent` resets mkdark's lime scope, and its text flips to a light ink. Give it the card's lime explicitly. Generate darks with `python3 docs/design/tools/mkdark.py <lights> <out>` from `main` (it fails on any untagged colour), then the href sed (`href="X.dc.html"` → `href="X.dark.dc.html"`). Read live files before editing, and publish only the changed files.
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
  - iOS recipient rule (#78): send `recipient_id` only on an explicit pick; omit for the claimer default; `null` only for "Someone not on BiteDown"; batch "Shared them" omits it.
  - Round 3 (owner): the Home profile button becomes a settings gear; the tip stays observation-only; Social posts through one green "+" beside Requests, with a person-plus button for Connect (approved, #82); request notes keep 280 chars and the board clamps to 4 lines; chat and a waste-tracking metric are out of scope.
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
- **Backend:** PASS on `main` after #79 (2199 passed, 98%). BE-8 … BE-22 resolved (BE-21 accepted as documented; #84 re-verified BE-19–22). Open: BE-7 (info). Follow-up only if memory gets tight: lower `ENRICH_MAX_PIXELS` to about 25 MP.
- **ML / pipeline:** the 8-source dataset (#62) and #73 are independent PASSes. ML-57/59/60/61/63 and PL-8 fixed; PL-5 won't-fix; ML-51/52/55/62 named risks. Open: ML-11–14, ML-28, ML-32, ML-40, ML-64 (low), ML-65 (info). YOLO not evaluated yet.
- **Design:** the full-canvas UI/UX gate passed with fixes (v51). Round 3 is READY WITH FIXES, with the fixes applied (v53, #82).
- **iOS:** the foundation (#47), Fridge (#64) and PR0 (#81) PASS; IOS-14–18 fixed. IOS-13 open (low).
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
