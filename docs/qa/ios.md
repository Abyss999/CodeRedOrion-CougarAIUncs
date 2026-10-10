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
