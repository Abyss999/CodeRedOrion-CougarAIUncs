import SwiftUI

/// Stand-in for Add text, Barcode and Receipt review, which arrive in the next PR (2b). Their entry points
/// (tiles, "+ Add something we missed", "Type it instead") already route here.
struct AddPlaceholderView: View {
    let destination: AddDestination
    let onBack: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            BackButton(action: onBack, id: AccessibilityID.Add.placeholderBack)
            ContentUnavailableView {
                Label(destination.title, systemImage: "hammer")
            } description: {
                Text("This way of adding food is coming soon.")
            }
            .foregroundStyle(Theme.Colors.ink)
        }
        .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.m)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Add.placeholder)
    }
}
