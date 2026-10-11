import SwiftUI

/// "Cook tonight": the top suggested recipe on a forest card (opens RecipeDetail via a closure).
struct HomeCookCard: View {
    let recipe: Recipe
    let onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                Label {
                    Text(HomeModel.eyebrow(for: recipe))
                } icon: {
                    Image(systemName: "clock").accessibilityHidden(true)
                }
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.onForest)
                Text(recipe.title)
                    .font(Theme.Fonts.sheetTitle)
                    .foregroundStyle(Theme.Colors.onForest)
                    .multilineTextAlignment(.leading)
                Text(HomeModel.detail(for: recipe))
                    .font(Theme.Fonts.callout)
                    .foregroundStyle(Theme.Colors.onForest.opacity(0.8))
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(Theme.Spacing.m + Theme.Spacing.xxs)
            .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens the recipe")
        .accessibilityIdentifier(AccessibilityID.Home.cookCard)
    }
}

/// The muted placeholder under "Cook tonight" when there is nothing to cook yet (HomeEmpty), or
/// recipes couldn't load. Dashed border, no action.
struct HomeCookPlaceholder: View {
    let text: String

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Image(systemName: "frying.pan")
                .font(.title3)
                .foregroundStyle(Theme.Colors.muted)
                .accessibilityHidden(true)
            Text(text)
                .font(Theme.Fonts.callout)
                .foregroundStyle(Theme.Colors.muted)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, Theme.Spacing.m)
        .padding(.vertical, Theme.Spacing.m + Theme.Spacing.xxs)
        .background(Theme.Colors.track.opacity(0.5), in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
            .strokeBorder(Theme.Colors.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(AccessibilityID.Home.cookEmpty)
    }
}
