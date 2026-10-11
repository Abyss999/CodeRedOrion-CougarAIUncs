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
- States, per screen: `<screen>.empty`, `<screen>.error`, `<screen>.error.retry`,
  `<screen>.loading`, `<screen>.skeleton.<n>`.
- Sheets: `add.sheet`, `remove.sheet`; outcomes `remove.outcome.<api value>`, reasons
  `remove.reason.<api value>`. Toast: `toast.undo`, `toast.undo.button`.
- Put the identifier on the **content element a test acts on**. Check the real element type with
  `app.debugDescription` (the Add sheet's id lands on a `StaticText`; the version label is a `Button`).
  Query with `app.descendants(matching: .any)[id]` when the type can change.
- **Tab bar:** identifiers set with `.accessibilityIdentifier` on `Tab` reach the tab bar buttons only
  intermittently on iOS 26.5 (IOS-4). Until fixed, tests find tabs by label through `app.tab(ID.x)`
  (labels are what VoiceOver reads: Home, Recipes, Add, Fridge, Social).
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
| `-UIPreferredContentSizeCategoryName UICTContentSizeCategoryAccessibilityXXXL` | AX5 text (system, not ours) |

Use `XCUIApplication.mockSignedIn([extra args])` from `UITestSupport.swift`. The base-URL override is
persisted in UserDefaults across launches: reset it through the debug sheet at the start of a test
(never via a `-api_base_url_override` launch argument, which shadows saved values).

## Debug base URL entry
Long-press the version label on Home (`debug.versionLabel`) to open `debug.settings`: field
`debug.baseURL.field`, `debug.baseURL.save`, `debug.baseURL.reset`, `debug.baseURL.error`,
`debug.baseURL.current` ("In use: ..."). Debug builds only; the Release binary contains none of it.

## Device matrix
| Device | Use |
|---|---|
| iPhone 17 Pro, iOS 26.5, light + dark | default for every test and screenshot |
| iPhone SE (3rd gen), iOS 26.5, AX5 | layout stress. Create once: `xcrun simctl create "iPhone SE QA" com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation com.apple.CoreSimulator.SimRuntime.iOS-26-5`; then `xcrun simctl ui <udid> content_size accessibility-extra-extra-extra-large` and **reset to `large` afterwards** |
Appearance: `xcrun simctl ui <udid> appearance light|dark` (reset to light). `simctl` has no Reduce Motion
switch; Reduce Motion is covered by unit tests of the `Theme.Motion` choke point.

## Every data screen needs
Empty (`ContentUnavailableView`), skeleton shaped like the final layout (not a spinner) and error with
retry, each with a UI test using the launch args above; plus VoiceOver labels, 44 pt targets and an AX5
run on the SE.

## Unit-test notes
- Unsigned builds (CI, `CODE_SIGNING_ALLOWED=NO`) have no Keychain entitlement, so the three real
  Keychain tests `XCTSkip` (IOS-4b). Run them signed or ad hoc to cover them.
- `StubURLProtocol` (in `LiveAPIClientTests.swift`) stubs HTTP for `LiveAPIClient`.
- Expected values for tokens are literals copied from `docs/design/DESIGN_SYSTEM.md`, not read back
  from `Theme.hexTable`.
