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

**Approval:** record who approved and the date here before Wave 2 (iOS) starts. Changes requested
on the canvas get mirrored back into `screens/` and `DESIGN_SYSTEM.md`.

## Interaction notes for iOS
- **Removal is one or two taps.** Swipe left on a row to reveal **Remove**, which opens the sheet.
  *Used it* and *Gave it away* finish immediately. *Threw it away* goes to the reason grid, where
  one tap finishes. *Gave it away* shows a "Gave it to" picker only when the item has an open Share
  listing.
- The **Add** tab-bar button is a raised 60 pt circle that opens the Add sheet. It is not a real tab.
- The **Food Pantry** widget is collapsed by default (chips preview) and expands in place.
- **Request notes** use two alternating fills and a slight rotation (±1.2° max). The header row
  always names the source (friend or group).
- The **Impact** chart is a stacked bar per week: saved (bottom) and thrown out (top), with a 2 pt
  surface gap. Values are labeled above each bar because the orange fails 3:1 against white.
  Build it with Swift Charts and add selection for per-week detail.
