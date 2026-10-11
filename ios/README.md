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
Seed, signed-in, fail and slow imply `-UITestMockAPI`. Mock login accepts any credentials except password `wrong-password` (401); signup with `taken@example.com` returns 409 `email_taken`.

## Accessibility identifiers
Convention `screen.element[.id]`, lowercase, defined in `App/Support/AccessibilityID.swift`; tests use the same constants.
- Tabs: `tab.home`, `tab.recipes`, `tab.add`, `tab.fridge`, `tab.social`. Add sheet: `add.sheet`.
- Fridge: `fridge.list`, `fridge.storage`, `fridge.storage.<fridge|pantry|freezer>`, `fridge.group.<food_group>`, `fridge.row.<id>`, `fridge.row.<id>.remove`, `fridge.row.<id>.badge`.
- Remove: `remove.sheet`, `remove.outcome.used|donated|thrown_out`, `remove.reason.<expired|forgot|didnt_like|other>`.
- States: `<screen>.empty`, `<screen>.error`, `<screen>.error.retry`, `<screen>.loading`, `<screen>.skeleton.<n>`.
- Debug: `debug.versionLabel`, `debug.settings`, `debug.baseURL.field|save|reset|error|current`.

## Motion (docs/design/MOTION.md)
All animation goes through the Reduce Motion choke point; screen code never calls `withAnimation` or `.animation` directly.
- Tokens: `Theme.Motion.quick | standard | emphasized`, `staggerStep` (40 ms), `staggerCap` (8), `shimmerDuration` (1.2 s), `staggerDelay(index:)`.
  `Theme.Motion.animation(_:reduceMotion:)` returns `quick` under Reduce Motion; `Theme.Motion.transition(_:reduceMotion:)` returns `.opacity`.
- Helpers (`App/Motion`): `withMotion(_:reduceMotion:_:)`, `.motionAnimation(_:value:)`, `.motionTransition(_:)`, `.shake(trigger:)`
  (3 x 6 pt in 0.3 s, opacity dip under Reduce Motion), `.checkmarkScaleIn(_:)`, `.numericChange(value:)`, `CountUpText(value:format:)` (jumps to the final value under Reduce Motion).
- Skeletons: `.shimmering()` (1.2 s linear sweep, static under Reduce Motion) is built into `SkeletonRow` / `SkeletonList`.
- Stagger: keep a `StaggerController`, call `restart()` only on first load or a new result (never on refresh), and put
  `.staggeredAppearance(index:controller:rise:)` on rows. Rows appearing outside the window just appear.
- Haptics: `Haptics.success() / warning() / error() / selection() / lightImpact()` via a `HapticsProviding` provider
  (`SystemHaptics`, `NoOpHaptics`, `RecordingHaptics` for unit tests). Mock-API launches use `NoOpHaptics`. Unaffected by Reduce Motion.
- Undo toast: `.undoToast(item: $toast)` with `UndoToastItem(message:actionTitle:onUndo:onTimeout:)`. 5 s (15 s while VoiceOver or Switch Control is on),
  progress bar, 44 pt Undo button, posts a VoiceOver announcement. Attach it to the screen content inside a tab, not to the `TabView`
  (it would cover the tab bar). Ids: `toast.undo`, `toast.undo.message`, `toast.undo.button`, `toast.undo.progress` (progress is hidden from VoiceOver).
