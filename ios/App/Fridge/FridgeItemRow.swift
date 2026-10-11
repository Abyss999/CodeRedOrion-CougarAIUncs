import SwiftUI

/// `ItemRow` on the Fridge: food-group tile, name, meta line and `ExpiryBadge`.
/// The row is a container (`fridge.row.<id>`) holding one combined text element and the badge
/// (`fridge.row.<id>.badge`). At accessibility sizes the badge moves under the text.
struct FridgeItemRow: View {
    let item: Item
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var badge: ExpiryBadgeModel? { ExpiryBadgeModel.make(for: item) }
    private var stacked: Bool { dynamicTypeSize.isAccessibilitySize }

    var body: some View {
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
        .padding(.vertical, Theme.Spacing.sm)
        .frame(minHeight: Theme.Size.minTouch)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Fridge.row(item.id))
    }

    private var text: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(item.name)
                .font(Theme.Fonts.rowTitle)
                .foregroundStyle(Theme.Colors.ink)
            Text(ItemText.meta(item))
                .font(item.freshness == .spoiled ? Theme.Fonts.meta.weight(.medium) : Theme.Fonts.meta)
                .foregroundStyle(item.freshness == .spoiled ? Theme.Colors.urgentInk : Theme.Colors.muted)
        }
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder private var badgeView: some View {
        if let badge {
            ExpiryBadge(model: badge)
                .accessibilityIdentifier(AccessibilityID.Fridge.rowBadge(item.id))
        }
    }
}
