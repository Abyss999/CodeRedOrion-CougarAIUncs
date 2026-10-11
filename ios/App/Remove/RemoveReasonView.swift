import SwiftUI

extension WasteReason {
    var tileTitle: String {
        switch self {
        case .expired: "Expired"
        case .forgot: "Forgot about it"
        case .didntLike: "Didn't like it"
        case .other: "Other"
        }
    }

    var symbol: String {
        switch self {
        case .expired: "calendar.badge.exclamationmark"
        case .forgot: "clock"
        case .didntLike: "hand.thumbsdown"
        case .other: "ellipsis"
        }
    }

    /// Artboard order: Expired, Forgot, Didn't like, Other.
    static let displayOrder: [WasteReason] = [.expired, .forgot, .didntLike, .other]
}

/// Remove: waste reason (`RemoveReason` artboard, SCREENS #8), pushed natively from the remove
/// sheet: "Why was it thrown out?" over one grouped list. One tap: the row highlights, `.warning`
/// haptic, the removal (thrown_out + reason) happens at once and the sheet dismisses.
struct RemoveReasonView: View {
    let item: Item
    let onReason: (WasteReason) -> Void
    let close: () -> Void

    @State private var chosen: WasteReason?
    @State private var closeTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.sheetSection) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text("Why was it thrown out?")
                        .font(Theme.Fonts.sheetTitle)
                        .foregroundStyle(Theme.Colors.ink)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier(AccessibilityID.RemoveReason.title)
                    Text(item.name)
                        .font(Theme.Fonts.sheetMeta)
                        .foregroundStyle(Theme.Colors.muted)
                }
                VStack(spacing: 0) {
                    ForEach(Array(WasteReason.displayOrder.enumerated()), id: \.element) { index, reason in
                        RemoveReasonTile(reason: reason, isChosen: chosen == reason) { pick(reason) }
                        if index < WasteReason.displayOrder.count - 1 {
                            Theme.Colors.hairline.frame(height: Theme.Stroke.hairline)
                        }
                    }
                }
                .background(Theme.Colors.surface)
                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(AccessibilityID.RemoveReason.list)
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.s)
            .padding(.bottom, Theme.Spacing.l)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.Colors.ground)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .navigationBarBackButtonHidden(chosen != nil)
        .accessibilityIdentifier(AccessibilityID.RemoveReason.screen)
        .onDisappear { closeTask?.cancel() }
    }

    private func pick(_ reason: WasteReason) {
        guard chosen == nil else { return }
        chosen = reason
        Haptics.warning()
        onReason(reason)
        // Cancelled if the sheet goes away first, so it can't close a newer sheet.
        closeTask = Task {
            try? await Task.sleep(for: Theme.Motion.confirmHold)
            guard !Task.isCancelled else { return }
            close()
        }
    }
}
