import SwiftUI

/// Recipes tab (artboard `Recipes`): `POST /recipes/suggest` (request 10) with filter chips.
/// "Only what I have" is on by default and filters `missing_items` empty on the client.
struct RecipesView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var model: RecipesModel?

    var body: some View {
        NavigationStack {
            Group {
                if let model {
                    RecipesContent(model: model)
                } else {
                    Color.clear
                }
            }
            .background(Theme.Colors.ground.ignoresSafeArea())
            .navigationBarHidden(true)
            .navigationDestination(for: Recipe.self) { RecipeDetailView(recipe: $0) }
        }
        .accessibilityIdentifier(AccessibilityID.Recipes.screen)
        .task {
            if model == nil { model = RecipesModel(api: env.api) }
            await model?.loadIfNeeded()
        }
    }
}

private struct RecipesContent: View {
    @Bindable var model: RecipesModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                header
                filters
                if model.all != nil, let error = model.error {
                    BannerView(style: .error, message: RecipesModel.friendlyMessage(for: error),
                               retry: { Task { await model.refresh() } },
                               dismiss: nil,
                               identifiers: BannerIdentifiers(container: "recipes.banner", retry: "recipes.banner.retry"),
                               horizontalInset: 0)
                }
                stateBody
                    .motionAnimation(Theme.Motion.quick, value: model.resultToken)
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.s)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .refreshable { await model.refresh() }
    }

    private var header: some View {
        HStack {
            Text("Recipes")
                .font(Theme.Fonts.screenTitle)
                .foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(AccessibilityID.Recipes.title)
            Spacer()
            Button {
                Task { await model.refresh() }
            } label: {
                Image(systemName: "arrow.clockwise")
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                    .background(Theme.Colors.surface, in: Circle())
                    .overlay(Circle().strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline))
                    .contentShape(Circle())
            }
            .disabled(model.isRefreshing)
            .accessibilityLabel("New suggestions")
            .accessibilityIdentifier(AccessibilityID.Recipes.refresh)
        }
    }

    private var filters: some View {
        FlowLayout(spacing: Theme.Spacing.s) {
            chip("Only what I have", key: "onlyHave", on: model.onlyWhatIHave, icon: "checkmark") { model.onlyWhatIHave.toggle() }
            chip("Expiring first", key: "expiring", on: model.expiringFirst, icon: "clock") { model.expiringFirst.toggle() }
            chip("Under 30 min", key: "quick", on: model.underThirty, icon: nil) { model.underThirty.toggle() }
            chip("Vegetarian", key: "vegetarian", on: model.vegetarian, icon: nil) { Task { await model.toggleVegetarian() } }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Filters")
        .accessibilityIdentifier(AccessibilityID.Recipes.filters)
    }

    private func chip(_ title: String, key: String, on: Bool, icon: String?, action: @escaping () -> Void) -> some View {
        Button {
            Haptics.selection()
            action()
        } label: {
            HStack(spacing: Theme.Spacing.stack) {
                if on, let icon { Image(systemName: icon).font(Theme.Fonts.badge) }
                Text(title).font(on ? Theme.Fonts.segmentSelected : Theme.Fonts.segment)
            }
            .foregroundStyle(on ? Theme.Colors.onForest : Theme.Colors.ink)
            .padding(.horizontal, Theme.Spacing.sm + 2)
            .frame(minHeight: Theme.Size.segment)
            .background(on ? Theme.Colors.forest : Theme.Colors.surface, in: Capsule())
            .overlay(Capsule().strokeBorder(Theme.Colors.border, lineWidth: on ? 0 : Theme.Stroke.hairline))
            .frame(minHeight: Theme.Size.minTouch)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
        .accessibilityValue(on ? "On" : "Off")
        .accessibilityIdentifier(AccessibilityID.Recipes.filter(key))
    }

    @ViewBuilder
    private var stateBody: some View {
        switch model.state {
        case .loading:
            SkeletonList(screen: AccessibilityID.Recipes.screen, count: 4)
        case .error(let error):
            ErrorStateView(screen: AccessibilityID.Recipes.screen, error: RecipesModel.displayError(error)) {
                Task { await model.retry() }
            }
        case .empty:
            EmptyStateView(screen: AccessibilityID.Recipes.screen, title: "No recipes yet",
                           message: "Add some food to your fridge and we'll suggest what to cook.",
                           systemImage: "frying.pan")
        case .filteredOut(let hidAll):
            if hidAll {
                EmptyStateView(screen: AccessibilityID.Recipes.screen, title: "Nothing from just what you have",
                               message: "Every idea needs a few extra ingredients.",
                               systemImage: "frying.pan", actionTitle: "Show recipes that need a few things") {
                    model.showNeedsAFewThings()
                }
            } else {
                EmptyStateView(screen: AccessibilityID.Recipes.screen, title: "No recipes match",
                               message: "Try turning a filter off.", systemImage: "line.3.horizontal.decrease.circle",
                               actionTitle: "Clear filters") { model.clearFilters() }
            }
        case .content(let recipes):
            content(recipes)
        }
    }

    private func content(_ recipes: [Recipe]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            if let best = recipes.first {
                NavigationLink(value: best) { BestMatchCard(recipe: best) }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(AccessibilityID.Recipes.best)
            }
            if recipes.count > 1 {
                VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                    Text("More from your fridge")
                        .font(Theme.Fonts.section)
                        .foregroundStyle(Theme.Colors.ink)
                        .accessibilityAddTraits(.isHeader)
                    VStack(spacing: 0) {
                        ForEach(Array(recipes.dropFirst().enumerated()), id: \.element.id) { i, recipe in
                            NavigationLink(value: recipe) { RecipeRow(recipe: recipe) }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier(AccessibilityID.Recipes.row(i))
                            if i < recipes.count - 2 { Divider().overlay(Theme.Colors.hairline) }
                        }
                    }
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .accessibilityIdentifier(AccessibilityID.Recipes.list)
                }
            }
        }
    }
}

private struct BestMatchCard: View {
    let recipe: Recipe

    private var eyebrow: String {
        let n = recipe.usesItems.count
        return n == 0 ? "Best match" : "Best match · uses \(n) \(n == 1 ? "item" : "items") from your fridge"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text(eyebrow).font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.onForestMuted)
            Text(recipe.title).font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.onForest)
                .multilineTextAlignment(.leading)
            if !recipe.usesItems.isEmpty {
                FlowLayout(spacing: Theme.Spacing.stack) {
                    ForEach(recipe.usesItems.prefix(4)) { item in
                        let phrase = RecipeText.expiryPhrase(item.predictedExpiry)
                        Text(phrase.map { "\(item.name) · \($0)" } ?? item.name)
                            .font(Theme.Fonts.badge)
                            .foregroundStyle(Theme.Colors.onForestChip)
                            .padding(.horizontal, Theme.Spacing.badgeHorizontal).padding(.vertical, Theme.Spacing.xs)
                            .background(Theme.Colors.forestChip, in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
                    }
                }
            }
            if let macros = recipe.macros { MacroStrip(macros: macros, onCard: true) }
            HStack {
                Text(RecipeText.meta(recipe) + (recipe.needsNothing ? "" : " · needs \(recipe.missingItems.count) more"))
                    .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.onForestMuted)
                Spacer()
                Text("Cook it").font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.onForest)
                    .frame(minHeight: Theme.Size.minTouch)
            }
        }
        .padding(Theme.Spacing.m + 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
        .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens the recipe")
    }
}

private struct RecipeRow: View {
    let recipe: Recipe

    private var meta: String {
        var parts = [RecipeText.meta(recipe)]
        if let m = recipe.macros { parts.append("\(m.kcal) kcal · \(Int(m.proteinG.rounded())) g protein") }
        if !recipe.needsNothing { parts.append("needs \(recipe.missingItems.count) more") }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(recipe.title).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    .multilineTextAlignment(.leading)
                Text(meta).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                    .multilineTextAlignment(.leading)
            }
            Spacer(minLength: Theme.Spacing.s)
            if !recipe.usesItems.isEmpty {
                Text("Uses \(recipe.usesItems.count)")
                    .font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.forest)
                    .padding(.horizontal, Theme.Spacing.badgeHorizontal).padding(.vertical, Theme.Spacing.xs)
                    .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
                    .fixedSize()
            }
        }
        .padding(.horizontal, Theme.Spacing.m).padding(.vertical, Theme.Spacing.sm + 2)
        .frame(minHeight: Theme.Size.minTouch)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
