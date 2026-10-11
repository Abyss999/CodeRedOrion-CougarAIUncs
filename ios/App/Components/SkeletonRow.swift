import SwiftUI

/// Moving highlight for skeletons: 1.2 s linear, repeating. Reduce Motion: static (no sweep).
struct ShimmerModifier: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var phase: CGFloat = -1

    func body(content: Content) -> some View {
        content
            .overlay {
                if !reduceMotion {
                    GeometryReader { geo in
                        LinearGradient(colors: [.clear, Theme.Colors.surface.opacity(0.65), .clear],
                                       startPoint: .leading, endPoint: .trailing)
                            .frame(width: geo.size.width * 0.6)
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
            RoundedRectangle(cornerRadius: 12, style: .continuous).fill(fill)
                .frame(width: Theme.Size.avatar, height: Theme.Size.avatar)
            VStack(alignment: .leading, spacing: 6) {
                RoundedRectangle(cornerRadius: 4).fill(fill).frame(width: 140, height: 14)
                RoundedRectangle(cornerRadius: 4).fill(fill).frame(width: 96, height: 11)
            }
            Spacer(minLength: 0)
            RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous).fill(fill)
                .frame(width: 56, height: 24)
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

/// A rounded card of `count` skeleton rows with hairline dividers (`<screen>.loading`).
/// Callers cross-fade it to content with `.motionTransition(.opacity)` / `Theme.Motion.quick`.
struct SkeletonList: View {
    let screen: String
    var count = 5

    var body: some View {
        VStack(spacing: 0) {
            ForEach(0..<count, id: \.self) { i in
                SkeletonRow().accessibilityIdentifier(AccessibilityID.State.skeletonRow(screen, i))
                if i < count - 1 { Divider().overlay(Theme.Colors.hairline) }
            }
        }
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.State.loading(screen))
    }
}
