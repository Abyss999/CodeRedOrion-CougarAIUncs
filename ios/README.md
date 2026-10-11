# iOS app

SwiftUI, deployment target **iOS 18**, built with **Xcode 26** (iOS 26 SDK) so the system `TabView`
renders as the Liquid Glass bar. The project is generated: `cd ios && xcodegen generate`.

## Layout
- `App/Networking`: `APIClient` protocol, `LiveAPIClient`, `MockAPIClient` + `MockFixtures`, Codable `Models`, `AuthStore` (Keychain), `BaseURLProvider`.
- `App/Components`: `FoodGroupIcon`, `ExpiryBadge`, `EmptyStateView` / `ErrorStateView`, `SkeletonRow`, `GroupHeaderText`.
- `App/Support`: `AppEnvironment` (DI, Mock vs Live), `LaunchConfiguration`, `AccessibilityID`, `DebugSettings`.
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
Seed, signed-in, fail and slow imply `-UITestMockAPI`. Mock login accepts any credentials except password `wrong-password` (401); signup with `taken@example.com` returns 409 `email_taken`.

## Accessibility identifiers
Convention `screen.element[.id]`, lowercase, defined in `App/Support/AccessibilityID.swift`; tests use the same constants.
- Tabs: `tab.home`, `tab.recipes`, `tab.add`, `tab.fridge`, `tab.social`. Add sheet: `add.sheet`.
- Fridge: `fridge.list`, `fridge.storage`, `fridge.storage.<fridge|pantry|freezer>`, `fridge.group.<food_group>`, `fridge.row.<id>`, `fridge.row.<id>.remove`, `fridge.row.<id>.badge`.
- Remove: `remove.sheet`, `remove.outcome.used|donated|thrown_out`, `remove.reason.<expired|forgot|didnt_like|other>`.
- States: `<screen>.empty`, `<screen>.error`, `<screen>.error.retry`, `<screen>.loading`, `<screen>.skeleton.<n>`.
- Debug: `debug.versionLabel`, `debug.settings`, `debug.baseURL.field|save|reset|error|current`.

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
