import SwiftUI

/// Moving highlight for skeletons: 1.2 s linear, repeating. Reduce Motion: static (no sweep).
struct ShimmerModifier: ViewModifier {
    @MotionReduced private var reduceMotion
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .overlay {
                if !reduceMotion {
                    GeometryReader { geo in
                        LinearGradient(colors: [.clear, Theme.Colors.surface.opacity(Theme.Motion.shimmerHighlightOpacity), .clear],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: geo.size.width * Theme.Motion.shimmerBandWidth)
                            .offset(x: phase * geo.size.width)
                    }
                    .allowsHitTesting(false)
                }
            }
            .clipped()
            .onAppear {
                guard !reduceMotion else { return }
                phase = -1
                withAnimation(.linear(duration: Theme.Motion.shimmerDuration).repeatForever(autoreverses: false)) {
                    phase = 1.4
                }
            }
    }
}

extension View {
    /// Skeleton shimmer (loading only).
    func shimmering() -> some View { modifier(ShimmerModifier()) }
}

/// Placeholder shaped like the final `ItemRow`: 40 pt avatar tile, two text bars, badge pill.
struct SkeletonRow: View {
    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            RoundedRectangle(cornerRadius: Theme.Radius.avatar, style: .continuous).fill(fill)
                .frame(width: Theme.Size.avatar, height: Theme.Size.avatar)
            VStack(alignment: .leading, spacing: Theme.Spacing.stack) {
                RoundedRectangle(cornerRadius: Theme.Radius.bar).fill(fill).frame(width: Theme.Size.skeletonTitle.width, height: Theme.Size.skeletonTitle.height)
                RoundedRectangle(cornerRadius: Theme.Radius.bar).fill(fill).frame(width: Theme.Size.skeletonMeta.width, height: Theme.Size.skeletonMeta.height)
            }
            Spacer(minLength: 0)
            RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous).fill(fill)
                .frame(width: Theme.Size.skeletonBadge.width, height: Theme.Size.skeletonBadge.height)
        }
        .padding(.horizontal, Theme.Spacing.m)
        .padding(.vertical, Theme.Spacing.sm)
        .background(Theme.Colors.surface)
        .shimmering()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
    }

    private var fill: Color { Theme.Colors.limeTint }
}

/// A rounded card of `count` skeleton rows with hairline dividers: a single accessibility element
/// "Loading" with id `<screen>.loading` (no per-row ids).
/// Callers cross-fade it to content with `.motionTransition(.opacity)` / `Theme.Motion.quick`.
struct SkeletonList: View {
    let screen: String
    var count = 5

    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<count, id: \.self) { i in
                SkeletonRow()
                if i < count - 1 { Divider().overlay(Theme.Colors.hairline) }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        // One VoiceOver stop for the whole list, not one per row.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
        .accessibilityIdentifier(AccessibilityID.State.loading(screen))
    }
}
