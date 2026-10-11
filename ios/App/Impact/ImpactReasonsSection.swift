import SwiftUI

/// "Why food got thrown out": one bar per reason, count at the end.
struct ImpactReasonsSection: View {
    let reasons: [WasteReasonStat]
    let wastedCount: Int
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            ImpactSectionTitle("Why food got thrown out")
            if wastedCount == 0 {
                Text("Nothing thrown out in this range.")
                    .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted)
            } else {
                let top = max(reasons.map(\.count).max() ?? 1, 1)
                ForEach(reasons) { r in row(r, top: top) }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Impact.reasons)
    }

    private func row(_ r: WasteReasonStat, top: Int) -> some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.xs))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        return layout {
            Text(ImpactFormat.reasonTitle(r.reason))
                .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.inkSecondary)
                .frame(width: dynamicTypeSize.isAccessibilitySize ? nil : 100, alignment: .leading)
            ImpactFractionBar(fraction: Double(r.count) / Double(top), color: Theme.Colors.chartWasted)
            Text("\(r.count)")
                .font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.ink)
                .frame(minWidth: 24, alignment: dynamicTypeSize.isAccessibilitySize ? .leading : .trailing)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(ImpactFormat.reasonTitle(r.reason)), \(r.count) \(r.count == 1 ? "item" : "items")")
        .accessibilityIdentifier(AccessibilityID.Impact.reason(r.reason.rawValue))
    }
}
