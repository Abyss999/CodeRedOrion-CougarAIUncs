import SwiftUI

/// Handles `bitedown://friend/<code>` deep links anywhere in the app: presents the scan result flow
/// (adding the friend and showing FriendAdded or the error). Apply once at the app root.
private struct FriendLinkModifier: ViewModifier {
    @Environment(AppEnvironment.self) private var env
    @State private var link: PendingLink?

    struct PendingLink: Identifiable {
        let id = UUID()
        let code: String
    }

    func body(content: Content) -> some View {
        content
            .onOpenURL { url in
                if let code = FriendLink.code(from: url) { link = PendingLink(code: code) }
            }
            .sheet(item: $link) { pending in
                NavigationStack {
                    FriendScanView(api: env.api, initialCode: pending.code) { link = nil }
                        .toolbar {
                            ToolbarItem(placement: .cancellationAction) {
                                Button("Close") { link = nil }
                            }
                        }
                }
                .tint(Theme.Colors.forest)
            }
    }
}

extension View {
    /// Presents the friend-add flow when the app opens a `bitedown://friend/<code>` URL.
    func handlesFriendLinks() -> some View { modifier(FriendLinkModifier()) }
}
