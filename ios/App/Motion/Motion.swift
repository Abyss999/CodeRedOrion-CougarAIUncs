import SwiftUI

extension Theme {
    /// Motion tokens from docs/design/MOTION.md. Views never write ad-hoc animations: they use
    /// these tokens through the Reduce Motion helpers in `ReduceMotion.swift`.
    enum Motion {
        /// Taps, toggles, checkbox and colour changes.
        static let quick: Animation = .easeOut(duration: 0.15)
        /// Rows inserting or removing, expanding, layout changes.
        static let standard: Animation = .spring(response: 0.35, dampingFraction: 0.85)
        /// One moment per screen at most: a success, a new note landing.
        static let emphasized: Animation = .spring(response: 0.5, dampingFraction: 0.75)

        /// 40 ms per list item, capped at 6 items: 5 x 40 ms of delay + a 0.3 s item = 0.5 s.
        /// Items past the 6th appear together with the 6th.
        static let staggerStep: Double = 0.040
        static let staggerCap = 6
        /// Chart columns stagger tighter (20 ms; Impact bars).
        static let chartStaggerStep: Double = 0.020
        /// Per-item animation inside a stagger (0.3 s, so the whole sequence ends by 0.5 s).
        static let staggerItem: Animation = .easeOut(duration: 0.3)
        static let staggerItemDuration: Double = 0.3
        /// A new item inserted at the top of a list: moves down 8 pt and fades in over 0.3 s.
        static let listInsert: Animation = .easeOut(duration: 0.3)
        static let listInsertOffset: CGFloat = 8
        /// Listening pulse (loops): ring grows up to 8 pt, peak 30% opacity, 1.6 s period.
        static let pulseGrowth: CGFloat = 8
        static let pulsePeakOpacity: Double = 0.30
        static let pulsePeriod: Double = 1.6
        /// Stroke width of the animated pulse ring.
        static let pulseLineWidth: CGFloat = 2
        /// Reduce Motion: static ring, 4 pt at 25% opacity.
        static let pulseStaticWidth: CGFloat = 4
        static let pulseStaticOpacity: Double = 0.25
        /// Skeleton shimmer period (linear, repeating).
        static let shimmerDuration: Double = 1.2
        /// Shimmer highlight: a `surface` band at this opacity, this fraction of the row wide.
        static let shimmerHighlightOpacity: Double = 0.65
        static let shimmerBandWidth: CGFloat = 0.6
        /// One-shot animations finish within this.
        static let oneShotLimit: Double = 0.5

        /// Delay for the item at `index`: `step` per item, items past the cap share the last delay
        /// (index 5, the 6th item, is 5 x 40 ms = 0.2 s).
        static func staggerDelay(index: Int, step: Double = staggerStep) -> Double {
            Double(min(max(index, 0), staggerCap - 1)) * step
        }

        /// The one place Reduce Motion is decided for animations: with Reduce Motion on, every
        /// animation becomes the `quick` fade (callers pair it with opacity-only changes).
        static func animation(_ animation: Animation, reduceMotion: Bool) -> Animation {
            reduceMotion ? quick : animation
        }

        /// Reduce Motion substitute for a transition: fades replace moves, scales and rotations.
        static func transition(_ transition: AnyTransition, reduceMotion: Bool) -> AnyTransition {
            reduceMotion ? .opacity : transition
        }
    }
}

// MARK: - Reduce Motion source of truth

private struct ReduceMotionOverrideKey: EnvironmentKey { static let defaultValue: Bool? = nil }

extension EnvironmentValues {
    /// DEBUG/UI-test override for Reduce Motion (`-UITestReduceMotion`); nil means "use the system setting".
    var reduceMotionOverride: Bool? {
        get { self[ReduceMotionOverrideKey.self] }
        set { self[ReduceMotionOverrideKey.self] = newValue }
    }
}

/// The single read of Reduce Motion in the app: the system setting, unless `reduceMotionOverride`
/// is set at the root. All motion code uses `@MotionReduced private var reduceMotion`.
@propertyWrapper
struct MotionReduced: DynamicProperty {
    @Environment(\.accessibilityReduceMotion) private var system
    @Environment(\.reduceMotionOverride) private var override
    var wrappedValue: Bool { override ?? system }
}
