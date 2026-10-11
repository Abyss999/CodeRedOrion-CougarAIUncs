import SwiftUI

/// Inline error banner (`fridge.remove.error`) for a rolled-back remove or undo, or a failed
/// refresh. `urgent` colours plus an icon and words, so colour is never the only cue.
struct FridgeBannerView: View {
    let banner: FridgeBanner
    let dismiss: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        layout {
            Label(banner.message, systemImage: "exclamationmark.triangle.fill")
                .font(Theme.Fonts.meta.weight(.semibold))
                .foregroundStyle(Theme.Colors.urgentInk)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: Theme.Spacing.xs) {
                if let retry = banner.retry {
                    Button { retry() } label: {
                        // Sizing on the label, inside the button, so the button is 44 pt (IOS-12).
                        Text("Try again")
                            .font(Theme.Fonts.badge)
                            .foregroundStyle(Theme.Colors.urgentInk)
                            .padding(.horizontal, Theme.Spacing.s)
                            .frame(minHeight: Theme.Size.minTouch)
                            .contentShape(Rectangle())
                    }
                    .accessibilityIdentifier(AccessibilityID.Fridge.removeErrorRetry)
                }
                Button(action: dismiss) {
                    Image(systemName: "xmark")
                        .font(Theme.Fonts.badge)
                        .foregroundStyle(Theme.Colors.urgentInk)
                        .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel("Dismiss")
                .accessibilityIdentifier(AccessibilityID.Fridge.removeErrorDismiss)
            }
        }
        .padding(.leading, Theme.Spacing.m)
        .padding(.trailing, Theme.Spacing.xs)
        .padding(.vertical, Theme.Spacing.xs)
        .background(Theme.Colors.urgentBg, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .padding(.horizontal, Theme.Spacing.gutter)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Fridge.removeError)
    }
}
