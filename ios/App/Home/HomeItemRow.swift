import SwiftUI

/// A "Use these first" row: food-group tile, name, quantity · group, and the expiry badge.
/// Tapping opens the item (a closure until Item detail lands). At AX sizes the badge moves under the text.
struct HomeItemRow: View {
    let item: Item
    let onOpen: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var badge: ExpiryBadgeModel? { ExpiryBadgeModel.make(for: item) }
    private var stacked: Bool { dynamicTypeSize.isAccessibilitySize }

    var body: some View {
        Button(action: onOpen) {
            HStack(alignment: stacked ? .top : .center, spacing: Theme.Spacing.sm) {
                FoodGroupIcon(group: item.foodGroup)
                if stacked {
                    VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                        text
                        badgeView
                    }
                    Spacer(minLength: 0)
                } else {
                    text
                    Spacer(minLength: Theme.Spacing.s)
                    badgeView
                }
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.vertical, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.minTouch)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(AccessibilityID.Home.row(item.id))
    }

    private var text: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(item.name)
                .font(Theme.Fonts.rowTitle)
                .foregroundStyle(Theme.Colors.ink)
            Text("\(ItemText.quantity(item)) · \(item.foodGroup.displayName)")
                .font(Theme.Fonts.meta)
                .foregroundStyle(Theme.Colors.muted)
        }
        .multilineTextAlignment(.leading)
    }

    @ViewBuilder private var badgeView: some View {
        if let badge { ExpiryBadge(model: badge) }
    }
}
