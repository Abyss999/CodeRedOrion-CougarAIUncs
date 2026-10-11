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
    static var window: TimeInterval { Theme.Motion.staggerDelay(index: Theme.Motion.staggerCap) + 0.6 }

    var isActive: Bool { Date() < activeUntil }

    func restart() {
        generation += 1
        activeUntil = Date().addingTimeInterval(Self.window)
    }
}

extension View {
    /// Fade (and rise `rise` pt) in, delayed 40 ms per index, capped at 8 items. Reduce Motion:
    /// a plain `quick` fade, no rise, no delay.
    func staggeredAppearance(index: Int, controller: StaggerController, rise: CGFloat = 0) -> some View {
        modifier(StaggeredAppearanceModifier(index: index, controller: controller, rise: rise))
    }
}

private struct StaggeredAppearanceModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let index: Int
    let controller: StaggerController
    let rise: CGFloat
    @State private var shown: Bool

    init(index: Int, controller: StaggerController, rise: CGFloat) {
        self.index = index; self.controller = controller; self.rise = rise
        _shown = State(initialValue: !controller.isActive)
    }

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown || reduceMotion ? 0 : rise)
            .onAppear { if !shown { reveal() } }
            .onChange(of: controller.generation) { _, _ in
                shown = false
                reveal()
            }
    }

    private func reveal() {
        let anim = Theme.Motion.animation(Theme.Motion.standard, reduceMotion: reduceMotion)
            .delay(reduceMotion ? 0 : Theme.Motion.staggerDelay(index: index))
        withAnimation(anim) { shown = true }
    }
}
