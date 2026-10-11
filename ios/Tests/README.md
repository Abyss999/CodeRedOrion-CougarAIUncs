# iOS tests

`Tests/UnitTests` (XCTest, hosted in the app) and `Tests/UITests` (XCUITest). Both run in CI from
the `FoodWasteReducer` scheme. Screen PRs add tests here; QA owns this folder.

## Run
```
cd ios && xcodegen generate && xcodebuild test -project FoodWasteReducer.xcodeproj \
  -scheme FoodWasteReducer -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  CODE_SIGNING_ALLOWED=NO -derivedDataPath <dir>
```
Add `-only-testing:FoodWasteReducerUITests` (or `FoodWasteReducerTests`) to split. One `xcodebuild`
at a time on the shared Mac (`pgrep -x xcodebuild`); never kill by pattern.

## Accessibility identifiers
- Format `screen.element[.id]`, lowercase, dot separated. Constants live in
  `App/Support/AccessibilityID.swift`; views use them, tests mirror them (UI tests cannot import the
  app module, so `UITestSupport.swift` repeats the strings; keep both in sync).
- Lists: `fridge.row.<item id>`, with children `.remove`, `.badge`. Sections: `fridge.group.<food_group>`.
- States, per screen: `<screen>.empty`, `<screen>.error`, `<screen>.error.retry`, `<screen>.loading`.
  A skeleton list is ONE accessibility element (`<screen>.loading`, label "Loading"); rows have no ids.
- Sheets: `add.sheet`, `remove.sheet`; outcomes `remove.outcome.<api value>`, reasons
  `remove.reason.<api value>`. Toast: `toast.undo`, `toast.undo.button`.
- Put the identifier on the **content element a test acts on**. Check the real element type with
  `app.debugDescription` (the Add sheet's id lands on a `StaticText`; the version label is a `Button`).
  Query with `app.descendants(matching: .any)[id]` when the type can change.
- **Tab bar:** the app installs `tab.<name>` on the `UITabBarItem`s (IOS-4 fix, asserted strictly over
  3 launches). Tests still find tabs by label through `app.tab(ID.x)` (labels are what VoiceOver reads:
  Home, Recipes, Add, Fridge, Social).
- A SwiftUI `Label` with an identifier puts it on both the icon (Image) and the text: query
  `app.staticTexts[id]` (see `app.urlError`).
- Every icon-only control needs an `accessibilityLabel` (tests assert `.label`). Interactive
  elements are at least 44 x 44 pt (tests assert `frame`).

## Launch arguments (DEBUG builds only)
| Argument | Effect |
|---|---|
| `-UITestMockAPI` | `MockAPIClient` instead of `LiveAPIClient`, in-memory session (no Keychain) |
| `-UITestSignedIn` | start signed in as Priya (implies mock) |
| `-UITestSeed <fridge\|empty\|expired\|long>` | mock data set; default `fridge`. Dates are relative to today |
| `-UITestFailNetwork` | every mock call throws a network error (error + retry states) |
| `-UITestSlowNetwork` | every mock call waits 3 s (loading/skeleton states) |
| `-UITestShowToast` | Home shows one Undo toast ("Baby spinach removed"); `toast.undo.marker` appears after Undo |
| `-UITestReduceMotion` | forces Reduce Motion on (simctl has no switch) |
| `-UITestLoadingForever` / `-UITestFailList` / `-UITestFailListOnce` | item list never returns / fails / fails once then Retry succeeds |
| `-UITestFailRemove` / `-UITestFailRestore` | only remove / restore fails (rollback + `fridge.remove.error` banner) |
| `-UITestSlowRemove` / `-UITestSlowRestore` | remove / restore take 3 s |
| `-UITestRecordHaptics` | haptics recorded on the `debug.haptics` probe (comma-joined, "none" when empty); `debug.stagger.count` counts Fridge staggers |
| `-UIPreferredContentSizeCategoryName UICTContentSizeCategoryAccessibilityXXXL` | AX5 text (system, not ours) |

Use `XCUIApplication.mockSignedIn([extra args])` from `UITestSupport.swift`. The base-URL override is
persisted in UserDefaults across launches: reset it through the debug sheet at the start of a test
(never via a `-api_base_url_override` launch argument, which shadows saved values).

## Fridge and remove
Seeds: `fridge` (and `listing`) has item-spinach on an open listing claimed by Marcus Ojeda and
item-carrots on an open listing with no claimer; the pantry is empty. Ids live in `FID` and
`RemoveArgs` (`FridgeUITestSupport.swift`, `RemoveFlowUITests.swift`). The Fridge `List` is lazy and
rows are tall at AX5, so use `app.reveal(element)` (scrolls until the element is hittable **and above
the floating tab bar**: a swipe that starts under the bar drags the bar and switches tabs) and
`openRemove(app, item:)` (a long swipe is a full swipe and opens the sheet directly). Probes behind a
sheet may be hidden from accessibility; read them after the sheet dismisses.

## Debug base URL entry
Long-press the version label on Home (`debug.versionlabel`) to open `debug.settings`: field
`debug.baseurl.field`, `debug.baseurl.save`, `debug.baseurl.reset`, `debug.baseurl.error`,
`debug.baseurl.current` ("In use: ..."). Debug builds only; the Release binary contains none of it.

## Device matrix
| Device | Use |
|---|---|
| iPhone 17 Pro, iOS 26.5, light + dark | default for every test and screenshot |
| iPhone SE (3rd gen), iOS 26.5, AX5 | layout stress. Create once: `xcrun simctl create "iPhone SE QA" com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation com.apple.CoreSimulator.SimRuntime.iOS-26-5`; then `xcrun simctl ui <udid> content_size accessibility-extra-extra-extra-large` and **reset to `large` afterwards** |
Appearance: `xcrun simctl ui <udid> appearance light|dark` (reset to light). `simctl` has no Reduce Motion
switch; use `-UITestReduceMotion` (`MotionUITests`) plus the unit tests of the `Theme.Motion` choke point.

## Every data screen needs
Empty (`ContentUnavailableView`), skeleton shaped like the final layout (not a spinner) and error with
retry, each with a UI test using the launch args above; plus VoiceOver labels, 44 pt targets and an AX5
run on the SE.

## Unit-test notes
- Unsigned builds (CI, `CODE_SIGNING_ALLOWED=NO`) have no Keychain entitlement, so the three real
  Keychain tests `XCTSkip` (IOS-7). Run them signed or ad hoc to cover them.
- `SkeletonAccessibilityTests` hosts a view and turns on the accessibility automation flag
  (`_AXSSetAutomationEnabled`, test target only) so SwiftUI builds its accessibility tree.
- `StubURLProtocol` (in `LiveAPIClientTests.swift`) stubs HTTP for `LiveAPIClient`.
- Expected values for tokens are literals copied from `docs/design/DESIGN_SYSTEM.md`, not read back
  from `Theme.hexTable`.
