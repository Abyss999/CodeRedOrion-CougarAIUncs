import SwiftUI
import Charts

/// "Items per week": the last six weeks as stacked bars (saved, then thrown out on top) in Swift Charts.
///
/// Motion (MOTION.md, Impact): the whole stacked bar of each week grows from the baseline as ONE unit
/// (the saved, gap and thrown-out values scale together), 20 ms apart; each week's "saved·out" label
/// appears only after its bar has landed. One linear clock `t` (0...0.5 s) drives all of it, so the
/// sequence is done by 0.5 s. It plays once, on first load; a refresh or a range change never replays
/// it. Reduce Motion: a plain fade, no growth.
struct ImpactWeeklyChart: View {
    let weeks: [WeekCounts]
    /// True when the entrance already played (the chart is created again after a state change).
    let alreadyRevealed: Bool
    let onRevealed: () -> Void

    @MotionReduced private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var clock: Double
    @State private var visible: Bool

    init(weeks: [WeekCounts], alreadyRevealed: Bool, onRevealed: @escaping () -> Void) {
        self.weeks = weeks
        self.alreadyRevealed = alreadyRevealed
        self.onRevealed = onRevealed
        _clock = State(initialValue: alreadyRevealed ? 1 : 0)
        _visible = State(initialValue: alreadyRevealed)
    }

    var body: some View {
        ImpactCard(spacing: Theme.Spacing.sm) {
            HStack {
                ImpactSectionTitle("Items per week")
                Spacer(minLength: Theme.Spacing.s)
                legend
            }
            ChartBody(weeks: weeks, clock: clock, reduceMotion: reduceMotion)
                .frame(height: 190)
                .opacity(visible ? 1 : 0)
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                .accessibilityHidden(true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(summary)
        .accessibilityIdentifier(AccessibilityID.Impact.weekly)
        .onAppear(perform: reveal)
    }

    private var legend: some View {
        HStack(spacing: Theme.Spacing.sm) {
            key(Theme.Colors.chartSaved, "Saved")
            key(Theme.Colors.chartWasted, "Thrown out")
        }
        .accessibilityHidden(true)
    }

    private func key(_ color: Color, _ text: String) -> some View {
        HStack(spacing: Theme.Spacing.xs + 1) {
            RoundedRectangle(cornerRadius: 2).fill(color).frame(width: 10, height: 10)
            Text(text).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
        }
    }

    private var summary: String {
        let parts = weeks.map { "week of \(ImpactFormat.weekLabel($0.week)): \($0.saved) saved, \($0.wasted) thrown out" }
        return "Items per week, last six weeks. " + parts.joined(separator: "; ")
    }

    private func reveal() {
        guard !alreadyRevealed, !visible else { return }
        if reduceMotion {
            clock = 1
            withAnimation(Theme.Motion.quick) { visible = true }
        } else {
            visible = true
            withAnimation(.linear(duration: ChartBody.total)) { clock = 1 }
        }
        onRevealed()
    }
}

/// The chart itself. `clock` is animatable, so every frame of the entrance re-evaluates `body`.
private struct ChartBody: View, Animatable {
    static let barDelay = 0.05
    static let barDuration = 0.25
    static let labelDuration = 0.10
    /// Last bar lands at 0.05 + 5 x 0.02 + 0.25 = 0.40 s; its label fades in by 0.50 s.
    static let total = Theme.Motion.oneShotLimit

    let weeks: [WeekCounts]
    var clock: Double
    let reduceMotion: Bool
    var animatableData: Double {
        get { clock }
        set { clock = newValue }
    }

    private static let saved = "Saved", gap = "Gap", wasted = "Thrown out"

    var body: some View {
        let peak = Double(weeks.map { $0.saved + $0.wasted }.max() ?? 0)
        let top = max(peak + 2, 4)
        let gapUnits = top * 0.013
        Chart {
            ForEach(Array(weeks.enumerated()), id: \.element.id) { i, w in
                let s = growth(i)
                let x = ImpactFormat.weekLabel(w.week)
                BarMark(x: .value("Week", x), y: .value("Saved", Double(w.saved) * s), width: .ratio(0.72))
                    .foregroundStyle(by: .value("Series", Self.saved))
                BarMark(x: .value("Week", x), y: .value("Gap", gapUnits * s), width: .ratio(0.72))
                    .foregroundStyle(by: .value("Series", Self.gap))
                BarMark(x: .value("Week", x), y: .value("Thrown out", Double(w.wasted) * s), width: .ratio(0.72))
                    .foregroundStyle(by: .value("Series", Self.wasted))
                    .cornerRadius(Theme.Radius.bar)
                    .annotation(position: .top, spacing: Theme.Spacing.xxs) {
                        Text("\(w.saved)\u{00B7}\(w.wasted)")
                            .font(Theme.Fonts.meta.weight(.semibold))
                            .foregroundStyle(Theme.Colors.inkSecondary)
                            .fixedSize()
                            .opacity(labelOpacity(i))
                    }
            }
        }
        .chartForegroundStyleScale([Self.saved: Theme.Colors.chartSaved, Self.gap: Color.clear, Self.wasted: Theme.Colors.chartWasted])
        .chartLegend(.hidden)
        .chartYScale(domain: 0...top)
        .chartYAxis(.hidden)
        .chartXAxis {
            AxisMarks { _ in
                AxisValueLabel().font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
            }
        }
        .chartPlotStyle { plot in
            plot.overlay(alignment: .bottom) { Rectangle().fill(Theme.Colors.hairline).frame(height: 1) }
        }
    }

    /// 0...1 height factor for week `i`: staggered by 20 ms, eased out. Reduce Motion: always 1.
    private func growth(_ i: Int) -> Double {
        if reduceMotion { return 1 }
        let elapsed = clock * Self.total - Self.barDelay - Double(i) * Theme.Motion.chartStaggerStep
        let x = min(max(elapsed / Self.barDuration, 0), 1)
        return max(1 - pow(1 - x, 3), 0.0001)
    }

    /// A label shows only once its own bar has landed, then fades in over 0.1 s.
    private func labelOpacity(_ i: Int) -> Double {
        if reduceMotion { return 1 }
        let landed = Self.barDelay + Double(i) * Theme.Motion.chartStaggerStep + Self.barDuration
        let start = max(landed, Self.total - Self.labelDuration)
        return min(max((clock * Self.total - start) / Self.labelDuration, 0), 1)
    }
}
