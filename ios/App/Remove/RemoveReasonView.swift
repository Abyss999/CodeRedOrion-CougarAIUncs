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

    var hint: String {
        switch self {
        case .expired: "Went off before I got to it"
        case .forgot: "Lost at the back"
        case .didntLike: "Not for me"
        case .other: "Something else"
        }
    }

    /// Artboard order: Expired, Forgot, Didn't like, Other.
    static let displayOrder: [WasteReason] = [.expired, .forgot, .didntLike, .other]
}

/// Remove: waste reason (`RemoveReason` artboard, SCREENS #8), pushed natively from the remove
/// sheet. One tap: the tile highlights, `.warning` haptic, the removal (thrown_out + reason)
/// happens at once and the sheet dismisses.
struct RemoveReasonView: View {
    let item: Item
    let onReason: (WasteReason) -> Void
    let close: () -> Void

    @State private var chosen: WasteReason?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var columns: [GridItem] {
        let count = dynamicTypeSize.isAccessibilitySize ? 1 : 2
        return Array(repeating: GridItem(.flexible(), spacing: Theme.Spacing.tileGap, alignment: .top), count: count)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.sheetSection) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text("Why did it go?")
                        .font(Theme.Fonts.sheetTitle)
                        .foregroundStyle(Theme.Colors.ink)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityIdentifier(AccessibilityID.RemoveReason.title)
                    Text("\(item.name) · one tap and you're done")
                        .font(Theme.Fonts.sheetMeta)
                        .foregroundStyle(Theme.Colors.muted)
                }
                LazyVGrid(columns: columns, spacing: Theme.Spacing.tileGap) {
                    ForEach(WasteReason.displayOrder, id: \.self) { reason in
                        RemoveReasonTile(reason: reason, isChosen: chosen == reason) { pick(reason) }
                    }
                }
                Text("Your reasons shape your tips, so next time we can remind you sooner.")
                    .font(Theme.Fonts.callout)
                    .foregroundStyle(Theme.Colors.inkSecondary)
                    .padding(.horizontal, Theme.Spacing.tileInner)
                    .padding(.vertical, Theme.Spacing.sm)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                    .accessibilityIdentifier(AccessibilityID.RemoveReason.tip)
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.bottom, Theme.Spacing.l)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.Colors.ground)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.visible, for: .navigationBar)
        .accessibilityIdentifier(AccessibilityID.RemoveReason.screen)
    }

    private func pick(_ reason: WasteReason) {
        guard chosen == nil else { return }
        chosen = reason
        Haptics.warning()
        onReason(reason)
        Task {
            try? await Task.sleep(for: Theme.Motion.confirmHold)
            close()
        }
    }
}
