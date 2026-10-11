import SwiftUI

/// Soft pulsing ring around the mic button while listening: grows up to 8 pt, peaks at 30%
/// opacity, 1.6 s period (0.6 Hz, far below flash thresholds). Reduce Motion: a static 4 pt ring at 25%.
/// Size it to the control it surrounds: `ListeningPulse(diameter: 64)` draws outside that circle.
/// Id: `listening.pulse` (present only while shown; hidden from VoiceOver, which hears "Listening" from the control).
struct ListeningPulse: View {
    @MotionReduced private var reduceMotion
    var diameter: CGFloat = 64
    var color: Color = Theme.Colors.forest

    var body: some View {
        Group {
            if reduceMotion {
                Circle()
                    .strokeBorder(color.opacity(Theme.Motion.pulseStaticOpacity), lineWidth: Theme.Motion.pulseStaticWidth)
                    .frame(width: diameter + Theme.Motion.pulseStaticWidth * 2, height: diameter + Theme.Motion.pulseStaticWidth * 2)
            } else {
                TimelineView(.animation) { context in
                    let t = context.date.timeIntervalSinceReferenceDate
                        .truncatingRemainder(dividingBy: Theme.Motion.pulsePeriod) / Theme.Motion.pulsePeriod
                    let grow = Theme.Motion.pulseGrowth * t
                    Circle()
                        .stroke(color.opacity(Theme.Motion.pulsePeakOpacity * sin(.pi * t)), lineWidth: Theme.Motion.pulseLineWidth)
                        .frame(width: diameter + grow * 2, height: diameter + grow * 2)
                }
            }
        }
        .frame(width: diameter + Theme.Motion.pulseGrowth * 2, height: diameter + Theme.Motion.pulseGrowth * 2)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
        .accessibilityIdentifier(AccessibilityID.Listening.pulse)
    }
}
