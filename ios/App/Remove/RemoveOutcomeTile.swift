import SwiftUI

extension RemoveOutcome {
    var tileTitle: String {
        switch self {
        case .used: "Used it"
        case .donated: "Shared it"
        case .thrownOut: "Threw it away"
        }
    }

    var symbol: String {
        switch self {
        case .used: "checkmark"
        case .donated: "gift"
        case .thrownOut: "trash"
        }
    }
}

/// One 68 pt outcome tile (`RemoveSheet` artboard): icon chip and title, no caption. Outlined on
/// `surface`; once chosen it turns `limeTint` with a 2 pt `forest` border, a filled chip and a
/// checkmark that scales in (0.8 → 1, `quick`; a fade under Reduce Motion).
struct RemoveOutcomeTile: View {
    let outcome: RemoveOutcome
    let isChosen: Bool
    /// Shows a chevron: this tile leads to another step instead of finishing.
    var leadsOn = false
    let action: () -> Void

    private var chipFill: Color {
        if isChosen { return Theme.Colors.forest }
        return outcome == .thrownOut ? Theme.Colors.urgentBg : Theme.Colors.limeTint
    }
    private var chipInk: Color {
        if isChosen { return Theme.Colors.lime }
        return outcome == .thrownOut ? Theme.Colors.urgentInk : Theme.Colors.forest
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.tileInner) {
                RoundedRectangle(cornerRadius: Theme.Radius.avatar, style: .continuous)
                    .fill(chipFill)
                    .frame(width: Theme.Size.avatar, height: Theme.Size.avatar)
                    .overlay {
                        Image(systemName: outcome.symbol)
                            .font(Theme.Fonts.button)
                            .foregroundStyle(chipInk)
                    }
                    .accessibilityHidden(true)
                Text(outcome.tileTitle)
                    .font(Theme.Fonts.tileTitle)
                    .foregroundStyle(Theme.Colors.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                trailing
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.vertical, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.removalOption)
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
        .accessibilityLabel(outcome.tileTitle)
        .accessibilityAddTraits(isChosen ? [.isSelected] : [])
        .accessibilityIdentifier(AccessibilityID.Remove.outcome(outcome.rawValue))
    }

    @ViewBuilder private var trailing: some View {
        if leadsOn {
            Image(systemName: "chevron.right")
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.muted)
                .accessibilityHidden(true)
        } else {
            Image(systemName: "checkmark.circle.fill")
                .resizable()
                .scaledToFit()
                .frame(width: Theme.Size.tileCheckmark, height: Theme.Size.tileCheckmark)
                .foregroundStyle(Theme.Colors.forest)
                .checkmarkScaleIn(isChosen)
                .accessibilityHidden(true)
                .accessibilityIdentifier(AccessibilityID.Remove.checkmark(outcome.rawValue))
        }
    }
}
