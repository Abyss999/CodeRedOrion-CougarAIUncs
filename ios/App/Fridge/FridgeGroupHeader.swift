import SwiftUI

/// Food-group section header: glyph, uppercase group name and "· count" (Fridge artboard).
struct FridgeGroupHeader: View {
    let section: ItemSection

    var body: some View {
        HStack(spacing: Theme.Spacing.stack) {
            FoodGroupGlyph(group: section.foodGroup)
            GroupHeaderText(text: section.foodGroup.displayName)
            Text("· \(section.items.count)")
                .font(Theme.Fonts.meta.weight(.medium))
                .foregroundStyle(Theme.Colors.muted)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(section.foodGroup.displayName), \(section.items.count) \(section.items.count == 1 ? "item" : "items")")
        .accessibilityAddTraits(.isHeader)
        .accessibilityIdentifier(AccessibilityID.Fridge.group(section.foodGroup.rawValue))
    }
}
