import SwiftUI

extension AccessibilityID.Recipes {
    static let title = "recipes.title"
    static let refresh = "recipes.refresh"
    static let filters = "recipes.filters"
    static func filter(_ key: String) -> String { "recipes.filter.\(key)" }   // onlyHave|expiring|quick|vegetarian
    static let best = "recipes.best"
    static let list = "recipes.list"
    static func row(_ index: Int) -> String { "recipes.row.\(index)" }
    static let showMissing = "recipes.showmissing"
    static let clearFilters = "recipes.clearfilters"
}

extension AccessibilityID {
    enum RecipeDetail {
        static let screen = "recipedetail"
        static let title = "recipedetail.title"
        static let ingredients = "recipedetail.ingredients"
        static let steps = "recipedetail.steps"
        static let servingSize = "recipedetail.servingsize"
        static let macros = "recipedetail.macros"
        static let missing = "recipedetail.missing"
        static let made = "recipedetail.made"
        static let madeError = "recipedetail.made.error"
        static let madeErrorRetry = "recipedetail.made.error.retry"
        static let madeDone = "recipedetail.made.done"
    }
}

/// Wrapping row layout for the filter chips.
struct FlowLayout: Layout {
    var spacing: CGFloat = Theme.Spacing.s

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        layout(in: proposal.width ?? .infinity, subviews: subviews).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = layout(in: bounds.width, subviews: subviews)
        for (i, origin) in result.origins.enumerated() {
            subviews[i].place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y), proposal: .unspecified)
        }
    }

    private func layout(in width: CGFloat, subviews: Subviews) -> (size: CGSize, origins: [CGPoint]) {
        var origins: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, maxX: CGFloat = 0
        for sub in subviews {
            let s = sub.sizeThatFits(.unspecified)
            if x > 0, x + s.width > width { x = 0; y += rowHeight + spacing; rowHeight = 0 }
            origins.append(CGPoint(x: x, y: y))
            x += s.width + spacing
            rowHeight = max(rowHeight, s.height)
            maxX = max(maxX, x - spacing)
        }
        return (CGSize(width: maxX, height: y + rowHeight), origins)
    }
}

/// kcal / protein / carbs / fat per serving.
struct MacroStrip: View {
    let macros: Macros
    /// On a forest card (Recipes hero) or on the ground (detail).
    var onCard = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var cells: [(value: String, label: String, spoken: String)] {
        [("\(macros.kcal)", "kcal", "\(macros.kcal) calories"),
         ("\(Int(macros.proteinG.rounded())) g", "protein", "\(Int(macros.proteinG.rounded())) grams protein"),
         ("\(Int(macros.carbsG.rounded())) g", "carbs", "\(Int(macros.carbsG.rounded())) grams carbs"),
         ("\(Int(macros.fatG.rounded())) g", "fat", "\(Int(macros.fatG.rounded())) grams fat")]
    }

    var body: some View {
        // AX sizes: 2 x 2 so the figures never truncate.
        let columns = Array(repeating: GridItem(.flexible(), spacing: onCard ? Theme.Spacing.xxs : Theme.Spacing.s),
                            count: dynamicTypeSize.isAccessibilitySize ? 2 : 4)
        LazyVGrid(columns: columns, spacing: onCard ? Theme.Spacing.xxs : Theme.Spacing.s) {
            ForEach(cells, id: \.label) { cell in
                VStack(spacing: Theme.Spacing.xxs) {
                    Text(cell.value).font(Theme.Fonts.cardHeading)
                        .foregroundStyle(onCard ? Theme.Colors.onForest : Theme.Colors.ink)
                    Text(cell.label).font(Theme.Fonts.meta)
                        .foregroundStyle(onCard ? Theme.Colors.onForestMuted : Theme.Colors.muted)
                }
                .frame(maxWidth: .infinity)
                .padding(.vertical, Theme.Spacing.s)
                .background(onCard ? Theme.Colors.forest : Theme.Colors.surface,
                            in: RoundedRectangle(cornerRadius: onCard ? 0 : Theme.Radius.input, style: .continuous))
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(cell.spoken)
            }
        }
        .background(onCard ? Theme.Colors.forestChip : Color.clear)
        .clipShape(RoundedRectangle(cornerRadius: onCard ? Theme.Radius.control : 0, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Per serving")
    }
}

extension Recipe {
    /// Earliest `predictedExpiry` of the items this recipe uses (nil when unknown).
    var soonestExpiry: Date? { usesItems.compactMap(\.predictedExpiry).min() }
    var needsNothing: Bool { missingItems.isEmpty }
}

enum RecipeText {
    /// "Today", "Tomorrow", "N days" for a `uses_items` expiry.
    static func expiryPhrase(_ date: Date?, now: Date = Date(), calendar: Calendar = .current) -> String? {
        guard let date else { return nil }
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now), to: calendar.startOfDay(for: date)).day ?? 0
        switch days {
        case ..<0: return "Expired"
        case 0: return "Today"
        case 1: return "Tomorrow"
        default: return "\(days) days"
        }
    }

    static func meta(_ r: Recipe) -> String {
        var parts = ["\(r.minutes) min"]
        if let s = r.servings { parts.append(s == 1 ? "1 serving" : "\(s) servings") }
        return parts.joined(separator: " · ")
    }
}
