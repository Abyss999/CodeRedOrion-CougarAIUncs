import SwiftUI

/// Placeholder Home tab content. Hosts the version label (Debug settings entry) and the
/// `-UITestShowToast` hook: the Undo toast is attached here, inside the tab's content, as real
/// screens will do.
struct HomePlaceholderView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var toast: UndoToastItem?
    @State private var undoTapped = false

    var body: some View {
        VStack(spacing: Theme.Spacing.m) {
            Text("Home")
            VersionLabel()
            if undoTapped {
                Text("Undo tapped")
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.muted)
                    .accessibilityIdentifier(AccessibilityID.Toast.marker)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .undoToast(item: $toast)
        .task {
            #if DEBUG
            if env.launch.showToast, toast == nil {
                toast = UndoToastItem(message: "Baby spinach removed", onUndo: { undoTapped = true })
            }
            #endif
        }
    }
}
