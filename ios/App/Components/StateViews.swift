import SwiftUI

/// Empty state: `ContentUnavailableView` with an optional action. `screen` namespaces the
/// accessibility id (`<screen>.empty`).
struct EmptyStateView: View {
    let screen: String
    let title: String
    let message: String
    var systemImage: String = "leaf"
    var actionTitle: String?
    var action: (() -> Void)?

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: systemImage)
        } description: {
            Text(message)
        } actions: {
            if let actionTitle, let action {
                Button(actionTitle, action: action).buttonStyle(.borderedProminent)
            }
        }
        .foregroundStyle(Theme.Colors.ink)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.State.empty(screen))
    }
}

/// Error state with a retry button (`<screen>.error`, `<screen>.error.retry`).
struct ErrorStateView: View {
    let screen: String
    let error: Error
    var retryTitle = "Try again"
    let retry: () -> Void

    private var isOffline: Bool { (error as? APIError)?.isNetwork ?? false }

    var body: some View {
        ContentUnavailableView {
            Label(isOffline ? "You're offline" : "Something went wrong",
                  systemImage: isOffline ? "wifi.slash" : "exclamationmark.triangle")
        } description: {
            Text(error.localizedDescription)
        } actions: {
            Button(retryTitle, action: retry)
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier(AccessibilityID.State.retry(screen))
        }
        .foregroundStyle(Theme.Colors.ink)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.State.error(screen))
    }
}
