import SwiftUI

/// Loading placeholder shaped like the Impact content: hero card, tile grid, two cards. One
/// VoiceOver element "Loading" (`impact.loading`).
struct ImpactSkeleton: View {
    var body: some View {
        VStack(spacing: Theme.Spacing.m) {
            block(height: 150, radius: Theme.Radius.hero)
            HStack(spacing: Theme.Spacing.tileGap) {
                block(height: 96, radius: Theme.Radius.card)
                block(height: 96, radius: Theme.Radius.card)
            }
            HStack(spacing: Theme.Spacing.tileGap) {
                block(height: 96, radius: Theme.Radius.card)
                block(height: 96, radius: Theme.Radius.card)
            }
            block(height: 120, radius: Theme.Radius.card)
            block(height: 220, radius: Theme.Radius.card)
        }
        .shimmering()
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
        .accessibilityIdentifier(AccessibilityID.State.loading(AccessibilityID.Impact.screen))
    }

    private func block(height: CGFloat, radius: CGFloat) -> some View {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .fill(Theme.Colors.limeTint)
            .frame(height: height)
    }
}
