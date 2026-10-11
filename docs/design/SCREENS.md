# Screen inventory

Every screen the app needs, checked against [`docs/IDEA.md`](../IDEA.md). It's the single list
that iOS builds and QA tests against.

- Artboards are in [`screens/`](screens/) and on the canvas,
  https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx.
- Tokens and components are in [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md).
- **Every data screen also needs three states** (standing Design delta):
  - empty and error: native `ContentUnavailableView` with a retry action
  - loading: skeleton rows shaped like the final layout
- Pushed screens keep the tab bar; the artboards omit it.
- Animation for every screen is in [`MOTION.md`](MOTION.md).

## Navigation map
```
Landing ─┬─ Sign up ─┐
         └─ Log in ──┴─▶ Tab bar
Tab bar: Home │ Recipes │ [Add] │ Fridge │ Social            (iOS 26 glass TabView; Add is a tab that presents a sheet)
Home ──▶ Profile & settings (avatar) · Impact (saved pill) · Fridge (See all) · Recipe detail (Cook tonight)
Recipes ──▶ Recipe detail ──▶ "I made this" (marks the ingredients used)
Add sheet ─┬─ Snap your fridge ─▶ Photo review ─┐
           ├─ One item (photo) ─▶ Photo review ─┤
           ├─ Type or say it ───▶ (inline list) ┤
           ├─ Barcode ─▶ (native scanner) ─▶ Barcode result ┤
           └─ Receipt ─▶ (native doc camera) ─▶ Receipt review ┴─▶ Fridge
Fridge ──▶ Item detail ──▶ Remove: outcome ──▶ Remove: waste reason (thrown out only)
Fridge row swipe ──▶ Remove: outcome
Social ─┬─ Food Pantry widget ─▶ Food Pantry (claim)
        ├─ "Post one" ─▶ Ask for something
        ├─ Request note "I have it" (fulfil)
        └─ "+" ─▶ Friends & groups ─▶ Group (group pantry, requests)
```

## Screens
| # | Screen | Artboard | Purpose (IDEA ref) | API | Notes |
|---|---|---|---|---|---|
| 1 | Landing | `Main` | Sign-in entry | (none) | One large app mark (no wordmark), tagline "Use what you have. Share what you spare.", value points as titles only, buttons follow the content. Green **Sign up / Log in**, then **Continue with Google**. No Apple |
| 2 | Sign up | `SignUp` | Account creation | `POST /auth/signup`, `POST /auth/oauth/google` | Labels above the fields, show-password toggle, 8-character minimum |
| 3 | Log in | `LogIn` | | `POST /auth/login`, `POST /auth/oauth/google` | Inline error state is drawn. Forgot-password is **deferred** (no email sending yet) |
| 4 | Home | `Home` | Use-first list, cook tonight, tip, impact pill | `GET /items` (soonest), `POST /recipes/suggest` (cached), `GET /tips`, `GET /impact` | A dismissible one-line **tip at the top** (owner), then Use these first, Cook tonight and the Impact pill. A **Profile and settings** icon button opens Profile. Weights in lb/oz per the Units setting |
| 5 | Fridge / Pantry | `Fridge` | View all food (core 5), food groups, freshness | `GET /items?storage=&group_by=food_group` | One status per row: the badge ("Use soon", "Looks off" for spoiled, an estimated range like "2–3 days", "Expired"). Meta = quantity only. Tap → Item detail. Swipe → Remove (no extra confirm: the sheet has Cancel, plus a 5 s Undo) |
| 6 | Item detail / edit | `ItemDetail` | Edit, see the expiry source, share | `PATCH /items/:id`, `POST /share`, `DELETE /share/:id` | "estimated" chip when `expiry_source != user`. The Share toggle shows the audience and any claim. **Check again** (photo → `POST /items/from-photo` mode=single → `PATCH` of `freshness` + `confidence` + `freshness_checked_at` only; the image and the other candidates are discarded, nothing is stored). **What to look for**: 2–3 static spoilage signs per category, "signs, not a safety guarantee". Per-item photo history is deferred (it needs image storage) |
| 7 | Remove: outcome | `RemoveSheet` | **Core 3**: used / shared / threw away | `POST /items/:id/remove` | Titles only: **Used it** (acts in one tap) · **Shared it** (selected → a **Given to** menu row above Cancel, defaulting to the claimer, else "Someone not on BiteDown"; options: the claimer, friends, fellow group members, **Someone not on BiteDown**; then **Done**) · **Threw it away** (→ reason). Header meta "<qty>" with an expiry badge; a shared badge on the icon when listed. 5 s Undo → `POST /items/:id/restore`. Needs `recipient_id` (explicit `null` = someone not on BiteDown), queued as `feat/donation-recipient` |
| 8 | Remove: waste reason | `RemoveReason` | One-tap reason | (same call, `waste_reason`) | Title "Why was it thrown out?"; a native grouped list of four 56 pt rows (icon + title): Expired / Forgot / Didn't like / Other |
| 9 | Add sheet | `AddSheet` | **Core 2**: 5 ways to add | (none) | Hero "Snap your fridge" (88 pt, full width) plus 2×2 options; Barcode hint "Boxes, cans, jars" |
| 10 | Photo review | `PhotoReview` | Fridge or single photo → items | `POST /items/from-photo`, `POST /items` | A **Looks spoiled** section on top, with **Toss it** / **Keep it** per item. "Add N" stays disabled until each is decided. Toss = create, then remove as `thrown_out` / `expired` (it counts as waste). Two calls are accepted for v1: if the remove fails, the item stays in the fridge with freshness spoiled ("Looks off") and a banner says so, so the user can remove it (`PhotoReviewError`). Keep = add with freshness spoiled. Confidence < 0.5 shows "not sure". Quantity stepper |
| 11 | Type or say it | `AddText` | Text or voice → items | `POST /items/parse-text`, `POST /items` | Speech framework dictation. Needs mic and speech permission strings |
| 12 | Barcode result | `BarcodeResult` | Barcode → item | `GET /items/barcode/:code`, `POST /items` | Native `DataScannerViewController`. "Not this?" → Type it |
| 13 | Receipt review | `ReceiptReview` | Receipt → items | `POST /items/from-receipt`, `POST /items` | Native `VNDocumentCameraViewController`. Shows the raw line under each cleaned name. Non-food starts unticked |
| 14 | Recipes | `Recipes` | **Core 4** | `POST /recipes/suggest` | The first chip **"Only what I have"** is on by default (recipes whose `missing_items` is empty; the client filters a request for 10). An empty state offers "Show recipes that need a few things". Other filters: expiring first, under 30 min, vegetarian. Macros |
| 15 | Recipe detail | `RecipeDetail` | Cook from what you have | (the suggestion's payload), then `POST /items/:id/remove` ×N (outcome `used`) | "I made this" marks its fridge items used, which feeds Impact |
| 16 | Impact | `Impact` | Impact dashboard (main goal) | `GET /impact?range=` | Hero **Food saved** in lb (client converts `saved.kg`), "Previous 30 days" under it. CO₂e is a secondary line with a driving equivalent. Tiles: Items saved, money; 6-week chart; waste reasons. **The screen scrolls** |
| 17 | Social | `Social` | Food Pantry widget + request board | `GET /share`, `GET /requests`, `POST /requests/:id/fulfil` | Food Pantry widget: "Shared by friends and groups", 3 food tiles plus "+N more", no counts. Request notes have an **Offer** button (44 pt, VoiceOver "Offer to <name>: <item>") → **Offer confirmation** (row 38) → `POST /requests/:id/fulfil` |
| 18 | Food Pantry | `FoodPantry` | Shared surplus (main goal) | `GET /share`, `POST /share/:id/claim` | All / Friends / Groups filter (no counts). Rows keep quantities, which are needed before claiming |
| 19 | Ask for something | `RequestComposer` | Post a request | `POST /requests` | 280-character limit. Audience: a **multi-select** checklist (Friends and/or any of your groups, at least one). One note shows on every chosen board. Uses the multi-audience `POST /requests` `audiences {friends, group_ids}` (**shipped in #66**); received notes show audiences you can't see as `hidden_count` ("+2 other groups") |
| 20 | Friends & groups | `Connect` | Social "+" | `POST /friends`, `POST /friends/:id/accept`, `DELETE /friends/:id`, `POST /groups/join`, `POST /groups`, `GET /groups` | Accept / decline friend requests |
| 21 | Group | `GroupDetail` | Groups with their own pantries (main goal) | `GET /groups/:id`, `GET /groups/:id/pantry`, `POST /items` (`group_id`), `POST /groups/:id/leave` | Share invite via the system share sheet |
| 22 | Profile & settings | `Settings` | Account and preferences | `DELETE /auth/me` | Units, default storage and currency are **stored on the device for v1**. The API stays metric everywhere; **the iOS client converts kg to lb/oz** for display wherever weights appear (Home, Fridge, Item detail, Impact). Sign out, Delete account (with confirmation) |
| 23 | Launch | `Launch` | Session restore | (Keychain token, then any authed call) | App mark and a native activity indicator while the stored sign-in is checked. Routes to Home (signed in) or Landing. Gap audit 2026-10-11 |
| 24 | Signed out | `SessionExpired` | Re-auth after a 401 | `POST /auth/login`, `POST /auth/oauth/google` | Landing with an inline, non-modal banner: "You were signed out. Log in again to pick up where you left off." |
| 25 | Fridge, first use | `FridgeEmpty` | Empty state for row 5 | `GET /items` (empty) | Native empty state: "Nothing in your fridge yet", one line, **Add food** → Add sheet. Search hidden |
| 26 | Home, first use | `HomeEmpty` | Empty state for row 4 | `GET /items`, `GET /impact` (zeros) | "0 lb saved" pill; "Use these first" becomes an Add food card; Cook tonight is a muted placeholder; no tip |
| 27 | Camera off | `CameraDenied` | Permission denied on row 9 | (none) | Inline card: "Camera access is off" with **Open Settings** and **Type it instead**. Camera options show "Off"; voice-off falls back to typing |
| 28 | Can't reach BiteDown | `ServerError` | Global offline / server error | any; `GET /health` for Try again | Non-modal banner plus the section error state with **Try again**. A **Server address** row (the demo tunnel URL changes per run) links to Settings |
| 29 | Finding your food | `PhotoAnalyzing` | Progress for row 10 | `POST /items/from-photo` (5–15 s) | Photo, native progress indicator, "Finding your food…", **Cancel**. No fake percentages |
| 30 | Photo found nothing / failed | `PhotoReviewError` | Errors for row 10 | `POST /items/from-photo` (no candidates, 502) | Drawn: no candidates, "We couldn't spot any food" with **Retake photo** / **Type it instead**. Not drawn, same layout as a banner: 502 "Photo analysis is down right now. Your photo wasn't saved." with **Try again**; and the Toss partial failure (row 10) "Couldn't mark <item> as thrown out. It's in your fridge as Looks off." |
| 31 | Google sign-in error | `GoogleSignInError` | Errors for rows 2–3 | `POST /auth/oauth/google` | Drawn: 409 `account_exists_use_password` ("This email already has a BiteDown password…", email prefilled). Same alert card, not drawn: 409 `identity_conflict` "This account is already linked to a different Google account."; 403 `email_not_verified` "Verify your Google email, then try again."; 503 `oauth_not_configured` "Google sign-in isn't available right now. Use email instead." |
| 32 | Item shared (owner) | `ItemShared` | Owner's view of a claimed listing (row 6) | `GET /share`, `POST /items/:id/remove` (`donated`), `DELETE /share/:id` | "Claimed by <name>", Stop sharing, and a primary **Remove** that opens the Remove sheet with Shared it + Given to defaulting to the claimer |
| 33 | Fridge, select | `FridgeSelect` | Multi-select on row 5 | `POST /items/remove-batch` | "3 selected" / Done; circular checkboxes; a bottom bar **Used them** / **Shared them** replaces the tab bar. Throwing away stays per item (it needs a reason) |
| 34 | Batch undo | `BatchUndo` | Undo for row 33 | `POST /items/restore-batch` | The Undo toast as shipped (#64, Design delta 20): "3 items marked used", **Undo**, 3 pt progress strip |
| 35 | Impact, ranges | `ImpactRange` | Row 16 with ranges | `GET /impact?range=week\|month\|all` | Week / Month / All; a "vs previous" chip per headline (arrow plus words, never colour alone; none for All, since `previous` is null); used vs given-away stacked bar. Taller artboard (scrolls) |
| 36 | Your requests | `MyRequests` | The author's requests (row 17) | `GET /requests`, `DELETE /requests/:id` | Open notes with **Cancel**; fulfilled notes show "Fulfilled by Marcus Ojeda" |
| 37 | Friends, pending | `ConnectPending` | Row 20 with sent requests and errors | `GET /friends` (`outgoing`), `DELETE /friends/:id`, `POST /friends` | "Sent · 1" with **Withdraw**; inline field error "No BiteDown account uses that email." |
| 38 | Offer confirmation | `FulfilConfirm` | Confirm before fulfilling a request (it closes the request for everyone, with no undo) | `POST /requests/:id/fulfil` | The note, three lines on what happens (they see you have it, the note leaves the board, you sort out the handoff), **I have it** + Cancel. No in-app messaging is promised |

## Coverage check against IDEA
- **Must-haves:** spoilage groups (5, 6), all five ways to add (9–13), removal with outcome (7, 8), recipes (14, 15), viewing all food (5). ✅
- **Main goals:** friends (20), shareable pantry (6, 18), request board (17, 19), group pantries (21), Impact (16). ✅
- **Supporting:** expiry shown with its source (6, 10), spoilage from photos (5, 10), personal tips (4). ✅
- **Stretch, deferred:** widgets (blocked: they need a paid team for App Groups), spoilage reminders (push), grocery list, dietary restrictions. **Recipe macros are done** (14, 15).
- **Dark mode:** every screen has a dark artboard (`<Name>.dark.dc.html`, the canvas's Dark page), generated from the light one by `docs/design/tools/mkdark.py` with the adaptive tokens. Edit the light artboard, then regenerate.
- **States from the 2026-10-11 gap audit (owner-approved):** launch and sign-out (23, 24), first-use empty states (25, 26), permissions (27), offline/server error (28), photo progress and failures (29, 30), Google errors (31), sharing owner view (32), batch remove/undo (33, 34), Impact ranges (35), your requests and pending friends (36, 37).
- **Also deferred:** onboarding, password reset, localisation.
