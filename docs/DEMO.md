# BiteDown demo script

## Five-minute presenter script

### 0:00–0:25 — Introduction

**Say:** “BiteDown helps people keep track of food, decide what to use next, and record what happened to it. I’ll show the path from adding food by photo to seeing how its outcome appears in Impact.”

### 0:25–1:35 — Add food from a photo

**Tap:** Open **Add**, choose the photo option, and select a prepared food or fridge photo. Review the suggested items before continuing.

**Audience sees:** A review of the items detected in the photo. Check the suggested item and its details, then add it to the inventory.

**Say:** “Photo suggestions are a starting point, not a substitute for checking the item. I’ll review this suggestion before adding it.”

### 1:35–2:10 — Show the predicted expiry

**Tap:** Open the added item or its inventory row and point to the predicted expiry and its displayed source.

**Audience sees:** An estimated expiry based on category defaults and Gemini inference. The app shows the prediction source; dates are estimates and can be corrected.

**Say:** “This date is an estimate, so it is useful for prioritizing food, not a guarantee about freshness or safety.”

### 2:10–3:10 — Remove it with an outcome

**Tap:** Return to the inventory, swipe the item to remove it, and choose one outcome: **Used it**, **Shared it** (donated), or **Threw it away**. If you choose **Threw it away**, select a reason.

**Audience sees:** The item leave the active inventory after the outcome is recorded. A donated outcome counts as food saved; a thrown-out outcome counts as food wasted.

**Say:** “The outcome is what makes this removal meaningful. I’m recording what happened, rather than just making the item disappear.”

### 3:10–4:05 — Open Impact

**Tap:** Open **Impact** from the app. If the Home screen does not expose it in this build, use the configured debug route; how to enable that route: **TODO: confirm**.

**Audience sees:** The Impact view for recorded food events, including saved and wasted outcomes and modeled impact figures where shown. Whether this screen is integrated into the demo build: **TODO: confirm**.

**Say:** “Impact is based on recorded food events. The associated money and CO₂e figures are estimates; they do not prove that additional waste was prevented.”

### 4:05–4:45 — Undo and compare

**Tap:** Return to the item or use the available Undo action for the removal, then open or refresh **Impact**.

**Audience sees:** The item restored, while Impact remains as it was before the removal was undone.

**Say:** “Undo restores the item without changing Impact from its pre-removal state. That is the expected behavior; the integrated demo path still needs confirmation.”

### 4:45–5:00 — Close

**Say:** “BiteDown measures food waste through the outcome recorded when food is removed: used, donated, or thrown out.”

## What is real and what is a fallback

- **Photo detection:** The Gemini fallback (`source: "gemini"`) until the teammate's YOLO lands. "Check again" works the same way.
- **Receipts:** the API reads a receipt photo with Gemini vision (`POST /items/from-receipt`, response `source: "gemini"`); GLM-OCR is not used. The app has no receipt screen yet (Add 2b is not built), so show receipts through the API only, or say the tile is unavailable. Do not describe it as in-app OCR.
- **Barcode scanner:** `DataScannerViewController` doesn't run on the Simulator, so the Simulator uses a DEBUG manual-code field.
- **Google sign-in:** Hidden until the owner's OAuth client id exists.
- **Gemini-generated content:** Recipes, tips' wording and macros are labelled estimates.

## If it breaks

| Symptom | What to say or do |
|---|---|
| Photo suggestions fail to load | Do not present a result as live if it did not load. Check the demo's configured Gemini/API setup with the operator; exact recovery steps: **TODO: confirm**. |
| A photo suggestion or freshness flag looks wrong | Say that photo recognition needs user review and cannot establish food safety. Correct or skip the suggestion rather than claim it is verified. |
| The expiry prediction is missing or unexpected | Say that expiry dates are estimates based on supplied information and category defaults. Correct the suggested date if the screen allows it; otherwise: **TODO: confirm** the recovery step. |
| Receipt scan is unavailable or returns an error | In the app: the receipt tile is unavailable by design today. Through the API: a 502 means Gemini is rate-limited or down; wait a minute and retry once, otherwise move on. Never describe receipts as in-app OCR. |
| Barcode camera does not open in Simulator | Explain that the scanner does not run in Simulator and use the DEBUG manual-code field. |
| Google sign-in is absent | Explain that it is hidden until the OAuth client id exists. Use the prepared email sign-in if available; setup for the demo account: **TODO: confirm**. |
| Impact is not reachable | The handoff says Impact is reachable through a debug launch flag until Home wiring is complete. The exact flag and current build integration: **TODO: confirm**; do not imply the screen is wired if it is not. |
| Undo does not leave Impact unchanged | Do not claim success. Stop and report that the required Undo behavior was not demonstrated; the recovery steps: **TODO: confirm**. |

## Likely questions

1. **How is the expiry date chosen?**  
   It is an estimate based on the supplied information, category defaults, and Gemini inference. The date can be corrected and is not a guarantee about food safety.

2. **Does the photo model identify spoilage?**  
   Photo detection uses the Gemini fallback until the teammate's YOLO lands. Photos cannot establish food safety, and visible-spoilage flags need user review.

3. **Is receipt scanning using GLM-OCR?**  
   No. Receipts are read by Gemini vision through the API; GLM-OCR was evaluated and is deferred. The app's receipt screen is not built yet, so receipts are shown through the API only.

4. **What happens when I donate an item?**  
   A donated outcome counts as food saved. If the item has an open Share listing, the donation fulfils it.

5. **What does “Threw it away” record?**  
   It records the item as food wasted. A waste reason is required for that outcome.

6. **What do the Impact figures mean?**  
   Impact is computed from food events, and its money and CO₂e figures are estimates. They do not prove additional waste was prevented or emissions avoided.

7. **Why does Impact stay the same after Undo?**  
   The project contract requires Undo to leave Impact exactly as it was before the removal. The integrated demo path still needs confirmation.

8. **Are recipes, tips, and macros exact?**  
   Recipes, tip wording, and macros generated by Gemini are labelled estimates. **TODO: confirm** the exact on-screen estimate labels in the current demo build.
