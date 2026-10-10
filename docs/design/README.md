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
| Sign in (sign up / log in, green buttons with light text) | `screens/Main.dc.html` | awaiting approval |
| Home + tab bar (Home, Recipes, + Add, Fridge, Social) | `screens/Home.dc.html` | awaiting approval |
| Fridge / Pantry list (segmented storage, expiry badges, swipe to remove, spoilage flag) | `screens/Fridge.dc.html` | awaiting approval |
| Removal sheet, step 1: outcome (used / gave away / threw away) | `screens/RemoveSheet.dc.html` | awaiting approval |
| Removal sheet, step 2: waste reason (one tap) | `screens/RemoveReason.dc.html` | awaiting approval |
| Add sheet (fridge photo, one item, type/say, barcode, receipt) | `screens/AddSheet.dc.html` | awaiting approval |
| Social (Food Pantry widget, sticky-note requests, + friends/groups) | `screens/Social.dc.html` | awaiting approval |
| Impact Dashboard (CO₂e hero, saved/money, weekly chart, waste reasons) | `screens/Impact.dc.html` | awaiting approval |
| Add: review photo results (detected items, predicted expiry, spoilage flag, untick to skip) | `screens/PhotoReview.dc.html` | awaiting approval |
| Recipes tab (filters, best match using expiring items, more suggestions) | `screens/Recipes.dc.html` | awaiting approval |

**Approval:** record who approved and the date here before Wave 2 (iOS) starts. Changes requested
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
- The design is **not yet approved** for Wave 2. The owner has more changes coming.

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
