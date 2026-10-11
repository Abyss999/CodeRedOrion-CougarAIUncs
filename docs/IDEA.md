# BiteUp — product idea

> Built from the project brief. The original brainstorm doc hasn't been added yet — merge it in
> here when it is, and note any changes in `DECISIONS.md`.

## The problem
Households throw away a large share of the food they buy, mostly because they forget what they
have until it has gone off. Wasted food carries the emissions from producing, transporting and
storing it, plus the methane it makes in landfill. This app makes "what's in my fridge, and what
do I eat first" effortless, and **measures** the waste it prevents.

## Climate angle
Every removal records an outcome. That turns the app into a measurement tool:
**food saved** (used + donated) vs **food wasted** (thrown out), expressed as money and
**kg CO₂e avoided** using per-category emission factors. The Impact Dashboard is the proof.

## Core features (must have)
1. **Classify food into spoilage groups** — category + storage (fridge / pantry / freezer)
   determines the expiry model.
2. **Add food** — photo of the whole fridge/pantry, single-item photo, text lookup (Gemini parses
   "2 lbs chicken, a bag of spinach"), barcode scan (Open Food Facts), receipt scan (GLM-OCR).
3. **Remove food with an outcome** — the core loop:
   - **Used it** → food saved.
   - **Gave it away / donated** → food saved; fulfils the item's Share listing if it had one
     (optionally records who received it).
   - **Threw it away** → waste; one-tap reason: expired, didn't like it, forgot about it, other.
   Swipe-to-remove opens a 3-option sheet; one or two taps total.
4. **Recipes from what you have** — Gemini, prioritising items closest to expiry.
5. **View all added food** — Fridge/Pantry list sorted by expiry.

## Supporting intelligence
- **Expiry prediction** — category defaults + Gemini inference, shown with its source.
- **Spoilage detection** from photos (YOLO: fresh / use soon / spoiled).
- **Learning from removals** — an item removed after its predicted expiry is feedback for the
  prediction. Waste reasons feed personal tips ("you always forget the spinach").

## Main goals (after the must-haves)
- Friends, a shareable **Food Pantry**, a **request board** (sticky-note feed of friend/group
  requests), **groups with their own pantries**, and the **Impact Dashboard** (food saved, waste,
  money saved, CO₂ avoided, weekly trends, waste rate over time).

## Stretch
Home-screen widgets, spoilage reminders (push), grocery list, dietary restrictions, recipe macros.

## Future
Smart shopping list, allergy onboarding, group fridge.

## UI direction
- Colors: light green-yellow, deeper greens for contrast.
- Sign-in: simple, two buttons (log in / sign up), green with light text, plus **Continue with Google**. There is no Apple sign-in, because it needs a paid developer account.
- Bottom tab bar (Instagram / MyFitnessPal style): **Home, Recipes, [ + Add ], Fridge/Pantry, Social**.
- Social tab: Food Pantry widget first (tap to expand), then a sticky-note feed of requests, each
  headed with its source (friend or group). A **+** at the top adds friends or joins/creates a group.
- Add button options: fridge/pantry photo, single food photo, text lookup, barcode scan, receipt scan.

## Demo path (what judges see)
Add food by photo → get an expiry prediction → remove it with an outcome → watch the Impact
Dashboard update.
