import SwiftUI

/// PhotoAnalyzing: the photo, a progress indicator, "Finding your food…" and Cancel. No fake percentages.
/// The spinner loops only while analysing; with Reduce Motion it fades instead of rotating.
struct PhotoAnalyzingView: View {
    let photo: UIImage?
    let onCancel: () -> Void
    @MotionReduced private var reduceMotion
    @State private var spin = false
    @State private var fade = false
    @State private var slow = false

    var body: some View {
        VStack(spacing: Theme.Spacing.l) {
            PhotoBlock(photo: photo, height: Theme.AddFlow.analyzingPhotoHeight)
            VStack(spacing: Theme.Spacing.sm) {
                spinner
                Text("Finding your food…")
                    .font(Theme.Fonts.sheetTitle)
                    .foregroundStyle(Theme.Colors.ink)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                if slow {
                    Text("This can take a little longer.")
                        .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted)
                        .transition(.opacity)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.updatesFrequently)
            Spacer(minLength: 0)
            Button(action: onCancel) {
                Text("Cancel")
                    .font(Theme.Fonts.button)
                    .foregroundStyle(Theme.Colors.forest)
                    .padding(.horizontal, Theme.Spacing.xl - 4)
                    .frame(minHeight: Theme.Size.minTouch)
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                    .overlay { RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier(AccessibilityID.Add.analyzingCancel)
        }
        .padding(.horizontal, Theme.Spacing.gutter)
        .padding(.top, Theme.Spacing.xl).padding(.bottom, Theme.Spacing.l)
        .background {
            Theme.Colors.ground
                .accessibilityElement()
                .accessibilityLabel("Analyzing photo")
                .accessibilityIdentifier(AccessibilityID.Add.analyzing)
        }
        .task {
            try? await Task.sleep(for: Theme.AddFlow.slowNoticeAfter)
            if !Task.isCancelled { withAnimation(Theme.Motion.quick) { slow = true } }
        }
    }

    private var spinner: some View {
        ZStack {
            Circle().stroke(Theme.Colors.border, lineWidth: Theme.AddFlow.spinnerLine)
            Circle().trim(from: 0, to: 0.25)
                .stroke(Theme.Colors.forest, style: StrokeStyle(lineWidth: Theme.AddFlow.spinnerLine, lineCap: .round))
                .rotationEffect(.degrees(spin ? 360 : 0))
        }
        .frame(width: Theme.AddFlow.spinner, height: Theme.AddFlow.spinner)
        .opacity(reduceMotion ? (fade ? 0.35 : 1) : 1)
        .onAppear {
            if reduceMotion {
                withAnimation(.easeInOut(duration: 1).repeatForever(autoreverses: true)) { fade = true }
            } else {
                withAnimation(.linear(duration: 1).repeatForever(autoreverses: false)) { spin = true }
            }
        }
        .accessibilityHidden(true)
    }
}

/// The photo the person took, in a rounded block (a placeholder when there isn't one).
struct PhotoBlock: View {
    let photo: UIImage?
    let height: CGFloat

    var body: some View {
        RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
            .fill(Theme.Colors.track)
            .frame(height: height)
            .overlay {
                if let photo {
                    Image(uiImage: photo).resizable().scaledToFill().allowsHitTesting(false)
                } else {
                    Image(systemName: "camera").foregroundStyle(Theme.Colors.muted)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .contentShape(Rectangle())
            .allowsHitTesting(false)
            .accessibilityLabel("Your photo")
            .accessibilityAddTraits(.isImage)
    }
}
