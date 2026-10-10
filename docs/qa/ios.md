# iOS QA log

## 2026-10-10: first build (tab shell + `Theme.swift`)
Mac: Apple M4 Pro, macOS 26.5.1, Xcode 26.6, XcodeGen 2.45.4. Simulator: iPhone 17 Pro, iOS 26.5.

| Check | Result |
|---|---|
| `xcodegen generate` | ok |
| `xcodebuild test` (`CODE_SIGNING_ALLOWED=NO`) | **TEST SUCCEEDED**. 0 errors, no compile fixes needed. `ThemeTests` 2/2, `LaunchUITests` 1/1 |
| CI `ios.yml` (macos-15) | pass, see PR #9 |
| 5 tabs: Home, Recipes, Add, Fridge, Social | yes |
| Selected-tab tint is forest `#1F4D2B` | yes. Sampled `#154321` in the screenshot: the iOS 26 Liquid Glass selected pill darkens it slightly. The other tabs render in system label color |
| Dynamic Type, AX5 (`accessibility-extra-extra-extra-large`) | Body text scales. The tab bar labels stay fixed size, which is standard iOS behaviour (long-press shows the large content viewer). No clipping |
| Dark mode | Renders on system black with a dark glass tab bar. **The forest tint is barely visible on black** (see IOS-1). No dark tokens exist yet |

Screenshots, downscaled to 603 px wide: [light](ios/first-build-light.png), [dark](ios/first-build-dark.png),
[light AX5](ios/first-build-light-ax5.png), [dark AX5](ios/first-build-dark-ax5.png).

Not compared against `docs/design/screens/`: the shell has placeholder `Text` views only and no designed screen yet.

### Bugs
| ID | Severity | Summary | Status |
|---|---|---|---|
| IOS-1 | medium | Dark mode: the selected tab in forest `#1F4D2B` on the dark glass bar has very low contrast. It needs a dark variant of `forest` (or of an accent token) in `DESIGN_SYSTEM.md` and `Theme.swift` | open |
| IOS-2 | low | The tab bar is the iOS 26 Liquid Glass floating pill. Check that it matches the design's tab bar artboards when the design is approved | open |

## 2026-10-10: adaptive dark theme (branch `feat/ios-dark-theme`)
Mac: Apple M4 Pro, Xcode 26.6, simulator iPhone 17 Pro (iOS 26.5). Builder's `Theme.swift` was already adaptive (`Color(light:dark:)` backed by a `UIColor` trait provider) when QA ran.

### Tests added (`ios/Tests/UnitTests/ThemeTests.swift`)
Each test resolves `UIColor(Theme.Colors.X).resolvedColor(with: UITraitCollection(userInterfaceStyle:))`, converts to sRGB 8-bit hex, and compares with the Dark mode table in `DESIGN_SYSTEM.md`:
- `testEveryTokenMatchesLightValue` and `testEveryTokenMatchesDarkValue` cover all 22 tokens (ground through chartWasted).
- `testTokensDifferBetweenLightAndDarkExceptLime`: every token differs between modes; `lime` is identical.
- `testSelectedTabTintIsVisibleOnDarkGround`: forest vs ground in dark must be at least 7:1 (regression for IOS-1).
`scrim` has no table row, so it is not asserted.

### Results
| Check | Result |
|---|---|
| `xcodegen generate` + `xcodebuild test` (`CODE_SIGNING_ALLOWED=NO`) | **TEST SUCCEEDED**, 0 errors. `ThemeTests` 6/6, `LaunchUITests` 1/1. No failures |
| Light screenshot | ground `#F4F8E8`, selected tab dark forest, as before |
| Dark screenshot | ground `#0F1A12` (sampled 15,26,18). Selected Home icon and label render lime. Sampled icon pixel `#D3F78C` (211,247,140), brighter than the `#B9D871` token because the Liquid Glass selection applies vibrancy. Clearly visible against the pill (about 52,61,54) and the bar. Contrast is high |
| Appearance reset to light | done |

Screenshots (603 px wide): [light](ios/dark-theme-light.png), [dark](ios/dark-theme-dark.png).

### Verdict: PASS. IOS-1 is closed.
The selected-tab tint is now clearly visible in dark mode.

### New bugs
| ID | Severity | Summary | Status |
|---|---|---|---|
| IOS-3 | low | Placeholder tab content ("Home") and the inactive tab icons use the system label color (white/black), not `Theme.Colors.ink` or `tabInactive`. Not visible as a defect yet, but the tokens are unused in the shell. Revisit when real screens land | open |
