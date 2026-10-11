import SwiftUI

/// One-tap waste-reason tile (`WasteReasonGrid`). Outlined on `surface`; when tapped it
/// highlights (`limeTint` fill, 2 pt `forest` border, checkmark) with a `quick` colour change.
struct RemoveReasonTile: View {
    let reason: WasteReason
    let isChosen: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                HStack(alignment: .top, spacing: Theme.Spacing.xs) {
                    Text(reason.tileTitle)
                        .font(Theme.Fonts.cardHeading)
                        .foregroundStyle(Theme.Colors.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if isChosen {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(Theme.Colors.forest)
                            .accessibilityHidden(true)
                    }
                }
                Spacer(minLength: 0)
                Text(reason.hint)
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(Theme.Spacing.tileInner)
            .frame(maxWidth: .infinity, minHeight: Theme.Size.reasonTile, alignment: .topLeading)
            .background(isChosen ? Theme.Colors.limeTint : Theme.Colors.surface,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
                    .strokeBorder(isChosen ? Theme.Colors.forest : Theme.Colors.border,
                                  lineWidth: isChosen ? Theme.Stroke.selected : Theme.Stroke.hairline)
            }
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .motionAnimation(Theme.Motion.quick, value: isChosen)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(reason.tileTitle)
        .accessibilityHint(reason.hint)
        .accessibilityAddTraits(isChosen ? [.isSelected] : [])
        .accessibilityIdentifier(AccessibilityID.Remove.reason(reason.rawValue))
    }
}
