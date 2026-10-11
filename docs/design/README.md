# Design

The live canvas for the key screens, made with Claude's Design canvas and following taste-skill's
rules, is at
**https://claude.ai/artifact/ALmB8FYKGrayhDQXqvoncx**. It's private, so the owner has to share it
before teammates can open it. The source of every artboard is mirrored in `screens/`. These are
`.dc.html` mockups, **not SwiftUI**. iOS translates them into native views using
`ios/App/Theme.swift`, the code mirror of [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md).

Design read: a consumer iOS utility for students and shared households. Calm and practical, with a
fresh-produce palette and native iOS conventions (sheets, swipe actions, segmented controls,
system body type).

| Screen | Artboard | Status |
|---|---|---|
| Sign in (sign up / log in, green buttons with light text) | `screens/Main.dc.html` | approved 2026-10-10 |
| Home + tab bar (Home, Recipes, + Add, Fridge, Social) | `screens/Home.dc.html` | approved 2026-10-10 |
| Fridge / Pantry list (segmented storage, expiry badges, swipe to remove, spoilage flag) | `screens/Fridge.dc.html` | approved 2026-10-10 |
| Removal sheet, step 1: outcome (used / gave away / threw away) | `screens/RemoveSheet.dc.html` | approved 2026-10-10 |
| Removal sheet, step 2: waste reason (one tap) | `screens/RemoveReason.dc.html` | approved 2026-10-10 |
| Add sheet (fridge photo, one item, type/say, barcode, receipt) | `screens/AddSheet.dc.html` | approved 2026-10-10 |
| Social (Food Pantry widget, sticky-note requests, + friends/groups) | `screens/Social.dc.html` | approved 2026-10-10 |
| Impact Dashboard (CO₂e hero, saved/money, weekly chart, waste reasons) | `screens/Impact.dc.html` | approved 2026-10-10 |
| Add: review photo results (detected items, predicted expiry, spoilage flag, untick to skip) | `screens/PhotoReview.dc.html` | approved 2026-10-10 |
| Recipes tab (filters, best match using expiring items, more suggestions) | `screens/Recipes.dc.html` | approved 2026-10-10 |
| Sign up (Apple / Google / email form) | `screens/SignUp.dc.html` | added 2026-10-10 (owner request) |
| Log in (Apple / Google / email, inline error state) | `screens/LogIn.dc.html` | added 2026-10-10 (owner request) |

**Approval:** ✅ **Approved by the owner on 2026-10-10** (relayed through the Mac session), including feedback rounds 1–2, the native glass tab bar, "Use soon" and the colourful food-group icons. Wave 2 (iOS) has started. Changes requested
on the canvas get mirrored back into `screens/` and `DESIGN_SYSTEM.md`.

## Owner feedback round 1 (2026-10-10), applied
- **Sign in:** less empty space. A value-points card now sits between the headline and the buttons.
- **Fridge:** items are grouped by **food group** (protein, veggies, fruit, ...), each with an icon. No emoji. Home's list uses the same icons.
- **Photo review:** every detected item has a **quantity stepper**. Expiry moved into the meta line.
- **Recipes:** **macros** per serving (kcal / protein / carbs / fat) on the best match, and kcal + protein on the other suggestions.

These need two backend additions (see `docs/API.md` once built):
- `food_group` on items and candidates.
- `macros` on recipe suggestions.

## Owner decisions, 2026-10-10 (round 2)
- **Native glass tab bar**, with Add as a tab. All tabbed artboards are updated.
- **`semi_fresh` is a product feature.** Food that's fine but should be eaten soon gets a **"Use soon"** badge on the Fridge, and "ripe, use soon" on photo review.
- **Food-group icons are colourful**, and the removal sheet header uses them too.
- **Approved on 2026-10-10.** Wave 2 started.

## Sign-in (owner request, 2026-10-10)
- The landing screen keeps **Sign up / Log in** (green, as in the brief) and adds **"or continue with" Apple | Google**. The Sign up and Log in screens offer Apple and Google first, then email.
- **Use the official buttons, not the mockup's drawing.** The mockups show **dashed placeholders** where the logos go, because we don't redraw brand marks.
  - **Apple:** `SignInWithAppleButton` / `ASAuthorizationAppleIDButton`, black style in light mode and white in dark, with the label variant matching the screen (Sign up / Sign in / Continue).
  - **Google:** the button from the Google Sign-In SDK, or one built strictly to Google's branding guidelines: white, a `#747775` border, `#1F1F1F` text and the official "G" mark.
  - Apple and Google buttons are the **same size and prominence** (App Store guideline 4.8).
- **Sign in with Apple needs a paid Apple Developer Program team.** The capability can't be signed with the free Personal Team we use for the demo. So the Apple button sits behind a feature flag and is **hidden in Personal-Team builds**. It turns on once a paid team exists, and the backend supports it either way. Google works with a free Google Cloud OAuth client.
- Email: labels above inputs, a show-password toggle, the hint "At least 8 characters", and inline errors below the field (Log in shows the error state). "Forgot password" is **deferred**, because there's no email sending yet.

## Keeping the canvas in sync during Wave 2
The **orchestrator owns the canvas** and `docs/design/`, so there's a single writer and no publish conflicts. When an iOS PR deviates from an artboard, for a platform reason or a new state, the PR description includes a **"Design delta"** section: the artboard, what changed and why, plus a Simulator screenshot in `docs/qa/ios/`. The orchestrator updates the canvas and `screens/` to match when it merges the PR.

## Interaction notes for iOS
- **Removal is one or two taps.** Swipe left on a row to reveal **Remove**, which opens the sheet.
  *Used it* and *Gave it away* finish immediately. *Threw it away* goes to the reason grid, where
  one tap finishes. *Gave it away* shows a "Gave it to" picker only when the item has an open Share
  listing.
- **Tab bar (decided):** the native iOS 26 glass `TabView`. **Add is a tab** that presents the Add sheet and doesn't change the selected tab. There's no raised button.
- **Photo review** is the demo path's middle step. Snap your fridge → `POST /items/from-photo` →
  this screen → `POST /items`. Every detected item starts ticked, except ones the classifier flags
  as spoiled, which start unticked with "Looks spoiled. Toss it?". Low-confidence items say "not
  sure, tap to fix". Expiry badges come from the candidate's `predicted_expiry`. The footer
  explains that dates are estimates and can be edited, and the primary button counts the ticked
  items.
- **Recipes** come from `POST /recipes/suggest`. The best match is the hero card, with chips naming
  each expiring item it uses and how soon it expires. The other suggestions are rows with a
  "Uses N" badge and anything you'd need to buy.
- The **Food Pantry** widget is collapsed by default (chips preview) and expands in place.
- **Request notes** use two alternating fills and a slight rotation (±1.2° max). The header row
  always names the source (friend or group).
- The **Impact** chart is a stacked bar per week: saved (bottom) and thrown out (top), with a 2 pt
  surface gap. Values are labeled above each bar because the orange fails 3:1 against white.
  Build it with Swift Charts and add selection for per-week detail.
