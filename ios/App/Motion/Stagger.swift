import SwiftUI
import Observation

/// Controls when staggered appearance runs. Staggers happen on **first load** or a **new result**
/// only, never on refresh: the owner (view model / screen) calls `restart()` at those moments and
/// nowhere else. Rows created or shown outside the active window just appear.
///
///     @State private var stagger = StaggerController()
///     ... after the first load / a new result arrives:  stagger.restart()
///     ForEach(Array(items.enumerated()), id: \.element.id) { i, item in
///         Row(item).staggeredAppearance(index: i, controller: stagger)
///     }
@MainActor
@Observable
final class StaggerController {
    /// Bumps on every `restart()`; rows already on screen replay when it changes.
    private(set) var generation = 0
    @ObservationIgnored private var activeUntil = Date.distantPast

    /// How long rows that appear after `restart()` still animate in.
    static var window: TimeInterval { Theme.Motion.staggerDelay(index: Theme.Motion.staggerCap) + Theme.Motion.staggerItemDuration + 0.3 }

    var isActive: Bool { Date() < activeUntil }

    func restart() {
        generation += 1
        activeUntil = Date().addingTimeInterval(Self.window)
    }
}

extension View {
    /// Fade (and rise `rise` pt) in, delayed 40 ms per index, capped at 6 items, 0.3 s per item
    /// (whole sequence <= 0.5 s). Applies to the view as **one unit** (composited first, so a
    /// composite such as a stacked bar fades and moves as a whole). Pass `step:` for chart columns
    /// (`Theme.Motion.chartStaggerStep`). Reduce Motion: a plain 0.15 s fade, no rise, no delay.
    func staggeredAppearance(index: Int, controller: StaggerController, rise: CGFloat = 0,
                             step: Double = Theme.Motion.staggerStep) -> some View {
        modifier(StaggeredAppearanceModifier(index: index, controller: controller, rise: rise, step: step))
    }

    /// Grow a composite from its baseline as ONE `scaleY` (Impact stacked bars), never per segment.
    /// Same stagger/controller rules as `staggeredAppearance`. Reduce Motion: 0.15 s fade.
    func growsFromBaseline(index: Int, controller: StaggerController,
                           step: Double = Theme.Motion.chartStaggerStep) -> some View {
        modifier(GrowFromBaselineModifier(index: index, controller: controller, step: step))
    }
}

private struct StaggeredAppearanceModifier: ViewModifier {
    @MotionReduced private var reduceMotion
    let index: Int
    let controller: StaggerController
    let rise: CGFloat
    let step: Double
    @State private var shown: Bool

    init(index: Int, controller: StaggerController, rise: CGFloat, step: Double) {
        self.index = index; self.controller = controller; self.rise = rise; self.step = step
        _shown = State(initialValue: !controller.isActive)
    }

    func body(content: Content) -> some View {
        content
            .compositingGroup()
            .opacity(shown ? 1 : 0)
            .offset(y: shown || reduceMotion ? 0 : rise)
            .onAppear { if !shown { reveal() } }
            .onChange(of: controller.generation) { _, _ in
                shown = false
                reveal()
            }
    }

    private func reveal() {
        let anim = Theme.Motion.animation(Theme.Motion.staggerItem, reduceMotion: reduceMotion)
            .delay(reduceMotion ? 0 : Theme.Motion.staggerDelay(index: index, step: step))
        withAnimation(anim) { shown = true }
    }
}

private struct GrowFromBaselineModifier: ViewModifier {
    @MotionReduced private var reduceMotion
    let index: Int
    let controller: StaggerController
    let step: Double
    @State private var shown: Bool

    init(index: Int, controller: StaggerController, step: Double) {
        self.index = index; self.controller = controller; self.step = step
        _shown = State(initialValue: !controller.isActive)
    }

    func body(content: Content) -> some View {
        content
            .compositingGroup()   // one element: segments never animate separately
            .scaleEffect(x: 1, y: shown || reduceMotion ? 1 : 0.001, anchor: .bottom)
            .opacity(shown ? 1 : 0)
            .onAppear { if !shown { reveal() } }
            .onChange(of: controller.generation) { _, _ in
                shown = false
                reveal()
            }
    }

    private func reveal() {
        let anim = Theme.Motion.animation(Theme.Motion.staggerItem, reduceMotion: reduceMotion)
            .delay(reduceMotion ? 0 : Theme.Motion.staggerDelay(index: index, step: step))
        withAnimation(anim) { shown = true }
    }
}
