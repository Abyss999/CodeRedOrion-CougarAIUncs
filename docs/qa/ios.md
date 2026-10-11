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

## 2026-10-10: Foundation re-verify (#47)
Head: `b6429df` plus the builder's uncommitted `ios/App` and `project.yml` fixes (IOS-5, 9, 10, 11, the Add `Binding`, `APIDate`, tokens, id renames, BiteDown) plus the QA test edits below. Mac: Apple M4 Pro, Xcode 26.6, XcodeGen 2.45.4, `CODE_SIGNING_ALLOWED=NO`. `xcodegen generate`, then one full `xcodebuild test` per device, run one after the other with no backend suite running.

### Verdict: PASS
| Device | Unit | UI |
|---|---|---|
| iPhone 17 Pro (iOS 26.5), light, `large` | **117 run, 0 failed, 3 skipped** (Keychain, IOS-7 by design) | **24 run, 0 failed**, no expected failures |
| iPhone SE QA (iOS 26.5), **AX5** (`accessibility-extra-extra-extra-large`) | **117 run, 0 failed, 3 skipped** | **24 run, 0 failed**, no expected failures |

The SE was reset to `large` and shut down afterwards. The 17 Pro was left on light / `large`.

### Bug status
| ID | Status | Evidence |
|---|---|---|
| IOS-4 | fixed | `testTabIdentifiersReachTheTabBar_IOS4` is now strict over 3 launches per run: `tab.home`…`tab.social` on every launch, on both devices |
| IOS-5 | fixed | `testInvalidSchemeShowsErrorAndKeepsDefault` (strict, no scrolling): on SE AX5 the error is hittable, under the field and above the keyboard. Before: [se-ax5-ios5-before.png](media/ios-foundation/se-ax5-ios5-before.png). After: [se-ax5-baseurl-error.png](media/ios-foundation/se-ax5-baseurl-error.png) |
| IOS-6 | fixed | `xcodebuild -showBuildSettings` with a temporary `Local.xcconfig` (deleted afterwards): Debug and Release both resolve `API_BASE_URL = https://local-override.example.com`, bundle id `com.qa.test.fwr` |
| IOS-7 | fixed | Test targets have `GENERATE_INFOPLIST_FILE: YES`. `save()` logs `Keychain save failed, OSStatus -34018` and returns false (seen in the unsigned run). The 3 real-Keychain tests still skip unsigned, by design |
| IOS-8 | fixed | `.github/workflows/ios.yml`: `-destination "platform=iOS Simulator,name=$SIM_NAME,OS=26.5"` |
| IOS-9 | fixed | `SkeletonAccessibilityTests` (hosted `SkeletonList`, AX tree on): exactly 1 element, `<screen>.loading`, label "Loading", no per-row ids. `SkeletonRow` uses only Theme tokens (`ThemeTests.testComponentTokens` pins them). No numeric frame, spacing, radius or opacity literals are left in `ios/App` views (grep) |
| IOS-10 | fixed (VoiceOver) | `testTabButtonsHaveNoStrayImageLabels_IOS10`: the button labels are exactly Home, Recipes, Add, Fridge, Social and are queryable by id. Note: XCUITest still lists an image *inside* each button with a symbol label (`home`, `frying.pan.fill`). The button is the VoiceOver element, so that image is not a stop; it is logged, not asserted. No other view uses these SF Symbols, so the shared-image risk does not apply yet |
| IOS-11 | **new, fixed in this round** (medium) | At AX5 the toast kept message and Undo side by side, so on the SE the message broke mid-word ("spinac/h re-/move/d"): [before](media/ios-foundation/se-ax5-toast-before.png). Now stacked: [se-ax5-toast-stacked.png](media/ios-foundation/se-ax5-toast-stacked.png). `testToastMessageIsNotSqueezedAtAX5_IOS11` is strict: Undo below the message, message ≥ 80% of the toast width, Undo ≥ 44 pt, toast above the tab bar |

**CI failure `testAddFromFridgeKeepsFridgeSelected` (macos-26): test flake, not an app bug.** In CI the grabber drag did not dismiss the sheet within 5 s on a slow runner (the drag synthesis alone took 3.3 s), while the same helper passed in the other two Add tests in the same run. Locally it passed 5/5 iterations (`-test-iterations 5`) and in every full run on both devices. Fix in the test: wait for the sheet frame to settle, then drag, retrying up to 3 times. The builder's custom `Binding` (Add never becomes the selection) is in this head and passes too. No IOS id was assigned.

No open iOS bugs from this round. Still open from earlier: IOS-2 (glass tab bar vs artboard; owner).

### Tests changed (`ios/Tests/**`)
- `MotionTests`: stagger cap is now 6 (`testStaggerDelayIs40msPerIndexCappedAtSixItems`: index 5 = 0.2 s, later indexes share it). `testTokenValues` pins every `Theme.Motion` token against `docs/design/MOTION.md`: quick, standard, emphasized, 40 ms / 20 ms chart step, cap 6, 0.3 s item, list insert 8 pt / 0.3 s, pulse 8 pt / 30% / 1.6 s, static ring 4 pt / 25%, shimmer 1.2 s, one-shot 0.5 s. It also pins the builder's pulse line width and shimmer band and highlight. New `testFullStaggerSequenceFitsTheOneShotLimit` (5 × 40 ms + 0.3 s = 0.5 s exactly). The code matches MOTION.md; no discrepancy.
- New `APIDateTests` (15): backend-shaped `Item`, `ItemsResponse`/`SectionsResponse`/`ItemResponse`, `AuthSession.user.created_at` and `Impact.weekly.week` JSON.
  - Strings decoded: `…T12:00:00.123456+00:00`, `…T12:00:00+00:00`, `Z`, `.000Z`, `.123456Z`, and the week as a date or a midnight `+00:00` timestamp.
  - `parse` forms: T/t/space separators, 1-9 digit fractions crossed with Z/`+00:00`/no zone, `±HH:MM` and `±HHMM` (+05:30, +13:45, -05:00), a year rollover, a leap day, and date-only as local midnight in 4 zones.
  - About 45 rejected strings: bare dot, more than 9 digits, bare `+00`, out-of-range fields, bad separators, trailing junk.
  - Encoding: a whole-second `Z` string, and `dayString` at UTC+14.
  - The app has no event model, so "event" coverage is the date fields the app decodes.
- New `SkeletonAccessibilityTests` (3); `ThemeTests` adds `testComponentTokens` and `testDisplayNameIsBiteDown`.
- `BaseURLDebugUITests`: ids renamed to `debug.versionlabel` / `debug.baseurl.*`. The error is queried as the Label's **text** (`app.staticTexts`): SwiftUI puts the id on both the icon and the text. The test asserts strictly that the error is visible without scrolling and clears after a valid save.
- New `MotionUITests` (7), via `-UITestShowToast` and `-UITestReduceMotion`:
  - message, Undo label, a 44 pt target, and the toast above the tab bar
  - Undo calls back (`toast.undo.marker`) and dismisses
  - auto-dismiss: not before 5 s from launch, and gone within 7 s of first sighting, without calling Undo
  - Reduce Motion: the toast appears, Undo works, its frame does not move (a fade, not a slide), and the timeout is unchanged
  - AX5 stacked layout (IOS-11)
- `TabShellUITests`: IOS-4 strict, IOS-10 test, sturdier sheet dismissal. `README.md`: the new ids, launch args, the loading-id rule and the Label id note.

### Motion evidence (iPhone 17 Pro)
- [toast-motion.mp4](media/ios-foundation/toast-motion.mp4) (494 KB, 9.8 s, 440×960, `avconvert` Preset960x540): launch, then the toast with its 5 s progress bar, then it slides away. A frame sheet sampled every 0.5 s shows the toast for about 5 s.
- **No stagger is shown**: no screen in the foundation uses `staggeredAppearance` yet. It is covered by unit tests; record it with the first list screen (Fridge).
- Screenshots: [light](media/ios-foundation/toast-light.png), [dark](media/ios-foundation/toast-dark.png). In dark mode the toast uses the lime surface with dark text and stays legible.
