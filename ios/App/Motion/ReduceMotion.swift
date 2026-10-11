import SwiftUI

/// `withAnimation` that honours Reduce Motion. Pass `@Environment(\.accessibilityReduceMotion)`.
@MainActor
func withMotion<R>(_ animation: Animation = Theme.Motion.standard, reduceMotion: Bool,
                   _ body: () throws -> R) rethrows -> R {
    try withAnimation(Theme.Motion.animation(animation, reduceMotion: reduceMotion), body)
}

extension View {
    /// `.animation(_:value:)` through the Reduce Motion choke point.
    func motionAnimation<V: Equatable>(_ animation: Animation = Theme.Motion.standard, value: V) -> some View {
        modifier(MotionAnimationModifier(animation: animation, value: value))
    }

    /// `.transition` that becomes an opacity fade under Reduce Motion.
    func motionTransition(_ transition: AnyTransition) -> some View {
        modifier(MotionTransitionModifier(transition: transition))
    }

    /// Wrong-password style shake: 3 x 6 pt over 0.3 s. Reduce Motion: a brief opacity dip instead.
    /// Fire it by changing `trigger`.
    func shake<T: Equatable>(trigger: T) -> some View {
        modifier(ShakeModifier(trigger: trigger))
    }

    /// Scale-in (0.8 -> 1) for a tapped tile's checkmark. Reduce Motion: fade only.
    func checkmarkScaleIn(_ isShown: Bool) -> some View {
        modifier(CheckmarkScaleModifier(isShown: isShown))
    }

    /// Cross-fade on value change for numbers (`.numericText`); Reduce Motion: plain `quick` fade.
    func numericChange<V: Equatable>(value: V) -> some View {
        modifier(NumericChangeModifier(value: value))
    }
}

private struct MotionAnimationModifier<V: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let animation: Animation
    let value: V
    func body(content: Content) -> some View {
        content.animation(Theme.Motion.animation(animation, reduceMotion: reduceMotion), value: value)
    }
}

private struct MotionTransitionModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let transition: AnyTransition
    func body(content: Content) -> some View {
        content.transition(Theme.Motion.transition(transition, reduceMotion: reduceMotion))
    }
}

private struct ShakeModifier<T: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let trigger: T
    func body(content: Content) -> some View {
        if reduceMotion {
            content.keyframeAnimator(initialValue: 1.0, trigger: trigger) { view, opacity in
                view.opacity(opacity)
            } keyframes: { _ in
                KeyframeTrack {
                    LinearKeyframe(0.5, duration: 0.075)
                    LinearKeyframe(1.0, duration: 0.075)
                }
            }
        } else {
            content.keyframeAnimator(initialValue: 0.0, trigger: trigger) { view, x in
                view.offset(x: x)
            } keyframes: { _ in
                KeyframeTrack {
                    // 3 oscillations x 6 pt over 0.3 s
                    LinearKeyframe(6.0, duration: 0.05)
                    LinearKeyframe(-6.0, duration: 0.05)
                    LinearKeyframe(6.0, duration: 0.05)
                    LinearKeyframe(-6.0, duration: 0.05)
                    LinearKeyframe(6.0, duration: 0.05)
                    LinearKeyframe(0.0, duration: 0.05)
                }
            }
        }
    }
}

private struct CheckmarkScaleModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let isShown: Bool
    func body(content: Content) -> some View {
        content
            .scaleEffect(reduceMotion || isShown ? 1 : 0.8)
            .opacity(isShown ? 1 : 0)
            .animation(Theme.Motion.animation(Theme.Motion.quick, reduceMotion: reduceMotion), value: isShown)
    }
}

private struct NumericChangeModifier<V: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let value: V
    func body(content: Content) -> some View {
        content
            .contentTransition(reduceMotion ? .opacity : .numericText())
            .animation(Theme.Motion.animation(Theme.Motion.standard, reduceMotion: reduceMotion), value: value)
    }
}

/// Number that counts up to `value` (Impact hero). Reduce Motion: shows the final value immediately.
/// Counts again whenever `value` changes (range change). Finishes within 0.5 s.
struct CountUpText: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let value: Double
    var format: (Double) -> String = { String(format: "%.1f", $0) }
    @State private var shown: Double?

    var body: some View {
        Text(format(shown ?? (reduceMotion ? value : 0)))
            .contentTransition(.numericText())
            .monospacedDigit()
            .accessibilityLabel(format(value))
            .task(id: value) { await run() }
    }

    private func run() async {
        if reduceMotion { shown = value; return }
        let start = shown ?? 0, steps = 20
        for i in 1...steps {
            try? await Task.sleep(for: .milliseconds(22))
            if Task.isCancelled { return }
            let t = Double(i) / Double(steps)
            shown = start + (value - start) * (1 - pow(1 - t, 3))
        }
        shown = value
    }
}
