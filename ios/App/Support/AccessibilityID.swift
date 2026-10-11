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
        static let list = "fridge.list"
        static let storage = "fridge.storage"            // segmented control
        static func storageOption(_ s: String) -> String { "fridge.storage.\(s)" }  // fridge|pantry|freezer
        static func group(_ foodGroup: String) -> String { "fridge.group.\(foodGroup)" }
        static func row(_ id: String) -> String { "fridge.row.\(id)" }
        static func rowRemove(_ id: String) -> String { "fridge.row.\(id).remove" }
        static func rowBadge(_ id: String) -> String { "fridge.row.\(id).badge" }
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
    }

    /// Shared states (empty, error, loading). `screen` is the owning screen, e.g. "fridge".
    enum State {
        static func empty(_ screen: String) -> String { "\(screen).empty" }
        static func error(_ screen: String) -> String { "\(screen).error" }
        static func retry(_ screen: String) -> String { "\(screen).error.retry" }
        static func loading(_ screen: String) -> String { "\(screen).loading" }
        static func skeletonRow(_ screen: String, _ index: Int) -> String { "\(screen).skeleton.\(index)" }
    }

    /// Debug-only runtime API base URL entry point (long-press the version label).
    enum Debug {
        static let versionLabel = "debug.versionLabel"
        static let settingsSheet = "debug.settings"
        static let baseURLField = "debug.baseURL.field"
        static let baseURLSave = "debug.baseURL.save"
        static let baseURLReset = "debug.baseURL.reset"
        static let baseURLError = "debug.baseURL.error"
        static let baseURLCurrent = "debug.baseURL.current"
    }
}
