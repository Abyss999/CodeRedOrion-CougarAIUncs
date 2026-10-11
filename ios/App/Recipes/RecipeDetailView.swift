import SwiftUI

/// Recipe detail (artboard `RecipeDetail`). Push it with `RecipeDetailView(recipe:)`; it reads the API
/// from the environment. "I made this" removes the recipe's fridge items as used (remove-batch) with an
/// Undo toast (restore-batch) and posts `.itemsDidChange`.
struct RecipeDetailView: View {
    let recipe: Recipe
    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss
    @State private var toast: UndoToastItem?
    @State private var made = false
    @State private var working = false
    @State private var failure: String?
    @State private var servingGrams: Int?

    /// Items that can be marked used (a legacy bare-string `uses_items` entry has no id).
    private var usedIds: [String] {
        var seen = Set<String>()
        return recipe.usesItems.map(\.itemId).filter { !$0.isEmpty && seen.insert($0).inserted }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm + 2) {
                titleBlock
                if let macros = recipe.macros { MacroStrip(macros: macros).accessibilityIdentifier(AccessibilityID.RecipeDetail.macros) }
                ingredients
                if !recipe.steps.isEmpty { steps }
                if let failure {
                    BannerView(style: .error, message: failure,
                               retry: { Task { await madeThis() } }, dismiss: { self.failure = nil },
                               identifiers: BannerIdentifiers(container: AccessibilityID.RecipeDetail.madeError,
                                                              retry: AccessibilityID.RecipeDetail.madeErrorRetry),
                               horizontalInset: 0)
                }
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.s)
            .padding(.bottom, Theme.Spacing.l)
        }
        .background(Theme.Colors.ground.ignoresSafeArea())
        .safeAreaInset(edge: .bottom, spacing: 0) { footer }
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .undoToast(item: $toast)
        .accessibilityIdentifier(AccessibilityID.RecipeDetail.screen)
        .task { await loadServingSize() }
    }

    // MARK: Sections

    private var titleBlock: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(recipe.title).font(Theme.Fonts.screenTitle).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(AccessibilityID.RecipeDetail.title)
            Text("\(recipe.minutes) min" + (recipe.macros != nil ? " · macros estimated per serving" : ""))
                .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted)
            if let line = servingLine {
                Text(line).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.inkSecondary)
                    .accessibilityIdentifier(AccessibilityID.RecipeDetail.servingSize)
            }
        }
    }

    private var servingLine: String? {
        var parts: [String] = []
        if let g = servingGrams { parts.append("Serving size \(g) g") }
        if let s = recipe.servings { parts.append(s == 1 ? "1 serving" : "\(s) servings") }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var ingredients: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("Ingredients").font(Theme.Fonts.cardHeading.weight(.bold)).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            ForEach(recipe.usesItems) { item in
                bullet {
                    HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.stack) {
                        Text(item.name)
                        fridgeTag(item)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            ForEach(recipe.missingItems, id: \.self) { name in
                bullet { Text(name) }
            }
            if !recipe.missingItems.isEmpty {
                Text("You'll need: " + recipe.missingItems.joined(separator: ", "))
                    .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted)
                    .accessibilityIdentifier(AccessibilityID.RecipeDetail.missing)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.RecipeDetail.ingredients)
    }

    private func bullet<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
            Text("•").accessibilityHidden(true)
            content()
            Spacer(minLength: 0)
        }
        .font(Theme.Fonts.body).foregroundStyle(Theme.Colors.inkSecondary)
    }

    @ViewBuilder
    private func fridgeTag(_ item: RecipeItem) -> some View {
        let badge = ExpiryBadgeModel.make(expiry: item.predictedExpiry, freshness: nil)
        let urgent = badge?.style == .urgent
        let phrase = RecipeText.expiryPhrase(item.predictedExpiry)
        Text(phrase.map { "In your fridge · \($0)" } ?? "In your fridge")
            .font(Theme.Fonts.badge)
            .foregroundStyle(urgent ? Theme.Colors.urgentInk : Theme.Colors.forest)
            .padding(.horizontal, Theme.Spacing.s).padding(.vertical, Theme.Spacing.xxs)
            .background(urgent ? Theme.Colors.urgentBg : Theme.Colors.limeTint,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
    }

    private var steps: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("Steps").font(Theme.Fonts.cardHeading).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            ForEach(Array(recipe.steps.enumerated()), id: \.offset) { i, step in
                HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.s) {
                    Text("\(i + 1).").monospacedDigit().accessibilityHidden(true)
                    Text(step)
                    Spacer(minLength: 0)
                }
                .font(Theme.Fonts.body).foregroundStyle(Theme.Colors.inkSecondary)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Step \(i + 1). \(step)")
            }
        }
        .accessibilityIdentifier(AccessibilityID.RecipeDetail.steps)
    }

    // MARK: Footer

    @ViewBuilder
    private var footer: some View {
        if !usedIds.isEmpty {
            VStack(spacing: 0) {
                Divider().overlay(Theme.Colors.hairline)
                Button {
                    Task { await madeThis() }
                } label: {
                    HStack(spacing: Theme.Spacing.s) {
                        if working { ProgressView().tint(Theme.Colors.onForest) }
                        else if made { Image(systemName: "checkmark") }
                        Text(made ? "Marked as made" : "I made this")
                    }
                    .font(Theme.Fonts.button)
                    .foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                    .background(Theme.Colors.forest.opacity(made ? 0.6 : 1),
                                in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                }
                .disabled(made || working)
                .accessibilityIdentifier(made ? AccessibilityID.RecipeDetail.madeDone : AccessibilityID.RecipeDetail.made)
                .accessibilityHint("Marks the fridge items in this recipe as used")
                .padding(.horizontal, Theme.Spacing.gutter)
                .padding(.vertical, Theme.Spacing.sm)
            }
            .background(Theme.Colors.ground)
        }
    }

    // MARK: Actions

    private func madeThis() async {
        guard !made, !working else { return }
        let ids = usedIds
        guard !ids.isEmpty else { return }
        working = true
        failure = nil
        defer { working = false }
        do {
            _ = try await env.api.removeBatch(ids: ids, outcome: .used)
            made = true
            Haptics.success()
            NotificationCenter.default.post(name: .itemsDidChange, object: nil)
            let count = ids.count
            toast = UndoToastItem(message: count == 1 ? "1 item marked used" : "\(count) items marked used") {
                Task { await undo(ids) }
            }
        } catch {
            Haptics.error()
            failure = error.localizedDescription
        }
    }

    private func undo(_ ids: [String]) async {
        do {
            _ = try await env.api.restoreBatch(ids: ids)
            made = false
            NotificationCenter.default.post(name: .itemsDidChange, object: nil)
        } catch {
            // The items stay used (e.g. the 10 minute window passed).
            failure = error.localizedDescription
        }
    }

    /// Grams per serving from the est. weight of the fridge items this recipe uses (nil when unknown).
    private func loadServingSize() async {
        guard let servings = recipe.servings, servings > 0, !usedIds.isEmpty else { return }
        guard let listing = try? await env.api.listItems(storage: nil, groupBy: nil) else { return }
        let items: [Item]
        switch listing {
        case .flat(let flat): items = flat
        case .grouped(let sections): items = sections.flatMap(\.items)
        }
        let weights = items.filter { usedIds.contains($0.id) }.compactMap(\.estWeightKg)
        let totalKg = weights.reduce(0, +)
        guard totalKg > 0 else { return }
        let grams = totalKg * 1000 / Double(servings)
        servingGrams = max(5, Int((grams / 5).rounded()) * 5)
    }
}
