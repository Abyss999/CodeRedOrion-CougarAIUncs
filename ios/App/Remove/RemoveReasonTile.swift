import SwiftUI

/// One row of the waste-reason list (`RemoveReason` artboard): a 40 pt `limeTint` icon tile and the
/// reason, 68 pt tall. When tapped it shows a checkmark with a `quick` change.
struct RemoveReasonTile: View {
    let reason: WasteReason
    let isChosen: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.tileInner) {
                RoundedRectangle(cornerRadius: Theme.Radius.avatar, style: .continuous)
                    .fill(Theme.Colors.limeTint)
                    .frame(width: Theme.Size.avatar, height: Theme.Size.avatar)
                    .overlay {
                        Image(systemName: reason.symbol)
                            .font(Theme.Fonts.rowTitle)
                            .foregroundStyle(Theme.Colors.forest)
                    }
                    .accessibilityHidden(true)
                Text(reason.tileTitle)
                    .font(Theme.Fonts.tileTitle)
                    .foregroundStyle(Theme.Colors.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if isChosen {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Theme.Colors.forest)
                        .accessibilityHidden(true)
                }
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.vertical, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.removalOption)
            .background(isChosen ? Theme.Colors.limeTint : Color.clear)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .motionAnimation(Theme.Motion.quick, value: isChosen)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(reason.tileTitle)
        .accessibilityAddTraits(isChosen ? [.isSelected] : [])
        .accessibilityIdentifier(AccessibilityID.Remove.reason(reason.rawValue))
    }
}
