import UIKit

/// Haptic pairings from MOTION.md. Views call `Haptics.success()` etc.; the provider is swappable
/// so tests and the UI-test mock run silently (`NoOpHaptics`) or record (`RecordingHaptics`).
/// The system generators already honour Settings > Sounds & Haptics > System Haptics (and are
/// silent on the Simulator), so the system setting is respected without extra checks.
/// Haptics are unaffected by Reduce Motion (MOTION.md: haptics stay).
enum HapticEvent: String, Sendable {
    case success, warning, error, selection, lightImpact
}

@MainActor
protocol HapticsProviding: AnyObject {
    func play(_ event: HapticEvent)
}

@MainActor
final class SystemHaptics: HapticsProviding {
    private let notification = UINotificationFeedbackGenerator()
    private let selection = UISelectionFeedbackGenerator()
    private let impact = UIImpactFeedbackGenerator(style: .light)

    func play(_ event: HapticEvent) {
        switch event {
        case .success: notification.notificationOccurred(.success)
        case .warning: notification.notificationOccurred(.warning)
        case .error: notification.notificationOccurred(.error)
        case .selection: selection.selectionChanged()
        case .lightImpact: impact.impactOccurred()
        }
    }
}

@MainActor
final class NoOpHaptics: HapticsProviding {
    func play(_ event: HapticEvent) {}
}

/// Captures events for assertions in unit tests.
@MainActor
final class RecordingHaptics: HapticsProviding {
    private(set) var events: [HapticEvent] = []
    func play(_ event: HapticEvent) { events.append(event) }
}

@MainActor
enum Haptics {
    static var provider: HapticsProviding = SystemHaptics()

    /// Add confirmed, remove confirmed, claim, "I made this".
    static func success() { provider.play(.success) }
    /// "Threw it away".
    static func warning() { provider.play(.warning) }
    /// A sign-in error.
    static func error() { provider.play(.error) }
    /// Steppers, segmented controls, outcome tiles.
    static func selection() { provider.play(.selection) }
    static func lightImpact() { provider.play(.lightImpact) }
}
