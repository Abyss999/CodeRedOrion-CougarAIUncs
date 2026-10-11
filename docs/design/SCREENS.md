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
| 4 | Home | `Home` | Use-first list, cook tonight, tip, impact pill | `GET /items` (soonest), `POST /recipes/suggest` (cached), `GET /tips`, `GET /impact` | A **Profile and settings** icon button (not an avatar) opens Profile. Weights in lb/oz per the Units setting. The tip is a dismissible one-line observation. The Impact pill stays in the header |
| 5 | Fridge / Pantry | `Fridge` | View all food (core 5), food groups, freshness | `GET /items?storage=&group_by=food_group` | One status per row: the badge ("Use soon", "Looks off" for spoiled, an estimated range like "2–3 days", "Expired"). Meta = quantity only. Tap → Item detail. Swipe → Remove (no extra confirm: the sheet has Cancel, plus a 5 s Undo) |
| 6 | Item detail / edit | `ItemDetail` | Edit, see the expiry source, share | `PATCH /items/:id`, `POST /share`, `DELETE /share/:id` | "estimated" chip when `expiry_source != user`. The Share toggle shows the audience and any claim. **Check again** (photo → `POST /items/from-photo` mode=single → `PATCH` freshness). **What to look for**: 2–3 static spoilage signs per category, "signs, not a safety guarantee". Per-item photo history is deferred (it needs image storage) |
| 7 | Remove: outcome | `RemoveSheet` | **Core 3**: used / shared / threw away | `POST /items/:id/remove` | Titles only, no captions: **Used it** · **Shared it** ("Gave it to <claimer>" on a claimed listing; no "Someone else" in v1) · **Threw it away**. Header meta "<qty> · expires <when>", with a small shared badge on the icon when listed. 5 s Undo → `POST /items/:id/restore` |
| 8 | Remove: waste reason | `RemoveReason` | One-tap reason | (same call, `waste_reason`) | Expired / Forgot / Didn't like / Other, titles only |
| 9 | Add sheet | `AddSheet` | **Core 2**: 5 ways to add | (none) | |
| 10 | Photo review | `PhotoReview` | Fridge or single photo → items | `POST /items/from-photo`, `POST /items` | A **Looks spoiled** section on top, with **Toss it** / **Keep it** per item. "Add N" stays disabled until each is decided. Toss = create, then remove as `thrown_out` / `expired` (it counts as waste). Keep = add with freshness spoiled. Confidence < 0.5 shows "not sure". Quantity stepper |
| 11 | Type or say it | `AddText` | Text or voice → items | `POST /items/parse-text`, `POST /items` | Speech framework dictation. Needs mic and speech permission strings |
| 12 | Barcode result | `BarcodeResult` | Barcode → item | `GET /items/barcode/:code`, `POST /items` | Native `DataScannerViewController`. "Not this?" → Type it |
| 13 | Receipt review | `ReceiptReview` | Receipt → items | `POST /items/from-receipt`, `POST /items` | Native `VNDocumentCameraViewController`. Shows the raw line under each cleaned name. Non-food starts unticked |
| 14 | Recipes | `Recipes` | **Core 4** | `POST /recipes/suggest` | Filters: expiring first, under 30 min, vegetarian. Macros |
| 15 | Recipe detail | `RecipeDetail` | Cook from what you have | (the suggestion's payload), then `POST /items/:id/remove` ×N (outcome `used`) | "I made this" marks its fridge items used, which feeds Impact |
| 16 | Impact | `Impact` | Impact dashboard (main goal) | `GET /impact?range=` | CO₂e hero, saved/money tiles, 6-week chart, waste reasons. **The screen scrolls**: the waste-reasons section sits below the fold on a 390×844 screen, so the artboard clips it |
| 17 | Social | `Social` | Food Pantry widget + request board | `GET /share`, `GET /requests`, `POST /requests/:id/fulfil` | "I have it" button is 44 pt. Sticky notes with their source header |
| 18 | Food Pantry | `FoodPantry` | Shared surplus (main goal) | `GET /share`, `POST /share/:id/claim` | All / Friends / Groups filter |
| 19 | Ask for something | `RequestComposer` | Post a request | `POST /requests` | 280-character limit. Audience: a **multi-select** checklist (Friends and/or any of your groups, at least one). One note shows on every chosen board. Needs the multi-audience `POST /requests` (queued) |
| 20 | Friends & groups | `Connect` | Social "+" | `POST /friends`, `POST /friends/:id/accept`, `DELETE /friends/:id`, `POST /groups/join`, `POST /groups`, `GET /groups` | Accept / decline friend requests |
| 21 | Group | `GroupDetail` | Groups with their own pantries (main goal) | `GET /groups/:id`, `GET /groups/:id/pantry`, `POST /items` (`group_id`), `POST /groups/:id/leave` | Share invite via the system share sheet |
| 22 | Profile & settings | `Settings` | Account and preferences | `DELETE /auth/me` | Units, default storage and currency are **stored on the device for v1**. Sign out, Delete account (with confirmation) |

## Coverage check against IDEA
- **Must-haves:** spoilage groups (5, 6), all five ways to add (9–13), removal with outcome (7, 8), recipes (14, 15), viewing all food (5). ✅
- **Main goals:** friends (20), shareable pantry (6, 18), request board (17, 19), group pantries (21), Impact (16). ✅
- **Supporting:** expiry shown with its source (6, 10), spoilage from photos (5, 10), personal tips (4). ✅
- **Stretch, deferred:** widgets (blocked: they need a paid team for App Groups), spoilage reminders (push), grocery list, dietary restrictions. **Recipe macros are done** (14, 15).
- **Dark mode:** every screen has a dark artboard (`<Name>.dark.dc.html`, the canvas's Dark page), generated from the light one by `docs/design/tools/mkdark.py` with the adaptive tokens. Edit the light artboard, then regenerate.
- **Also deferred:** onboarding, password reset, localisation.
