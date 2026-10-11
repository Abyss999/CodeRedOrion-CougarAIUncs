import SwiftUI

/// Food saved, led by pounds: the number counts up, an arrow-and-words chip compares with the previous
/// window, and the carbon-emissions line (plain words, with a driving equivalent) is secondary.
struct ImpactHeroCard: View {
    let impact: Impact
    let range: ImpactRange
    @AppStorage(UnitSystem.storageKey) private var units: UnitSystem = .us

    var body: some View {
        let f = WeightFormatter(system: units)
        let text = f.string(kg: impact.saved.kg)
        let parts = ImpactFormat.heroParts(text)
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text("Food saved")
                .font(Theme.Fonts.rowTitle)
                .foregroundStyle(Theme.Colors.onForestMuted)
            HStack(alignment: .firstTextBaseline, spacing: Theme.Spacing.xs) {
                number(parts.number)
                    .font(Theme.Fonts.hero)
                    .tracking(Theme.Tracking.hero)
                    .foregroundStyle(Theme.Colors.onForest)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                if !parts.unit.isEmpty {
                    Text(parts.unit)
                        .font(Theme.Fonts.display(22, relativeTo: .title2, medium: true))
                        .foregroundStyle(Theme.Colors.onForest)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Food saved, \(f.spoken(kg: impact.saved.kg))")
            .accessibilityIdentifier(AccessibilityID.Impact.heroValue)

            if let previous = impact.previous, let phrase = ImpactFormat.previousPhrase(range) {
                ImpactDeltaChip(delta: ImpactFormat.weightDelta(current: impact.saved.kg, previous: previous.saved.kg, formatter: f),
                                suffix: "vs \(phrase)", onForest: true, identifier: AccessibilityID.Impact.heroChip)
                    .padding(.top, Theme.Spacing.xs)
            }

            Divider().overlay(Theme.Colors.onForest.opacity(Theme.Opacity.onForestFill))
                .padding(.top, Theme.Spacing.s)
            Label {
                Text(ImpactFormat.emissionsLine(co2eKg: impact.saved.co2eKg, system: units))
                    .font(Theme.Fonts.callout)
                    .foregroundStyle(Theme.Colors.onForest)
                    .fixedSize(horizontal: false, vertical: true)
            } icon: {
                Image(systemName: "leaf").foregroundStyle(Theme.Colors.onForest).accessibilityHidden(true)
            }
            .padding(.top, Theme.Spacing.xs)
            .accessibilityIdentifier(AccessibilityID.Impact.emissions)
        }
        .padding(Theme.Spacing.sheetSection)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Impact.hero)
    }

    /// Counts up while the figure is a plain number ("21.2"); "<1" just shows.
    @ViewBuilder private func number(_ s: String) -> some View {
        if let value = Double(s) {
            let decimals = s.split(separator: ".").dropFirst().first?.count ?? 0
            CountUpText(value: value) { String(format: "%.\(decimals)f", $0) }
        } else {
            Text(s)
        }
    }
}
