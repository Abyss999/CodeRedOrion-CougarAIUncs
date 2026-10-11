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

        /// 40 ms per item, capped at 8 items.
        static let staggerStep: Double = 0.040
        static let staggerCap = 8
        /// Skeleton shimmer period (linear, repeating).
        static let shimmerDuration: Double = 1.2
        /// One-shot animations finish within this.
        static let oneShotLimit: Double = 0.5

        /// Delay for the item at `index`: 40 ms per item, capped at 8 items.
        static func staggerDelay(index: Int, step: Double = staggerStep) -> Double {
            Double(min(max(index, 0), staggerCap)) * step
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
