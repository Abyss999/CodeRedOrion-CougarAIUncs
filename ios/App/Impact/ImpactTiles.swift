import SwiftUI

/// Items saved, money saved, food thrown out and the waste rate (stated alone, no comparison).
struct ImpactTiles: View {
    let impact: Impact
    let range: ImpactRange
    @AppStorage(UnitSystem.storageKey) private var units: UnitSystem = .us
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let f = WeightFormatter(system: units)
        let prev = impact.previous
        let columns = dynamicTypeSize.isAccessibilitySize
            ? [GridItem(.flexible())]
            : [GridItem(.flexible(), spacing: Theme.Spacing.tileGap), GridItem(.flexible(), spacing: Theme.Spacing.tileGap)]
        LazyVGrid(columns: columns, spacing: Theme.Spacing.tileGap) {
            tile("items", "Items saved", "\(impact.saved.count)", spoken: "\(impact.saved.count)",
                 delta: prev.map { ImpactFormat.countDelta(current: impact.saved.count, previous: $0.saved.count) })
            tile("money", "Money saved", ImpactFormat.money(impact.saved.money), spoken: ImpactFormat.money(impact.saved.money),
                 delta: prev.map { ImpactFormat.moneyDelta(current: impact.saved.money, previous: $0.saved.money) })
            tile("thrown", "Food thrown out", f.string(kg: impact.wasted.kg), spoken: f.spoken(kg: impact.wasted.kg),
                 delta: prev.map { ImpactFormat.weightDelta(current: impact.wasted.kg, previous: $0.wasted.kg, formatter: f) },
                 lowerIsBetter: true)
            tile("wasterate", "Waste rate", ImpactFormat.percent(impact.wasteRate), spoken: ImpactFormat.percent(impact.wasteRate), delta: nil)
        }
    }

    private func tile(_ kind: String, _ title: String, _ value: String, spoken: String,
                      delta: ImpactFormat.Delta?, lowerIsBetter: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
            Text(title).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
            Text(value)
                .font(Theme.Fonts.display(26, relativeTo: .title))
                .foregroundStyle(Theme.Colors.ink)
                .lineLimit(1)
                .minimumScaleFactor(0.6)
            if let delta {
                ImpactDeltaChip(delta: delta, suffix: "vs previous")
                    .padding(.top, Theme.Spacing.xs)
            }
        }
        .padding(Theme.Spacing.tileInner)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title), \(spoken)" + (delta.map { ". \($0.spoken) vs previous" } ?? ""))
        .accessibilityIdentifier(AccessibilityID.Impact.tile(kind))
    }
}
