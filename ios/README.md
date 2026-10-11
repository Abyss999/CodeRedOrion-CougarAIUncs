# iOS app

SwiftUI, deployment target **iOS 18**, built with **Xcode 26** (iOS 26 SDK) so the system `TabView`
renders as the Liquid Glass bar. The project is generated: `cd ios && xcodegen generate`.

## Layout
- `App/Networking`: `APIClient` protocol, `LiveAPIClient`, `MockAPIClient` + `MockFixtures`, Codable `Models`, `AuthStore` (Keychain), `BaseURLProvider`.
- `App/Components`: `FoodGroupIcon`, `ExpiryBadge`, `EmptyStateView` / `ErrorStateView`, `SkeletonRow`, `GroupHeaderText`.
- `App/Support`: `AppEnvironment` (DI, Mock vs Live), `LaunchConfiguration`, `AccessibilityID`, `DebugSettings`, `DebugProbes` (UI-test probes).
- `App/Fridge`: `FridgeView` (Fridge tab), `FridgeModel` (per-storage state, optimistic remove / Undo / rollback), row, group header, storage control, error banner.
- `App/Remove`: `RemoveSheet` (outcome, plus the claimer line), `RemoveReasonView` (waste reason, pushed inside the sheet), tiles.
- `Resources`: `Assets.xcassets` (AccentColor, placeholder AppIcon, food-group glyphs), `Fonts` (Outfit 500/600 + OFL licence).
- `Config/*.xcconfig`: per-configuration settings (`API_BASE_URL`).

## API base URL
Precedence: UserDefaults override (Debug builds only) > Info.plist `API_BASE_URL` (from `Config/Debug.xcconfig`
or `Release.xcconfig`) > `http://127.0.0.1:5055`. Read on every request, no rebuild needed.
For a changing tunnel URL: in a Debug build, **long-press the version label** on the Home tab
(`debug.versionLabel`), paste the https URL, Save. "Reset to default" clears the override.
`NSAllowsLocalNetworking` is in the plist for Debug only (a pre-build script removes it for Release).

## Run on your iPhone (free Personal Team)
1. `cp ios/Local.xcconfig.example ios/Local.xcconfig` (gitignored) and set `DEVELOPMENT_TEAM` and a unique `APP_BUNDLE_ID`.
2. `cd ios && xcodegen generate`, open the project, select your phone, Run. Trust the developer profile on the phone.
3. Point the app at the API: long-press the version label and paste the tunnel URL.
The app uses no capabilities that need a paid team (no push, iCloud or App Groups). CI and Simulator
builds work without `Local.xcconfig` (`CODE_SIGNING_ALLOWED=NO`).

## UI-test launch arguments (parsed in DEBUG builds only)
| Argument | Effect |
|---|---|
| `-UITestMockAPI` | use `MockAPIClient` (in-memory, no network, no Keychain) |
| `-UITestSeed <fixture>` | `fridge` (default, artboard data), `empty`, `expired`, `long` |
| `-UITestSignedIn` | start signed in as Priya |
| `-UITestFailNetwork` | every mock call throws a network error |
| `-UITestSlowNetwork` | every mock call takes 3 s (default 150 ms) |
| `-UITestShowToast` | shows the Undo toast on launch inside the Home tab; tapping Undo shows `toast.undo.marker` |
| `-UITestReduceMotion` | forces Reduce Motion on (root `reduceMotionOverride`; simctl has no switch for it) |
| `-UITestLoadingForever` | the item list never returns (skeleton `fridge.loading` stays up) |
| `-UITestFailList` | only the item list fails (error state); other calls succeed |
| `-UITestFailListOnce` | the first item list call fails, the retry succeeds |
| `-UITestFailRemove` | only `POST /items/:id/remove` fails (row rolls back, `fridge.remove.error` banner) |
| `-UITestFailRestore` | only `POST /items/:id/restore` fails (Undo rolls back, banner) |
| `-UITestSlowRemove` / `-UITestSlowRestore` | that call alone takes 3 s |
| `-UITestRecordHaptics` | records haptics and exposes them on the `debug.haptics` probe |

Seeds: `fridge` (default) is the Fridge artboard: 8 items, all in the fridge (pantry and freezer are empty), covering
fresh, `semi_fresh` (bananas, "Use soon") and spoiled (strawberries, "Check"). `item-spinach` has an open Share listing
claimed by Marcus Ojeda (`user-marcus`), so its sheet shows `remove.recipient`; `item-carrots` has an open listing with
no claimer (no recipient line). `listing` returns the same data. `expired` has past-date items ("Expired"), `empty` has none, `long` has 36 across all 9 groups.
In the mock, a donated removal fulfils the open listing and restore reopens it.

Every flag above except `-UITestShowToast`, `-UITestReduceMotion` and `-UITestRecordHaptics` implies `-UITestMockAPI`. Mock login accepts any credentials except password `wrong-password` (401); signup with `taken@example.com` returns 409 `email_taken`.

## Accessibility identifiers
Convention `screen.element[.id]`, lowercase, defined in `App/Support/AccessibilityID.swift`; tests use the same constants.
- Tabs: `tab.home`, `tab.recipes`, `tab.add`, `tab.fridge`, `tab.social`. Add sheet: `add.sheet`.
- Fridge: `fridge.list`, `fridge.title`, `fridge.storage`, `fridge.storage.<fridge|pantry|freezer>` (selected segment has the `isSelected` trait), `fridge.group.<food_group>`, `fridge.row.<id>` (container), `fridge.row.<id>.badge`, `fridge.row.<id>.remove` (swipe action; may not reach XCUITest, fall back to the "Remove" label), `fridge.remove.error`, `fridge.remove.error.retry`, `fridge.remove.error.dismiss`.
- Remove: `remove.sheet`, `remove.title`, `remove.cancel`, `remove.outcome.used|donated|thrown_out`, `remove.outcome.<raw>.check`, `remove.recipient` (static, non-interactive "Gave it away goes to <claimer>" line; shown only when the open listing has a claimer; the app sends no `recipient_id`, the server credits the claimer).
- Remove reason: tiles `remove.reason.<expired|forgot|didnt_like|other>`; screen `removereason.screen`, `removereason.title`, `removereason.tip`.
- States: `<screen>.empty`, `<screen>.error`, `<screen>.error.retry`, `<screen>.loading`, `<screen>.skeleton.<n>`.
- Debug: `debug.versionLabel`, `debug.settings`, `debug.baseURL.field|save|reset|error|current`.
- Probes (DEBUG, mock launches, on the Fridge tab): `debug.haptics` (label and value = comma-joined events, e.g. `success,warning`; `none` when empty; needs `-UITestRecordHaptics`) and `debug.stagger.count` (stagger restarts; staggers run on a storage's first load only). Content behind an open sheet may be hidden from accessibility, so read probes after it dismisses.

## Motion (docs/design/MOTION.md)
All animation goes through the Reduce Motion choke point; screen code never calls `withAnimation` or `.animation` directly,
and never reads `accessibilityReduceMotion` itself (use `@MotionReduced private var reduceMotion`, which honours `-UITestReduceMotion`).
- Tokens: `Theme.Motion.quick | standard | emphasized`, `staggerStep` (40 ms), `staggerCap` (6; items past the 6th share the 6th's delay, max 0.2 s),
  `chartStaggerStep` (20 ms), `staggerItem` (0.3 s, so a stagger ends by 0.5 s), `listInsert` (0.3 s), `shimmerDuration` (1.2 s), pulse constants.
  `Theme.Motion.animation(_:reduceMotion:)` returns `quick` (0.15 s fade) under Reduce Motion; `transition(_:reduceMotion:)` returns `.opacity`.
- Helpers (`App/Motion`): `withMotion`, `.motionAnimation(_:value:)`, `.motionTransition(_:)`, `.shake(trigger:)`, `.checkmarkScaleIn(_:)`,
  `.numericChange(value:)`, `CountUpText` (MOTION.md: final value immediately under Reduce Motion), `.listInsertTransition()` (new item at the top, down 8 pt + fade).
- Composites animate as one unit: `.staggeredAppearance(index:controller:rise:step:)` composites the view first; `.growsFromBaseline(index:controller:)`
  is one `scaleY` from the bottom (Impact stacked bars). Reduce Motion: 0.15 s fade.
- `ListeningPulse(diameter:)`: 8 pt, 30% peak, 1.6 s loop; static 4 pt ring at 25% under Reduce Motion (id `listening.pulse`).
- Skeletons: `.shimmering()` (1.2 s, static under Reduce Motion). `SkeletonList` is one VoiceOver element "Loading" (`<screen>.loading`, no per-row ids).
- Stagger: keep a `StaggerController`, call `restart()` only on first load or a new result (never on refresh).
- Haptics: `Haptics.success() / warning() / error() / selection() / lightImpact()` via `HapticsProviding` (`SystemHaptics`, `NoOpHaptics`, `RecordingHaptics`). Mock-API launches use `NoOpHaptics`.
- Undo toast: `.undoToast(item: $toast)` with `UndoToastItem(message:actionTitle:onUndo:onTimeout:)`. 5 s (15 s with VoiceOver or Switch Control), progress bar,
  44 pt Undo, VoiceOver announcement. Attach it to the screen content inside a tab, not to the `TabView`. Ids: `toast.undo`, `.message`, `.button`, `.progress`.
- Tab identifiers are installed on the `UITabBarItem`s by `TabBarIdentifiers` (SwiftUI's own identifier was flaky on iOS 26).
