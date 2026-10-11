import SwiftUI

/// `ItemRow` on the Fridge: food-group tile, name, quantity-only meta line and one `ExpiryBadge`.
///
/// Normal mode: the row is a container (`fridge.row.<id>`) holding one combined text element
/// (which carries the "Remove" accessibility action, IOS-13) and the badge (`fridge.row.<id>.badge`).
/// Select mode (`FridgeSelect` artboard): a leading checkbox column; the whole row is one checkbox
/// button (`fridge.row.<id>.select`). At accessibility sizes the badge moves under the text.
struct FridgeItemRow: View {
    let item: Item
    /// nil = normal mode; otherwise select mode with this checked state.
    var selected: Bool?
    var onToggle: () -> Void = {}
    var onRemove: () -> Void = {}
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var badge: ExpiryBadgeModel? { ExpiryBadgeModel.make(for: item) }
    private var stacked: Bool { dynamicTypeSize.isAccessibilitySize }

    var body: some View {
        if let selected {
            Button(action: onToggle) {
                HStack(spacing: 0) {
                    checkbox(selected)
                    content
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Select \(item.name), \(ItemText.meta(item))\(badge.map { ", " + $0.accessibilityText } ?? "")")
            .accessibilityValue(selected ? "Selected" : "Not selected")
            .accessibilityAddTraits(.isButton)
            .accessibilityIdentifier(AccessibilityID.Fridge.rowSelect(item.id))
        } else {
            content
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(AccessibilityID.Fridge.row(item.id))
        }
    }

    private var content: some View {
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
    }

    private func checkbox(_ on: Bool) -> some View {
        Circle()
            .strokeBorder(on ? Theme.Colors.forest : Theme.Colors.muted, lineWidth: Theme.Stroke.selected)
            .background(Circle().fill(on ? Theme.Colors.forest : Color.clear))
            .overlay {
                if on {
                    Image(systemName: "checkmark")
                        .font(Theme.Fonts.badge)
                        .foregroundStyle(Theme.Colors.onForest)
                }
            }
            .frame(width: Theme.Size.checkbox, height: Theme.Size.checkbox)
            .frame(width: Theme.Size.selectColumn)
            .frame(maxHeight: .infinity)
            .motionAnimation(Theme.Motion.quick, value: on)
            .accessibilityHidden(true)
    }

    private var text: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(item.name)
                .font(Theme.Fonts.rowTitle)
                .foregroundStyle(Theme.Colors.ink)
            Text(ItemText.meta(item))
                .font(Theme.Fonts.meta)
                .foregroundStyle(Theme.Colors.muted)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: "Remove") { if selected == nil { onRemove() } }
    }

    @ViewBuilder private var badgeView: some View {
        if let badge {
            ExpiryBadge(model: badge)
                .accessibilityIdentifier(AccessibilityID.Fridge.rowBadge(item.id))
        }
    }
}
