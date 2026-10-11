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

## 2026-10-10: foundation PR (`feat/ios-foundation`): iOS 18 + Xcode 26, tokens, APIClient, mock, motion, base URL
Mac: Apple M4 Pro, Xcode 26.6. Simulators: iPhone 17 Pro and a new **iPhone SE (3rd generation) "iPhone SE QA"** (iOS 26.5, `xcrun simctl create`; no runtime downloaded). Tests written while the builder's code landed; the final run is against the tree as of ~21:40.

### Verdict: PASS with open bugs (IOS-4 medium, IOS-5 to IOS-8 low). Motion UI tests are blocked (see "Not testable yet").
| Run | Result |
|---|---|
| Unit tests, iPhone 17 Pro | **96 run, 0 failed, 3 skipped** (the 3 real-Keychain tests, see IOS-7) |
| UI tests, iPhone 17 Pro | **16 run, 0 failed** (11 tab shell, 4 debug base URL, 1 launch) |
| Unit + UI on iPhone SE at AX5 (`accessibility-extra-extra-extra-large`) | unit 87/0 failed (run before MotionTests existed); UI 16 run, **1 failed**: `testInvalidSchemeShowsErrorAndKeepsDefault` (IOS-5). SE reset to `large` and shut down afterwards |
| Release build (`generic/platform=iOS Simulator`) | BUILD SUCCEEDED. The binary has none of `DebugSettingsSheet`, `debug.baseURL`, `api_base_url_override`, `UITestMockAPI` (strings count 0). Built Info.plist has **no** `NSAppTransportSecurity`; `API_BASE_URL` = release value; no entitlements |
| Build without `ios/Local.xcconfig` (the CI case) | works; bundle id `com.coderedorion.FoodWasteReducer` |
| `Local.xcconfig` gitignored | `git check-ignore -v` -> `.gitignore:45:ios/Local.xcconfig`; `Local.xcconfig.example` is not ignored |
| Entitlements | none in the repo or project.yml: no push, iCloud, App Groups or Sign in with Apple |

### Tests added (`ios/Tests/**`)
- `ThemeTests`: `addButton` removed; `useSoonBg/Ink` rows added to the exact light and dark hex table; all 9 food-group stroke/tile pairs in both modes (literals copied from DESIGN_SYSTEM); stroke vs tile >= 3:1; use-soon contrast; radii 14/18/28/20/16/12/10; Outfit-Medium and Outfit-SemiBold resolve with `UIFont(name:)`; `UIAppFonts` lists both files.
- `ExpiryBadgeTests` (11): Today, 1 day, N days, Expired, semi_fresh -> "Use soon" (but Today/Expired outrank it), spoiled -> "Check", nil expiry, across midnight, Honolulu vs Tokyo, DST end, date-only API parsing, accessibility text.
- `ModelsTests` (22): JSON shaped like docs/API.md: snake_case, ISO dates with and without fractions, date-only expiry = local midnight, optional `freshness` and `share`, unknown enums fall back to `other`, extra keys ignored, sections, auth, candidates, impact (empty weekly), recipes with and without macros, tips, the error shape, malformed JSON throws, round trips, encoder omits nil, API raw values.
- `MockAPIClientTests` (15): `group_by=food_group` order and omission of empty sections, expiry sort, storage filter, artboard badges, all four fixtures, remove then restore, API removal validation rules, create and patch, `failNetwork`, `failures[...]`, `failFirst` for retry, signed-out -> unauthorized, login/signup edge cases.
- `LiveAPIClientTests` (10, stub `URLProtocol`): bearer header, default base URL, `group_by` query, **an override is used on the very next request and reset restores the default**, path-prefix override, 401 signs out, login 401 does not, error shape mapping, non-JSON 5xx, decoding error.
- `BaseURLProviderTests` (11): precedence override > Info.plist > `http://127.0.0.1:5055`, validation (http/https only, rejects ftp/file/javascript/no host/query/fragment), trimming, rejected input is not stored, corrupt stored value ignored.
- `AuthStoreTests` (4): Keychain save/load/clear, isolation, store persistence across instances, in-memory path never touches the Keychain. **3 skip in unsigned runs.**
- `MotionTests` (9): exact token values, Reduce Motion returns `quick` for every animation, stagger 40 ms capped at 8 (and clamps below 0), `StaggerController` inactive until `restart()`, haptics provider records, toast constants, **a hosted `UndoToastView` auto-dismisses after about 5 s without calling Undo**.
- UI `TabShellUITests` (11): 5 tabs, order and VoiceOver labels (Home, Recipes, Add, Fridge, Social), Home selected at launch, tabs select, each tab >= 44 x 44 pt, **Add presents the sheet and the selected tab is unchanged after dismissing** (from Home, from Fridge, 3 times from Social, Add never selected), AX5 tabs hittable, screenshots attached. `BaseURLDebugUITests` (4): save a valid override and reset, invalid scheme shows an error, override persists across relaunch until reset, version label. `ios/Tests/README.md` documents the ID convention, launch args and device matrix.

### Screenshots (iPhone 17 Pro, 603 px)
[tab bar light](ios/foundation-tabbar-light.png), [tab bar dark](ios/foundation-tabbar-dark.png), [Add sheet light](ios/foundation-add-sheet-light.png), [Add sheet dark](ios/foundation-add-sheet-dark.png).
- Native glass `TabView`, 5 tabs in the order Home, Recipes, Add, Fridge, Social; Add is a filled circle-plus regular tab, no raised button. Selected Home shows the forest tint in light and the lime-family tint in dark, in a selection capsule. This matches the DESIGN_SYSTEM "Tab bar on iOS 26" spec (system `TabView`, forest tint, Add is a tab). Inactive tabs use the system label colour, accepted (IOS-3 won't-fix).
- Artboard (Home.dc.html) comparison: the artboard draws an approximation (flat pill); the system glass differs in material and icon weight by design. No defect.
- The Add placeholder sheet has a medium detent, 28 pt top corners (spec), grabber, the page ground colour and the word "Add"; Home stays selected behind it. Placeholder only; the AddSheet design is not built.

### CI review (`ios.yml`)
- `runs-on: macos-26` and `/Applications/Xcode_26.6.app` **exist** (runner-images `macos-26-arm64-Readme.md`: 26.6 is the default, with 26.0.1 to 26.5; simulators 26.2, 26.4, 26.5; iPhone 17 Pro on all).
- `macos-15` would also work only with a pin to Xcode 26.0.1 to 26.3 and has iOS 26.0 to 26.2 runtimes; the earlier workflow (default Xcode 16.4, first iPhone found) could not have built the iOS 26 SDK target.
- UI tests are included: the scheme tests both `FoodWasteReducerTests` and `FoodWasteReducerUITests`, so `xcodebuild test` runs them (about 3 min locally).
- Destination is pinned by name only (`iPhone 17 Pro`). The runner has this model on three runtimes, so add `,OS=26.5` for a deterministic choice (IOS-8).

### Bugs
| ID | Severity | Summary | Status |
|---|---|---|---|
| IOS-3 | low | System inactive tab colour under glass | closed, won't fix (owner) |
| IOS-4 | medium | `.accessibilityIdentifier` on `Tab` reaches the tab bar buttons only intermittently on iOS 26.5: in 5 launches the 5 identifiers were empty in 4, present in 1 (also seen across test runs). Repro: `-UITestMockAPI -UITestSignedIn`, read `app.tabBars.firstMatch.buttons.allElementsBoundByIndex.map(\.identifier)`. Tests find tabs by label; `testTabIdentifiersReachTheTabBar_IOS4` is a non-strict expected failure. Builder: find a reliable route (e.g. identifier on the tab content root as a second hook, or drive tests by label permanently) | open |
| IOS-5 | low | Debug settings sheet at AX5 on iPhone SE: after Save with `ftp://...` the error text `debug.baseURL.error` is not found, even after scrolling (keyboard plus large text push it off screen; sheet has no `scrollDismissesKeyboard` or placing the error above the field). Debug-only. Fails only on SE AX5 | open |
| IOS-6 | medium | `ios/Local.xcconfig` cannot override `API_BASE_URL`. `Debug.xcconfig` and `Release.xcconfig` include `Base.xcconfig` (which includes Local) and then assign `API_BASE_URL` afterwards, so the Local value loses. Verified with `xcodebuild -showBuildSettings`: with `Local.xcconfig` setting `API_BASE_URL=https://local-override.example.com`, Debug = `http://127.0.0.1:5055`, Release = `https://api.foodwastereducer.example`. `APP_BUNDLE_ID` and `DEVELOPMENT_TEAM` do work (bundle id became `com.qa.test.fwr`). The `.example` advertises the override. Fix: include Local last in Debug and Release | open |
| IOS-7 | low | `KeychainSessionStorage` fails in unsigned builds: `SecItemAdd` returns -34018 (errSecMissingEntitlement) under `CODE_SIGNING_ALLOWED=NO`, and `save()` ignores the status, so a sign-in is silently not persisted. Unit tests skip (3). Also: signed test runs fail to build (`Cannot code sign because the target does not have an Info.plist file`) for `FoodWasteReducerTests` and `FoodWasteReducerUITests`; add `GENERATE_INFOPLIST_FILE: YES` to those targets, otherwise the owner cannot run tests with Personal Team signing | open |
| IOS-8 | low | CI destination has no `OS=`; add `,OS=26.5` | open |
| IOS-9 | low | Skeleton: `SkeletonRow` uses ad-hoc radii 12 and 4 and bar sizes (CLAUDE.md: no ad-hoc values); each row is a separate "Loading" VoiceOver stop (5 per list). Group them into one element | open |
| IOS-10 | low | The tab image's own accessibility label is lowercase and odd (`home`, `add`) inside buttons labelled Home/Add. The button label is correct, so VoiceOver reads the button | open, cosmetic |

### Not testable yet (blocked on builder, no code path exists)
- **Undo toast UI tests** (appears, tap calls back, auto-dismiss in the UI, VoiceOver label, 44 pt target, `toast.undo` ids): nothing presents `.undoToast` and there is no debug or launch-arg hook. Request: a DEBUG hook, e.g. long-press or a launch arg `-UITestShowToast` that shows one `UndoToastItem`. Covered meanwhile: unit test of the 5 s timeout; the code sets a 44 pt min height, `toast.undo.button`, an Undo accessibility action and an announcement; the toast stays 15 s under VoiceOver/Switch Control (a sensible HIG addition, to be recorded in MOTION.md).
- **Reduce Motion on/off in UI tests**: `simctl ui` on this Xcode only supports `appearance`, `increase_contrast`, `content_size`; the builder added no launch argument. Covered by unit tests of `Theme.Motion.animation(_:reduceMotion:)`. Request: a DEBUG launch arg that forces `\.accessibilityReduceMotion`.
- **Shimmer and toast video clip** (`docs/qa/ios/`): no screen shows `SkeletonList` and no hook shows the toast, so there is nothing to record. To do when a screen or hook exists. `docs/design/MOTION.md` is not in this worktree, so token values were checked against the coordinator's numbers; re-check against the file once present.
- Food-group glyph assets (Grains/Pantry swap): no view renders them yet.
