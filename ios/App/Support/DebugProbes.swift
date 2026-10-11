import SwiftUI
import Observation

/// Records haptic events observably, so the `debug.haptics` probe updates as they play
/// (`-UITestRecordHaptics`, mock launches only).
@MainActor
@Observable
final class ObservableRecordingHaptics: HapticsProviding {
    private(set) var events: [HapticEvent] = []
    func play(_ event: HapticEvent) { events.append(event) }
    var joined: String { events.map(\.rawValue).joined(separator: ",") }
}

/// DEBUG-only element that UI tests read: invisible, not hit-testable, but present in the
/// accessibility tree with `value` as both its label and value. Renders nothing in Release.
struct DebugProbe: View {
    let id: String
    let value: String

    var body: some View {
        #if DEBUG
        Text(value.isEmpty ? "none" : value)
            .font(Theme.Fonts.meta)
            .frame(width: Theme.Size.debugProbe, height: Theme.Size.debugProbe)
            .opacity(Theme.Opacity.debugProbe)
            .allowsHitTesting(false)
            .accessibilityLabel(value)
            .accessibilityValue(value)
            .accessibilityIdentifier(id)
        #else
        EmptyView()
        #endif
    }
}
