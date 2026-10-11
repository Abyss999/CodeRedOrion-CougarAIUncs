import SwiftUI

/// "Used and donated": one stacked bar, labelled "19 used" and "4 donated" on two lines (round 3).
struct ImpactSplitCard: View {
    let used: Int
    let donated: Int

    var body: some View {
        ImpactCard {
            ImpactSectionTitle("Used and donated")
            bar
            VStack(alignment: .leading, spacing: Theme.Spacing.stack) {
                legend(color: Theme.Colors.chartSaved, text: "\(used) used", id: AccessibilityID.Impact.splitUsed)
                legend(color: Theme.Colors.chartDonated, text: "\(donated) donated", id: AccessibilityID.Impact.splitDonated)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Used and donated. \(used + donated) items saved: \(used) used, \(donated) donated")
        .accessibilityIdentifier(AccessibilityID.Impact.split)
    }

    private var bar: some View {
        GeometryReader { geo in
            let total = max(used + donated, 1)
            let gap: CGFloat = (used > 0 && donated > 0) ? 2 : 0
            let usable = geo.size.width - gap
            HStack(spacing: gap) {
                if used > 0 {
                    UnevenRoundedRectangle(topLeadingRadius: 11, bottomLeadingRadius: 11,
                                           bottomTrailingRadius: donated > 0 ? Theme.Radius.bar : 11,
                                           topTrailingRadius: donated > 0 ? Theme.Radius.bar : 11)
                        .fill(Theme.Colors.chartSaved)
                        .frame(width: usable * CGFloat(used) / CGFloat(total))
                }
                if donated > 0 {
                    UnevenRoundedRectangle(topLeadingRadius: used > 0 ? Theme.Radius.bar : 11,
                                           bottomLeadingRadius: used > 0 ? Theme.Radius.bar : 11,
                                           bottomTrailingRadius: 11, topTrailingRadius: 11)
                        .fill(Theme.Colors.chartDonated)
                        .frame(width: usable * CGFloat(donated) / CGFloat(total))
                }
            }
        }
        .frame(height: 22)
        .accessibilityHidden(true)
    }

    private func legend(color: Color, text: String, id: String) -> some View {
        HStack(spacing: Theme.Spacing.s) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 10, height: 10)
            Text(text).font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.ink)
        }
        .accessibilityIdentifier(id)
    }
}
