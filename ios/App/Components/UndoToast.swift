import SwiftUI

/// What the toast shows and does. Create one and assign it to the binding used by `.undoToast`.
struct UndoToastItem: Identifiable {
    let id = UUID()
    var message: String
    var actionTitle = "Undo"
    /// Called when the person taps Undo (the toast dismisses itself).
    var onUndo: () -> Void
    /// Called when the time runs out without Undo, e.g. to finalise something.
    var onTimeout: () -> Void = {}
}

enum UndoToastTiming {
    static let duration: Duration = .seconds(5)
    /// MOTION.md sets 5 s and says nothing more; per HIG (time-limited UI needs extra time for
    /// assistive tech) the toast stays 3x longer while VoiceOver or Switch Control is running.
    static let assistiveDuration: Duration = .seconds(15)
}

private struct UndoWindowOverrideKey: EnvironmentKey { static let defaultValue: Duration? = nil }

extension EnvironmentValues {
    /// DEBUG/UI-test override for the Undo window (`-UITestUndoWindow <seconds>`); nil in production.
    /// When set it replaces both the 5 s and the assistive-tech 15 s windows.
    var undoWindowOverride: Duration? {
        get { self[UndoWindowOverrideKey.self] }
        set { self[UndoWindowOverrideKey.self] = newValue }
    }
}

/// Bottom toast: message, "Undo" button (44 pt target) and a 5 s progress bar.
/// Accessibility ids: `toast.undo` (container), `toast.undo.button`, `toast.undo.progress`.
struct UndoToastView: View {
    @MotionReduced private var reduceMotion
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @Environment(\.accessibilitySwitchControlEnabled) private var switchControl
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.undoWindowOverride) private var windowOverride

    let item: UndoToastItem
    let dismiss: () -> Void
    /// The countdown window, set once when the toast appears. The bar is a timer-driven
    /// `ProgressView`, so there is no per-tick @State re-render and the app can go idle.
    @State private var window: ClosedRange<Date>?

    /// At accessibility text sizes the message gets the full width with Undo below it (IOS-11), so
    /// it wraps on whole words instead of being squeezed beside the button.
    private var stacked: Bool { dynamicTypeSize.isAccessibilitySize }
    private var contentLayout: AnyLayout {
        stacked
            ? AnyLayout(VStackLayout(alignment: .trailing, spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.sm))
    }

    private var duration: Duration {
        if let windowOverride { return windowOverride }
        return (voiceOver || switchControl) ? UndoToastTiming.assistiveDuration : UndoToastTiming.duration
    }

    var body: some View {
        VStack(spacing: 0) {
            contentLayout {
                Text(item.message)
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.onForest)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(AccessibilityID.Toast.message)
                Button {
                    item.onUndo()
                    dismiss()
                } label: {
                    Text(item.actionTitle)
                        .font(Theme.Fonts.button)
                        .fixedSize()   // "Undo" never wraps or truncates
                        .foregroundStyle(Theme.Colors.onForest)
                        .padding(.horizontal, Theme.Spacing.m)
                        .frame(minHeight: Theme.Size.minTouch)
                        .background(Theme.Colors.onForest.opacity(Theme.Opacity.onForestFill), in: Capsule())
                        .contentShape(Capsule())
                }
                .accessibilityIdentifier(AccessibilityID.Toast.button)
            }
            .padding(.leading, Theme.Spacing.m)
            .padding(.trailing, Theme.Spacing.s)
            .padding(.vertical, stacked ? Theme.Spacing.s : Theme.Spacing.xs)

            // A timer indicator, not decorative motion, so it also runs under Reduce Motion.
            Group {
                if let window {
                    ProgressView(timerInterval: window, countsDown: true) {
                        EmptyView()
                    } currentValueLabel: {
                        EmptyView()
                    }
                    .progressViewStyle(.linear)
                    .tint(Theme.Colors.onForestMuted)
                } else {
                    Color.clear
                }
            }
            .frame(height: Theme.Size.toastProgress)
            .clipped()
            .accessibilityHidden(true)
            .accessibilityIdentifier(AccessibilityID.Toast.progress)
        }
        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .shadow(color: Theme.Colors.scrim.opacity(Theme.Shadow.toast.opacity), radius: Theme.Shadow.toast.radius, y: Theme.Shadow.toast.y)
        .padding(.horizontal, Theme.Spacing.gutter)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Toast.container)
        .accessibilityAction(named: item.actionTitle) { item.onUndo(); dismiss() }
        .task(id: item.id) { await run() }
        .onAppear {
            AccessibilityNotification.Announcement("\(item.message). \(item.actionTitle) available.").post()
        }
    }

    /// One sleep for the whole window (no polling), then time out. The countdown starts when the
    /// toast appears; callers show it only once it's visible (FridgeView sets it after the sheet dismisses).
    private func run() async {
        let total = duration
        let start = Date()
        let c = total.components
        window = start...start.addingTimeInterval(Double(c.seconds) + Double(c.attoseconds) / 1e18)
        try? await Task.sleep(for: total)
        guard !Task.isCancelled else { return }
        item.onTimeout()
        dismiss()
    }
}

extension View {
    /// Presents `UndoToastView` at the bottom while `item` is non-nil. It slides up and away
    /// (`standard`); Reduce Motion: fades. Setting a new item replaces the current one.
    func undoToast(item: Binding<UndoToastItem?>) -> some View {
        modifier(UndoToastModifier(item: item))
    }
}

private struct UndoToastModifier: ViewModifier {
    @MotionReduced private var reduceMotion
    @Binding var item: UndoToastItem?

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .bottom) {
                if let current = item {
                    UndoToastView(item: current) {
                        // Only clear if still showing the same toast.
                        if item?.id == current.id { item = nil }
                    }
                    .id(current.id)
                    .motionTransition(.move(edge: .bottom).combined(with: .opacity))
                    .padding(.bottom, Theme.Spacing.m)
                }
            }
            .motionAnimation(Theme.Motion.standard, value: item?.id)
    }
}
