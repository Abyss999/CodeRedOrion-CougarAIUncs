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
    }

    enum Add {
        static let sheet = "add.sheet"
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
        /// Static "Gave it away goes to <claimer>" line, shown only when the open listing has a claimer.
        static let recipient = "remove.recipient"
        /// Checkmark that scales in on the tapped tile.
        static func checkmark(_ rawValue: String) -> String { "remove.outcome.\(rawValue).check" }
    }

    /// The waste-reason step (pushed inside the remove sheet). Tiles use `Remove.reason(_:)`.
    enum RemoveReason {
        static let screen = "removereason.screen"
        static let title = "removereason.title"
        static let tip = "removereason.tip"
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
