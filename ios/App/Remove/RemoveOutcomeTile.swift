import SwiftUI

extension RemoveOutcome {
    var tileTitle: String {
        switch self {
        case .used: "Used it"
        case .donated: "Gave it away"
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

/// One 68 pt outcome tile (`RemoveSheet` artboard). *Used it* is filled forest; the others are
/// outlined. A checkmark scales in (0.8 → 1, `quick`; a fade under Reduce Motion) once tapped.
struct RemoveOutcomeTile: View {
    let outcome: RemoveOutcome
    let subtitle: String
    let isChosen: Bool
    /// Shows a chevron: this tile leads to another step instead of finishing.
    var leadsOn = false
    let action: () -> Void

    private var filled: Bool { outcome == .used }
    private var titleInk: Color { filled ? Theme.Colors.onForest : Theme.Colors.ink }
    private var subtitleInk: Color { filled ? Theme.Colors.onForestMuted : Theme.Colors.muted }
    private var chipFill: Color {
        switch outcome {
        case .used: Theme.Colors.forestChip
        case .donated: Theme.Colors.limeTint
        case .thrownOut: Theme.Colors.urgentBg
        }
    }
    private var chipInk: Color {
        switch outcome {
        case .used: Theme.Colors.lime
        case .donated: Theme.Colors.forest
        case .thrownOut: Theme.Colors.urgentInk
        }
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
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(outcome.tileTitle)
                        .font(Theme.Fonts.tileTitle)
                        .foregroundStyle(titleInk)
                    Text(subtitle)
                        .font(Theme.Fonts.meta)
                        .foregroundStyle(subtitleInk)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                trailing
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.vertical, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.removalOption)
            .background(filled ? Theme.Colors.forest : Theme.Colors.surface,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .overlay {
                if !filled {
                    RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
                        .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline)
                }
            }
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(outcome.tileTitle)
        .accessibilityHint(subtitle)
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
                .foregroundStyle(filled ? Theme.Colors.lime : Theme.Colors.forest)
                .checkmarkScaleIn(isChosen)
                .accessibilityHidden(true)
                .accessibilityIdentifier(AccessibilityID.Remove.checkmark(outcome.rawValue))
        }
    }
}
