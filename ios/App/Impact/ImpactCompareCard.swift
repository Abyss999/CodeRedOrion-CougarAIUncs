import SwiftUI

/// "This month vs last month": wasted food (weight) this period against the one before it, with a
/// sentence that says which way it went. Hidden for All (no previous window).
struct ImpactCompareCard: View {
    let currentKg: Double
    let previousKg: Double
    let periods: (current: String, previous: String)
    @AppStorage(UnitSystem.storageKey) private var units: UnitSystem = .us
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let f = WeightFormatter(system: units)
        let frac = ImpactFormat.compareFractions(current: currentKg, previous: previousKg)
        let sentence = ImpactFormat.compareSentence(current: currentKg, previous: previousKg, previousName: periods.previous, formatter: f)
        ImpactCard(spacing: Theme.Spacing.sm) {
            ImpactSectionTitle("\(periods.current) vs \(periods.previous.lowercased())")
            VStack(spacing: Theme.Spacing.tileGap) {
                row(periods.current, frac.current, Theme.Colors.chartWasted, f.string(kg: currentKg))
                row(periods.previous, frac.previous, Theme.Colors.muted.opacity(0.45), f.string(kg: previousKg))
            }
            .accessibilityHidden(true)
            chip(sentence)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(periods.current) vs \(periods.previous.lowercased()). Wasted food: \(f.spoken(kg: currentKg)) \(periods.current.lowercased()), \(f.spoken(kg: previousKg)) \(periods.previous.lowercased()). \(sentence.text)")
        .accessibilityIdentifier(AccessibilityID.Impact.compare)
    }

    private func row(_ title: String, _ fraction: Double, _ color: Color, _ value: String) -> some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.xs))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        return layout {
            Text(title).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.inkSecondary)
                .frame(width: dynamicTypeSize.isAccessibilitySize ? nil : 84, alignment: .leading)
            ImpactFractionBar(fraction: fraction, color: color, height: 14)
            Text(value).font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.ink)
                .frame(minWidth: 52, alignment: dynamicTypeSize.isAccessibilitySize ? .leading : .trailing)
        }
    }

    private func chip(_ s: (text: String, direction: ImpactFormat.Direction)) -> some View {
        Label {
            Text(s.text)
        } icon: {
            Image(systemName: s.direction == .down ? "arrow.down" : s.direction == .up ? "arrow.up" : "equal")
                .imageScale(.small).accessibilityHidden(true)
        }
        .font(Theme.Fonts.badge)
        .foregroundStyle(s.direction == .up ? Theme.Colors.urgentInk : Theme.Colors.forest)
        .padding(.horizontal, Theme.Spacing.badgeHorizontal)
        .padding(.vertical, Theme.Spacing.xs)
        .background(s.direction == .up ? Theme.Colors.urgentBg : Theme.Colors.limeTint, in: Capsule())
        .accessibilityIdentifier(AccessibilityID.Impact.compareChip)
    }
}
