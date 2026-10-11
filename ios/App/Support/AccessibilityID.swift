import Foundation

/// Accessibility identifiers, convention `screen.element[.id]` (lowercase, dot separated).
/// Views set these with `.accessibilityIdentifier(...)`; UI tests query the same constants.
/// Full list and rules: ios/README.md.
enum AccessibilityID {
    enum Tab {
        static let home = "tab.home"
        static let recipes = "tab.recipes"
        static let add = "tab.add"
        static let fridge = "tab.fridge"
        static let social = "tab.social"
    }

    enum Fridge {
        static let screen = "fridge"
        static let title = "fridge.title"
        static let list = "fridge.list"
        static let storage = "fridge.storage"            // segmented control
        static func storageOption(_ s: String) -> String { "fridge.storage.\(s)" }  // fridge|pantry|freezer
        static func group(_ foodGroup: String) -> String { "fridge.group.\(foodGroup)" }
        static func row(_ id: String) -> String { "fridge.row.\(id)" }
        static func rowRemove(_ id: String) -> String { "fridge.row.\(id).remove" }
        static func rowBadge(_ id: String) -> String { "fridge.row.\(id).badge" }
        /// Rollback / refresh error banner, with its retry and dismiss buttons.
        static let removeError = "fridge.remove.error"
        static let removeErrorRetry = "fridge.remove.error.retry"
        static let removeErrorDismiss = "fridge.remove.error.dismiss"
        /// Header "Select" text button (enters select mode) and, in select mode, "Done" and the "N selected" status.
        static let select = "fridge.select"
        static let selectDone = "fridge.select.done"
        static let selectCount = "fridge.select.count"
        /// Select-mode row (one checkbox button per item).
        static func rowSelect(_ id: String) -> String { "fridge.row.\(id).select" }
        /// Select-mode bottom bar and its two actions.
        static let selectBar = "fridge.select.bar"
        static let selectUsed = "fridge.select.used"
        static let selectShared = "fridge.select.shared"
        /// Empty state "Add food" button (the empty state itself is `fridge.empty`).
        static let emptyAdd = "fridge.empty.add"
    }

    enum Add {
        static let sheet = "add.sheet"
    }

    // Namespaces for the upcoming screens. Each PR adds its element ids inside its own enum
    // (convention `screen.element[.id]`); `screen` is the screen's root id.
    enum Home { static let screen = "home" }
    enum PhotoReview { static let screen = "photoreview" }
    enum ItemDetail { static let screen = "itemdetail" }
    enum Impact { static let screen = "impact" }
    enum Recipes { static let screen = "recipes" }
    enum Social { static let screen = "social" }
    enum Auth { static let screen = "auth" }
    enum Settings { static let screen = "settings" }

    // Shared components. Per-instance ids (banner, form field) are passed in by the owning screen.
    enum Permission {
        /// `kind` is a `PermissionKind` raw value: camera | microphone | speech.
        static func card(_ kind: String) -> String { "permission.\(kind)" }
        static func openSettings(_ kind: String) -> String { "permission.\(kind).settings" }
        static func alternative(_ kind: String) -> String { "permission.\(kind).alternative" }
    }

    enum Audience {
        static let list = "audience.list"
        static let friends = "audience.friends"
        static func group(_ id: String) -> String { "audience.group.\(id)" }
        static let hint = "audience.hint"
    }

    enum Remove {
        static let sheet = "remove.sheet"
        static let outcomeUsed = "remove.outcome.used"
        static let outcomeDonated = "remove.outcome.donated"
        static let outcomeThrownOut = "remove.outcome.thrown_out"
        static func outcome(_ rawValue: String) -> String { "remove.outcome.\(rawValue)" }
        /// `reason` is the API value: expired | forgot | didnt_like | other.
        static func reason(_ rawValue: String) -> String { "remove.reason.\(rawValue)" }
        static let title = "remove.title"
        static let cancel = "remove.cancel"
        /// "Given to" row (shown once "Shared it" is selected), its menu button and the Done button.
        static let given = "remove.given"
        static let givenMenu = "remove.given.menu"
        static let done = "remove.done"
        /// Expiry badge in the sheet header, and the Food Pantry badge on the icon tile (listed items only).
        static let badge = "remove.badge"
        static let listingBadge = "remove.listing"
        /// Checkmark that scales in on the tapped tile.
        static func checkmark(_ rawValue: String) -> String { "remove.outcome.\(rawValue).check" }
    }

    /// The waste-reason step (pushed inside the remove sheet). Tiles use `Remove.reason(_:)`.
    enum RemoveReason {
        static let screen = "removereason.screen"
        static let title = "removereason.title"
        static let tip = "removereason.tip"
        /// The grouped list of reasons (rows use `Remove.reason(_:)`).
        static let list = "removereason.list"
    }

    /// Shared states (empty, error, loading). `screen` is the owning screen, e.g. "fridge".
    enum State {
        static func empty(_ screen: String) -> String { "\(screen).empty" }
        static func error(_ screen: String) -> String { "\(screen).error" }
        static func retry(_ screen: String) -> String { "\(screen).error.retry" }
        static func loading(_ screen: String) -> String { "\(screen).loading" }
        static func skeletonRow(_ screen: String, _ index: Int) -> String { "\(screen).skeleton.\(index)" }
    }

    enum Toast {
        static let container = "toast.undo"
        static let button = "toast.undo.button"
        static let message = "toast.undo.message"
        static let progress = "toast.undo.progress"
        /// Debug hook (`-UITestShowToast`): appears after Undo is tapped.
        static let marker = "toast.undo.marker"
    }

    enum Listening {
        /// Pulse ring around the mic while listening (present only while shown).
        static let pulse = "listening.pulse"
    }

    /// DEBUG-only probes for UI tests (mock launches only).
    enum Probe {
        /// Label/value: comma-joined haptic events (`-UITestRecordHaptics`), e.g. "success,warning".
        static let haptics = "debug.haptics"
        /// Label/value: how many times the Fridge stagger has restarted.
        static let staggerCount = "debug.stagger.count"
    }

    /// Debug-only runtime API base URL entry point (long-press the version label).
    enum Debug {
        static let versionLabel = "debug.versionlabel"
        static let settingsSheet = "debug.settings"
        static let baseURLField = "debug.baseurl.field"
        static let baseURLSave = "debug.baseurl.save"
        static let baseURLReset = "debug.baseurl.reset"
        static let baseURLError = "debug.baseurl.error"
        static let baseURLCurrent = "debug.baseurl.current"
    }
}
