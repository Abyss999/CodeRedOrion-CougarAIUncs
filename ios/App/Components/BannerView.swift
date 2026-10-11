import SwiftUI

/// Colour and icon for a banner. The icon and the words carry the meaning too, so colour is never the only cue.
enum BannerStyle: Hashable, Sendable {
    case error, warning, info, success

    var systemImage: String {
        switch self {
        case .error: "exclamationmark.triangle.fill"
        case .warning: "exclamationmark.circle.fill"
        case .info: "info.circle.fill"
        case .success: "checkmark.circle.fill"
        }
    }
    var background: Color {
        switch self {
        case .error: Theme.Colors.urgentBg
        case .warning: Theme.Colors.useSoonBg
        case .info: Theme.Colors.limeTint
        case .success: Theme.Colors.noteLime
        }
    }
    var ink: Color {
        switch self {
        case .error: Theme.Colors.urgentInk
        case .warning: Theme.Colors.useSoonInk
        case .info, .success: Theme.Colors.forest
        }
    }
}

/// Accessibility identifiers for one banner instance (each screen passes its own).
struct BannerIdentifiers: Sendable {
    var container: String
    var retry: String?
    var dismiss: String?
}

/// Inline banner: icon + message, an optional retry button and an optional dismiss button.
/// Stacks the buttons under the message at accessibility text sizes. Used by the Fridge and by
/// every later screen that shows a rolled-back or failed action.
struct BannerView: View {
    let style: BannerStyle
    let message: String
    var retryTitle = "Try again"
    var retry: (() -> Void)?
    var dismiss: (() -> Void)?
    var identifiers: BannerIdentifiers
    /// Side padding; pass 0 when the parent already insets the banner.
    var horizontalInset: CGFloat = Theme.Spacing.gutter
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        layout {
            Label(message, systemImage: style.systemImage)
                .font(Theme.Fonts.meta.weight(.semibold))
                .foregroundStyle(style.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
            if retry != nil || dismiss != nil {
                HStack(spacing: Theme.Spacing.xs) {
                    if let retry {
                        Button { retry() } label: {
                            // Sizing on the label, inside the button, so the button is 44 pt.
                            Text(retryTitle)
                                .font(Theme.Fonts.badge)
                                .foregroundStyle(style.ink)
                                .padding(.horizontal, Theme.Spacing.s)
                                .frame(minHeight: Theme.Size.minTouch)
                                .contentShape(Rectangle())
                        }
                        .accessibilityIdentifier(identifiers.retry ?? identifiers.container + ".retry")
                    }
                    if let dismiss {
                        Button(action: dismiss) {
                            Image(systemName: "xmark")
                                .font(Theme.Fonts.badge)
                                .foregroundStyle(style.ink)
                                .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                                .contentShape(Rectangle())
                        }
                        .accessibilityLabel("Dismiss")
                        .accessibilityIdentifier(identifiers.dismiss ?? identifiers.container + ".dismiss")
                    }
                }
            }
        }
        .padding(.leading, Theme.Spacing.m)
        .padding(.trailing, retry != nil || dismiss != nil ? Theme.Spacing.xs : Theme.Spacing.m)
        .padding(.vertical, Theme.Spacing.xs)
        .frame(minHeight: Theme.Size.minTouch)
        .background(style.background, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .padding(.horizontal, horizontalInset)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(identifiers.container)
    }
}
