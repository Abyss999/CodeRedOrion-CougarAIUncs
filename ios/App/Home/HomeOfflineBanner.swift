import SwiftUI

/// The yellow "Can't reach BiteDown" banner (ServerError artboard) with its Try again button.
/// Shown over the error state, and over stale content when a refresh fails.
struct HomeOfflineBanner: View {
    let message: String
    let retry: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.sm))
        layout {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: "wifi.slash").accessibilityHidden(true)
                Text(message)
                    .font(Theme.Fonts.callout.weight(.medium))
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button(action: retry) {
                Text("Try again")
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.useSoonBg)
                    .padding(.horizontal, Theme.Spacing.m)
                    .frame(minHeight: Theme.Size.minTouch)
                    .background(Theme.Colors.useSoonInk, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(AccessibilityID.Home.bannerRetry)
        }
        .foregroundStyle(Theme.Colors.useSoonInk)
        .padding(.vertical, Theme.Spacing.s)
        .padding(.leading, Theme.Spacing.sm + Theme.Spacing.xxs)
        .padding(.trailing, Theme.Spacing.s)
        .background(Theme.Colors.useSoonBg, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Home.banner)
    }
}
