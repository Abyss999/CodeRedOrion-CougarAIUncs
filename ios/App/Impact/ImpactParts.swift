import SwiftUI

extension Theme.Colors {
    /// "Donated" segment of the Impact split bar (ImpactRange artboard #8FB43A; dark = forestMid's dark).
    /// Not in DESIGN_SYSTEM.md yet; the orchestrator adds it.
    static let chartDonated = Color(light: 0x8FB43A, dark: 0x8FB45A)
}

/// Card surface shared by the Impact sections.
struct ImpactCard<Content: View>: View {
    var spacing: CGFloat = Theme.Spacing.sm
    @ViewBuilder var content: Content
    var body: some View {
        VStack(alignment: .leading, spacing: spacing) { content }
            .padding(Theme.Spacing.tileInner)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
    }
}

struct ImpactSectionTitle: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text)
            .font(Theme.Fonts.cardHeading)
            .foregroundStyle(Theme.Colors.ink)
            .accessibilityAddTraits(.isHeader)
    }
}

/// "Up 6.2 lb vs previous": an arrow plus words, never colour alone. Squeezed tiles fall back to the
/// chip over a muted "vs previous" caption instead of wrapping inside the pill.
struct ImpactDeltaChip: View {
    let delta: ImpactFormat.Delta
    /// Words after the delta ("vs previous", "vs previous 30 days").
    let suffix: String
    var onForest = false
    var identifier: String?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        Group {
            if onForest || dynamicTypeSize.isAccessibilitySize {
                chip("\(delta.text) \(suffix)")
            } else {
                ViewThatFits(in: .horizontal) {
                    chip("\(delta.text) \(suffix)").fixedSize()
                    VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                        chip(delta.text).fixedSize()
                        Text(suffix).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                    }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(delta.spoken) \(suffix)")
        .modifier(OptionalIdentifier(id: identifier))
    }

    private func chip(_ text: String) -> some View {
        Label {
            Text(text)
        } icon: {
            Image(systemName: symbol).imageScale(.small).accessibilityHidden(true)
        }
        .font(Theme.Fonts.badge)
        .foregroundStyle(ink)
        .padding(.horizontal, Theme.Spacing.badgeHorizontal)
        .padding(.vertical, Theme.Spacing.xs)
        .background(fill, in: Capsule())
    }

    private var symbol: String {
        switch delta.direction {
        case .up: "arrow.up"
        case .down: "arrow.down"
        case .same: "equal"
        }
    }
    private var ink: Color { onForest ? Theme.Colors.onForest : Theme.Colors.forest }
    private var fill: Color { onForest ? Theme.Colors.onForest.opacity(Theme.Opacity.onForestFill) : Theme.Colors.limeTint }
}

/// A horizontal bar: `fraction` (0...1) of the track, square on the left, rounded at the end.
struct ImpactFractionBar: View {
    let fraction: Double
    let color: Color
    var height: CGFloat = 10

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                UnevenRoundedRectangle(bottomTrailingRadius: Theme.Radius.bar, topTrailingRadius: Theme.Radius.bar)
                    .fill(Theme.Colors.hairline)
                UnevenRoundedRectangle(bottomTrailingRadius: Theme.Radius.bar, topTrailingRadius: Theme.Radius.bar)
                    .fill(color)
                    .frame(width: geo.size.width * min(max(fraction, 0), 1))
            }
        }
        .frame(height: height)
        .accessibilityHidden(true)
    }
}

private struct OptionalIdentifier: ViewModifier {
    let id: String?
    func body(content: Content) -> some View {
        if let id { content.accessibilityIdentifier(id) } else { content }
    }
}
