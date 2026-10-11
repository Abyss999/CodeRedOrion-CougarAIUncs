# Motion

Animation rules for the iOS app. The motion is calm and quick. It exists to confirm an action, show
where something went, or show that the app is working, and never as decoration. Native
transitions (sheets, push, tab switch, swipe actions) stay native and aren't restyled.

## Tokens (`Theme.Motion`)
| Token | SwiftUI | Use |
|---|---|---|
| `quick` | `.easeOut(duration: 0.15)` | Taps, toggles, checkbox and colour changes |
| `standard` | `.spring(response: 0.35, dampingFraction: 0.85)` | Rows inserting or removing, expanding, layout changes |
| `emphasized` | `.spring(response: 0.5, dampingFraction: 0.75)` | One moment per screen at most: a success, or a new note landing |
| `stagger` | 40 ms per list item (20–30 ms for chart columns), **capped at 6 items**: 5 × 40 ms of delay + a 0.3 s item = 0.5 s. Items past the 6th appear with the 6th | Lists appearing on first load or from a result |
| `shimmer` | 1.2 s linear, repeating | Skeleton loading only |

- **The whole sequence finishes within 0.5 s, stagger delays included.** Shorten the per-item duration (0.3–0.35 s) or the stagger to fit. Only loading indicators and the listening pulse loop.
- **Animate a composite as one unit.** A stacked bar grows as one element, never segment by segment, because separate segments come apart mid-animation. Value labels appear only once the shape they describe has arrived.
- Numbers that change use `.contentTransition(.numericText())`.
- **Haptics** pair with motion:
  - `.success`: add confirmed, remove confirmed, claim, "I made this".
  - `.selection`: steppers, segmented controls, outcome tiles.
  - `.warning`: "Threw it away".
  - `.error`: any failed key action (a sign-in error, a failed remove, add or claim).

## Reduce Motion (required)
When `accessibilityReduceMotion` is on, the elements still appear with a short fade. Don't skip the animation outright, and nothing may stay invisible:
- Moves, scales, rotations, shakes and shimmer become **opacity fades** (`quick`).
- Count-ups set the final value immediately.
- The listening pulse becomes a **static 4 pt ring at 25% opacity**, so listening is still visible. Skeleton shimmer becomes a static skeleton.
- Haptics and colour and state changes stay, so no information is lost.

iOS QA tests every flow with Reduce Motion on and off.

## By screen
| Screen | Animation | Token |
|---|---|---|
| **All data screens** | Skeleton rows shimmer while loading, then cross-fade to content. Empty and error states fade in | `shimmer`, `quick` |
| **Fridge** | After a removal, the row collapses (height + fade) at the tap, behind the sheet. The request has already fired, and the sheet holds 200 ms so the checkmark is seen. An **Undo toast** slides up from the bottom with a 5 s progress bar, then slides away | `standard` |
| | First load of a section: rows stagger in. Not repeated on every refresh | `stagger` |
| **Remove: outcome** | The tapped tile gets a checkmark scale-in (0.8 → 1) plus haptic, then the sheet dismisses. "Threw it away" pushes to the reason step natively | `quick`, then native |
| **Remove: reason** | The tapped reason tile highlights, then dismisses. Haptic `.warning` | `quick` |
| **Photo review** | Detection boxes draw onto the photo (stroke trim 0 → 1, 0.4 s). Candidate rows stagger in as results arrive. Ticking a box uses a symbol effect. The "Add N items" count uses numeric text | `stagger`, `quick` |
| **Type or say it** | While listening, the mic has a **soft pulsing ring**: up to 8 pt, peak 30% opacity, a 1.6 s period (0.6 Hz, far below flash thresholds). Each understood item inserts **at the top**, moving down 8 pt and fading in over 0.3 s | loop, `standard` |
| **Barcode** | Scan-frame corners breathe gently while searching. On detection the frame snaps to the code, turns `lime`, haptic success, and the result sheet rises | `emphasized` |
| **Receipt review** | Lines stagger in. Unticking a line updates the "Add N items" count with numeric text | `stagger` |
| **Item detail** | Edited values cross-fade. Turning on Share expands the audience row | `quick`, `standard` |
| **Home** | "kg saved" pill uses numeric text when it changes. "Use these first" staggers in on first load | `stagger` |
| **Impact** | The hero card fades in (0.25 s) and its CO₂e number counts up. After 100 ms, each week's **whole stacked bar** grows from the baseline as one unit (0.3 s, 20 ms stagger, ending by 0.5 s). Week labels fade in once the bars land. On a range change, bar heights spring to their new values and the count-up reruns. Nothing else on the screen animates at the same time | `quick`, `standard` |
| **Recipes** | The refresh icon rotates while suggestions load. Cards fade and rise 8 pt in | `standard` |
| **Recipe detail** | **"I made this":** ingredient chips check off one by one (60 ms apart), then a success toast ("3 items marked used · +1.2 kg saved") with Undo | `stagger`, `emphasized` |
| **Social** | Sticky notes **drop in** (12 pt, 0.35 s, 50 ms stagger) and settle onto their own slight tilt on first load. A newly posted note lands at the top. "I have it" cross-fades the note to "Fulfilled". The Food Pantry widget expands in place | `emphasized`, `standard` |
| **Food Pantry** | Claim → "Claimed" with a checkmark symbol, haptic success | `quick` |
| **Ask for something** | Character counter uses numeric text. Post dismisses the sheet, then the note lands on the board | `emphasized` |
| **Friends & groups** | Accepting a request slides the row out and the friend count ticks up | `standard` |
| **Group** | "Share invite" opens the system share sheet. Copying the code shows a "Copied" toast | `quick` |
| **Sign up / Log in** | A wrong password shakes the field 3 × 6 pt over 0.3 s, with haptic `.error`. Buttons show inline progress while signing in. On success, cross-fade into the tab bar | `quick` |
| **Settings** | None beyond native. Delete account uses a native confirmation alert | n/a |

## Don'ts
- Don't animate on every data refresh. Staggers run on **first load** or a **new result** only.
- No parallax, no bouncing icons, no confetti, no auto-playing loops except loading and listening.
- Never delay an action for an animation. The tap takes effect immediately and the motion confirms it.
- Don't animate text people are reading. Animate containers, not paragraphs.

The canvas demonstrates a few of these live: the listening pulse and staggered results on
"Type or say it", the bar grow on Impact, and the note drop on Social. **They were QA-tested
frame by frame** in headless Chrome, with Reduce Motion on and off. The tests checked end states,
timings, clipping and taste, and the values above are the tuned results. The canvas follows
`prefers-reduced-motion` the same way the app must: with fades, not by skipping animation.
