import SwiftUI

/// One-line observation from `GET /tips` (never advice), at the top of Home. Dismissible; the
/// owner remembers the dismissed message so it stays gone (see `HomeView`).
struct HomeTipCard: View {
    let message: String
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Image(systemName: "lightbulb")
                .font(.body)
                .foregroundStyle(Theme.Colors.forest)
                .accessibilityHidden(true)
            Text(message)
                .font(Theme.Fonts.callout)
                .foregroundStyle(Theme.Colors.inkSecondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, Theme.Spacing.sm)
                .accessibilityIdentifier(AccessibilityID.Home.tip)
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.Colors.muted)
                    .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Dismiss tip")
            .accessibilityIdentifier(AccessibilityID.Home.tipDismiss)
        }
        .padding(.leading, Theme.Spacing.m)
        .padding(.trailing, Theme.Spacing.xs)
        .overlay(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
            .strokeBorder(Theme.Colors.border, lineWidth: 1))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Tip")
    }
}
