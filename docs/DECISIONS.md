# Decisions

Newest first. Each entry: date, decision, why, alternatives considered.

## 2026-10-11 — Design feedback round 2 (teammate wedwqc, 13 comments; QA-checked; owner calls)
- **Owner: the recipient is chosen in a "Given to" menu** after "Shared it". It defaults to the claimer, otherwise to "Someone not on BiteDown". The options are the claimer, friends, fellow group members and **Someone not on BiteDown**. Food given to a non-app person logs as donated (saved), never as waste or to the wrong friend. This replaces the 2026-10-10/11 "always the claimer" rulings. API: `recipient_id` explicit `null` = someone not on BiteDown; a user id must be an accepted friend or fellow group member (else 404); yourself → 400. Queued as `feat/donation-recipient`.
- **Owner: the Home tip card sits at the top**, above "Use these first". It stays one line and dismissible. This reverses the earlier keep-below ruling.
- **Recipes open on "Only what I have"** (no missing items), switchable off.
- **Impact leads with food saved in lb**, and CO₂e becomes a secondary line with a driving equivalent. Month means "previous 30 days".
- **"I have it" becomes "Offer" plus a confirmation sheet.** Fulfilling closes the request for everyone and can't be undone. No in-app messaging is promised.
- **Kept against the comments, with reasons:** the Fridge swipe action stays forest, not red, with a take-out icon instead of the checkmark, because removal records an outcome and isn't a delete. The Add-sheet hero stays full width but shorter, to keep the shared 20 pt margins.
- Also: the reason picker becomes a list ("Why was it thrown out?"); the Pantry widget shows food tiles with no counts; Photo review loses its captions and gets a taller photo; the barcode hint is "Boxes, cans, jars"; the Remove sheet meta is capitalised, with a badge.

## 2026-10-11 — gunicorn gthread (#63)
- **The API container runs one `gthread` worker with 4 threads** (`GUNICORN_THREADS`, default 4; `--timeout 120`, `--graceful-timeout 30`). A slow Gemini call no longer blocks other requests, and the in-process recipe cache stays shared (lock-guarded). *Why not several processes:* the cache is per process and there is no Redis. This closes the follow-up noted under "Backend wave 2 rulings".

## 2026-10-11 — Multi-audience requests and tips (#66)
- **A request targets `audiences {friends, group_ids}`** (at least one, ≤ 50 groups) through the `request_audiences` join table. One note shows on every chosen board. `requests.group_id` is dropped after the backfill in migration 0006. The legacy `group_id` body field is accepted for one release (deprecated, keeping its old 403); sending both → 400; an audiences group you're not in → 404.
- **You only see the audiences you belong to.** The others are counted (`hidden_count`), never named, so group names can't leak.
- **Leaving a group removes that audience only.** A request whose only audience was that group is cancelled.
- **Tips cover a rolling 30 days** (matching "this month" and `/impact?range=month`). Each is one factual line of at most 100 characters, with no advice. A UX note for the Home screen: long item names trimmed in tips can look identical, so the tip text should name items in full.

## 2026-10-11 — New training sources and data rulings (#62; data owner LemurTech22, owner rulings)
- **Three sources added, all CC BY 4.0:** MeatScan (Zenodo 16764338, cow meat), DaFiF (Mendeley vx4ptwk3pb, fish) and Food Spoilage Status (Roboflow v1, produce). food_hvk7g stays `pending` (no downloadable version, no freshness labels). Attribution is in `docs/ML.md` and the README.
- **DaFiF freshness labels come from days on ice:** 1–3 fresh, 9–11 spoiled, 4–8 dropped. The paper's per-species cut-offs are paywalled. This is a data-owner ruling.
- **The new sources are kept, with their risks named** (data owner; ML QA had suggested capping beef):
  - beef is train-only, and its spoiled class is scene-confounded (ML-52);
  - fish tray colour tracks the label (ML-55);
  - fish held-out is one unseen batch (ML-51).
  Spoiled recall is reported per source with Wilson CIs.
- **MeatScan is never downloaded whole:** range reads from the 25 GB RAR, excluding the authors' augmentations. Roboflow copies of one photo share a split group (ML-50). A demoted cell moves wholly to train (ML-53). The Colab dataset cache is keyed by a `sources.json` hash.
- **Owner: cross-split pHash pairs are a warning in `stratification_check`.** `leakage_check`'s identity pHash ≤ 1% per source stays the gate. The pHash session merge is used only for measurability (with the 600 cap), never to loosen the span rule.
- **Owner: PL-5 won't be fixed.** MeatScan's two markets shoot in the same minute, so no timestamp-sound key gives more than 3 units. Beef stays train-only.
- **Owner: #62 merged on the go-ahead** after independent QA on the full 8-source dataset (food-main-mac): leakage PASS on every source, stratification PASS, parent_sibling 0. Held-out spoiled is 495 images, 68% AgriFreshNET.
- **The pre-#62 dataset (a2b) had a real leak** (fridge_objects held-out vs train 13 s apart), caught by the fixed ML-59 rule and absent from the #62 build. No model was trained on a2b, so no quoted metric is affected.
- **The ML / data track belongs to teammate LemurTech22.** Other sessions build there only when the owner asks, as for #62's QA fixes. Work lands through PRs with independent QA.

## 2026-10-11 — Dark-mode artboards (owner)
- **The canvas has a Dark page with a dark artboard for every screen**, no longer deferred. They're generated from the light artboards with the adaptive tokens (`docs/design/tools/mkdark.py`), so the light artboards stay the single source and dark can't drift. iOS QA compares dark screenshots against them.

## 2026-10-11 — Design feedback round (owner + teammate, 21 canvas comments)
A UI/UX QA pass checked every comment. The owner made the product calls, and the rest follow the review.
- **Spoiled items in Photo review are decided inline** (Toss it / Keep it in a "Looks spoiled" section), not a chain of popups. **Toss counts as waste:** the item is created and then removed as `thrown_out` / `expired` (two calls in v1).
- **No extra swipe confirmation.** A swipe only opens the outcome sheet (with Cancel), and a 5 s Undo follows.
- **Freshness shows only when a photo assessed it**, in the badge ("Looks off"). No guessed ripeness for unphotographed food, and no "Photo check" text. Estimated expiry shows as a range.
- **Weights follow the Units setting** (US default: lb/oz). The API stays metric.
- **Kept against the comments:**
  - the Profile entry on Home (as an icon), because it's the only route to Settings and Delete account;
  - the Impact pill in the header, because it's the demo path's last step;
  - "Used it" rather than "Used in a recipe / ate it";
  - **"Shared it"** rather than "Gave to a friend", because `donated` also covers groups and the Food Pantry;
  - no "someone not on BiteDown" option, because the API stores recipients as users only, and no recipient is recorded when nobody claimed the item.
- **Tagline:** "Use what you have. Share what you spare." (from #49), replacing "Eat what you buy." on the sign-in screen.
- **Owner: requests can target several audiences at once** (friends and/or groups). One note shows on every chosen board, via a join table. Backend change queued.
- **Deferred:** per-item photo history (needs image storage and a privacy review) and a free-text waste note.
- The principles are in `docs/design/DESIGN_SYSTEM.md` → Principles.

## 2026-10-10 — Google Sign-In and removal rulings (#60, Fridge screen)
- **`POST /auth/oauth/google` returns `created: true|false` in the body** as well as 201/200, so the app doesn't depend on status codes.
- **Safe account linking.** A Google sign-in links to an existing password account only if `email_verified` is true and the email is `gmail.com` / `googlemail.com`, or a Workspace `hd` claim equals the email domain. Otherwise → 409 `account_exists_use_password`, and nothing is written. *Why:* for other domains Google's `email_verified` is weaker, and auto-linking would let anyone with a Google account for that address take over the password account. The rejected alternative was accepting the risk for the demo.
- **One Google identity per user.** A different Google subject for the same user → 409 `identity_conflict`, checked before the domain rule.
- **JWKS:** cached per `max-age`, an unknown `kid` is refetched at most every 30 s, 60 s leeway on `exp` / `iat`. Migration 0005's downgrade sets null password hashes to `'!'`, which can never match a password.
- **Gave it away on a claimed item always goes to the claimer** (no "Someone else" for v1, no API change). When the listing is open with no claimer, the recipient chooser is hidden and nothing is recorded as recipient.
- **Removal motion:** the row collapses at the tap, behind the sheet, and the sheet holds 200 ms so the checkmark is seen. The request fires at the tap, so the action is never delayed.

## 2026-10-10 — Backend wave 2 rulings (#57, #54)
- **Number caps (BE-9):** `est_price` ≤ 99,999,999.99 (numeric(10,2)), `quantity` ≤ 1e6, `est_weight_kg` ≤ 1e5. Anything above → 400 `validation_error`. The last two columns are unbounded, but huge floats overflowed the CO₂e and weight maths into invalid JSON.
- **`uses_items` is `[{item_id, name, predicted_expiry}]`**, matched back to the user's items. The iOS `Recipe` model changes in the first screen PR that decodes recipes (Home).
- **The recipe cache is in-process** (6 h TTL, keyed on a hash of the active items). gunicorn runs one process, so the cache is shared. No Redis. Follow-up before integration QA: the gthread worker class (one process, threads) with a lock-guarded cache, so a slow Gemini call doesn't block other requests.
- **Backend PRs stay backend-only.** iOS client additions for new endpoints (`remove-batch` / `restore-batch`) go into the iOS screen PR that uses them.
- **Times are bucketed in UTC** (BE-10). Week buckets start Monday 00:00 UTC, and windows are exactly N × 24 h.
- **A malformed Gemini reply is an upstream error** (BE-13). `_generate` rejects anything that isn't a list or object: 502, or the default table for shelf life. Never a 500.
- **Receipt totals and coupons are filtered in the backend** (#54, BE-11 / BE-14). A line is dropped when an optional prefix plus a total / tax / payment / coupon keyword is followed only by numbers, card digits or a closed set of receipt words. So "TOTAL DUE" is dropped but "Total Cereal" is kept. A negative price is dropped too.
- **Self-signed QA doesn't pass the gate.** A builder's own QA, including a teammate's, is kept as their record, but only an independent QA verdict counts.

## 2026-10-10 — The app is called BiteDown (owner)
- **Product name: BiteDown** (owner). Teammate Truc (FrankinstyLe) proposed a rename as "BiteUp" in #49, and the owner chose **BiteDown**. #49's tagline, "Use what you have. Share what you spare.", and its positioning toward students and shared households come with it until the owner says otherwise.
- **The rename is user-facing only.** That covers the canvas (sign-in mark, settings version line, titles), the doc titles, the README and the iOS `CFBundleDisplayName`. Internal names stay: the Xcode target and scheme `FoodWasteReducer`, the repo, the Docker services and the bundle id. Renaming those would churn every open branch for no user-visible gain.

## 2026-10-10 — ML models handed to a teammate (owner)
- **ML model work is paused on our side.** A teammate is building the models. The Colab run, the `export.zip` YOLO gate, weights in `ml/serve`, the from-photo `source: "yolo"` check, GLM-OCR on MPS and further `ml/yolo` / `ml/eval` / pipeline data work are off the active queue until the owner says otherwise. The merged datasets, split rules, notebook and pipeline stay as they are. **The photo add flow, and so the demo path, runs on the existing Gemini-vision fallback** (`/items/from-photo` with `ML_SERVICE_URL` unset). Receipt OCR has no fallback (502), so receipt scan isn't available until the teammate's OCR lands.

## 2026-10-10 — Training data (Mac, stage 2)
- **Datasets and licences, verified on each source page:** fridge_objects (Roboflow, wajeeha workspace), hien_fridge (Roboflow, gracelearning) and VegQual (figshare 30596084) are all **CC BY 4.0**, which requires attribution (see `docs/ML.md` "Attributions" and the README). The fresh/stale fruit set is **raghavrpotdar/fresh-and-stale-images-of-fruits-and-vegetables (Kaggle, CC0)**.
- **Dropped `sriramr/fruits-fresh-and-rotten-for-classification`.** The Kaggle API reports its licence as "Unknown", so we can't confirm our use is allowed. `muhammad0subhan/fruit-and-vegetable-disease-healthy-vs-rotten` (CC0) was also rejected: at 5.2 GB it breaks the 8 GB disk budget on the Mac.

## 2026-10-10 — Motion
- **Motion is calm and functional** (`docs/design/MOTION.md`). It confirms an action, shows where
  something went, or shows that the app is working. The whole sequence takes at most 0.5 s, with
  stagger delays included. Composites animate as one unit. Reduce Motion gets fades, never a
  skipped animation. Haptics are used only at key moments.
- The values were **tuned by QA** with frame-by-frame tests of the canvas demos. Round 1 found
  stacked-bar segments coming apart, 680–770 ms sequences, a loud mic pulse and a missing
  reduce-motion state. Round 2 passed every check.

## 2026-10-10 — Orchestrator moved to the `food-main` session
- The orchestrator role (review, merge, rulings, design canvas, orchestrator-owned docs) moved from
  the VPS session `mobile-food` to the session `food-main`, to start with a fresh context. The Mac
  session `food-waste` still builds. The process is unchanged; see `CLAUDE.md` and the
  "Orchestrator handoff" section of `HANDOFF.md`.

## 2026-10-10 — Sign-in and screen set
- **Sign-in is email + Google only.** Sign in with Apple was removed: the capability can't be
  signed without a paid Apple Developer team, and passkeys need associated domains (also paid).
  SMS and magic links were rejected because they need paid or unbuilt email/SMS sending.
  `user_identities.provider` stays generic so a provider can be added later.
- **The screen set is complete for the idea: 22 screens** (`docs/design/SCREENS.md`), after an
  audit against `IDEA.md`. Preferences (units, default storage, currency) are stored on the device
  for v1. Forgot-password, onboarding, widgets, reminders, grocery list and dietary restrictions
  are deferred.
- **"I made this" on a recipe** marks its fridge ingredients as `used`, which closes the loop from
  recipes to Impact.

## 2026-10-10 — Wave 2 (iOS) decisions
- **Minimum iOS 18, built with Xcode 26 / the iOS 26 SDK.** iOS 26 gets the Liquid Glass tab bar, and iOS 18 gets the standard one. Xcode is pinned in `ios.yml`.
- **No TestFlight.** The owner doesn't have the paid Apple Developer Program. Development and QA use the **Simulator**. The demo runs on the **owner's iPhone, signed with a free Personal Team** (builds last 7 days). The team id and bundle id live in a gitignored `ios/Local.xcconfig`. Capabilities a free team can't sign are avoided: push, iCloud and App Groups, so **widgets are deferred**.
- **Demo connectivity: a Cloudflare quick tunnel from the Mac** (`scripts/demo_tunnel.sh`). It's HTTPS, so there are no ATS exceptions. The app's base URL is set at runtime in a Debug settings screen, because the tunnel URL changes per run. Compose stays bound to 127.0.0.1.
- **Freshness is stored on items** (`freshness`, `freshness_checked_at`, `confidence`), because flagging spoilage from photos is a core feature.
- **Account deletion** (`DELETE /auth/me`) is in scope, since the App Store requires it once sign-up exists. Undo-remove uses `POST /items/:id/restore` within 10 min.
- **Screen states:** empty and error use native `ContentUnavailableView`, loading uses skeleton rows, and an expired item's badge reads **"Expired"**.
- **The inactive tab colour** follows the system under Liquid Glass (IOS-3 closed as won't-fix).
- **Deferred:** onboarding, notifications, localisation, widgets. (Dark artboards were added on 2026-10-11.)

## 2026-10-10 — Gemini model, training venue
- **`GEMINI_MODEL=gemini-3.8-flash`.** This is the newest non-preview Flash model in the key's model list, as listed on the Mac on 2026-10-10. `gemini-3.8-flash-lite` is the fallback if cost or latency becomes a problem. Re-check the list before the demo, because preview and retired ids change.
- **The full YOLO26s training runs on Colab, not the Mac.** The MPS smoke run measured 173 s/epoch for yolo26s on VegQual alone, which puts the merged dataset at about 7.5 h for 80 epochs (6.5–9 h). The budget was 3 h. Short smoke runs and the pipeline checks stay on the Mac.
- **Held-out data must be split by capture time.** ML QA found that 127 of 132 timestamped held-out photos had a train or val shot within 10 s (ML-21). Without grouping by capture time, any accuracy number would be inflated.

## 2026-10-10 — Wave 1 decisions (backend core, ML, design)
- **YOLO26 via `ultralytics==8.4.175`.** That was the latest on PyPI on 2026-10-10, and Ultralytics' docs recommend YOLO26 for new projects (YOLO11 is the mature fallback). It is **AGPL-3.0**: fine for this public repo, but it matters if the code is ever closed. Details are in `docs/ML.md`.
- **Two-stage vision.** The detector predicts food *names* (about 50 classes, `ml/yolo/taxonomy.py`), and a separate `yolo26n-cls` classifier labels each crop fresh, semi_fresh ("use soon") or spoiled. semi_fresh was added on 2026-10-10 from teammate LemurTech22's work, and its gates stay binary (see `docs/QA.md`). *Why:* the fridge datasets have no freshness labels and the produce datasets have no fridge scenes. The consequence is that spoiled recall is effectively a produce-only number.
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
- **Demo connectivity:** how the phone reaches the API (same Wi-Fi as a laptop, a tunnel, or a hosted backend).
