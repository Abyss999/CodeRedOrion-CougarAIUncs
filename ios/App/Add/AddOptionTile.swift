import SwiftUI

/// How an Add tile looks and behaves.
enum AddTileState: Equatable {
    case enabled
    /// Camera access is off (CameraDenied): a disabled tile with an "Off" badge.
    case off
    /// A feature that isn't live (Receipt while OCR is down): disabled, with this badge.
    case unavailable(String)

    var isEnabled: Bool { self == .enabled }
    var badge: String? {
        switch self {
        case .enabled: nil
        case .off: "Off"
        case .unavailable(let text): text
        }
    }
}

private struct BadgePill: View {
    let text: String
    var body: some View {
        Text(text)
            .font(Theme.Fonts.badge)
            .foregroundStyle(Theme.Colors.muted)
            .padding(.horizontal, Theme.Spacing.badgeHorizontal).padding(.vertical, Theme.Spacing.xs)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
            .fixedSize()
    }
}

/// "Snap your fridge": the 88 pt forest hero.
struct HeroTile: View {
    let title: String
    let subtitle: String?
    let state: AddTileState
    let action: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        // At accessibility sizes the icon sits above the text, so the text keeps the full width.
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.sm))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.m))
        Button(action: action) {
            layout {
                Image(systemName: "camera.fill")
                    .font(.system(size: Theme.AddFlow.heroGlyph, weight: .semibold))
                    .foregroundStyle(state.isEnabled ? Theme.Colors.forest : Theme.Colors.muted)
                    .frame(width: Theme.AddFlow.heroIconTile, height: Theme.AddFlow.heroIconTile)
                    .background(state.isEnabled ? Theme.Colors.lime : Theme.Colors.surface,
                                in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text(title).font(Theme.Fonts.section)
                        .foregroundStyle(state.isEnabled ? Theme.Colors.onForest : Theme.Colors.muted)
                    if let subtitle {
                        Text(subtitle).font(Theme.Fonts.callout)
                            .foregroundStyle(state.isEnabled ? Theme.Colors.onForestMuted : Theme.Colors.muted)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let badge = state.badge { BadgePill(text: badge) }
            }
            .padding(.horizontal, Theme.Spacing.l - 6).padding(.vertical, Theme.Spacing.m)
            .frame(maxWidth: .infinity, minHeight: Theme.AddFlow.heroMinHeight, alignment: .leading)
            .background(state.isEnabled ? Theme.Colors.forest : Theme.Colors.hairline,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!state.isEnabled)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(state.isEnabled ? "\(title). \(subtitle ?? "")" : "\(title), \(state.badge ?? "")")
        .accessibilityIdentifier(AccessibilityID.Add.hero)
    }
}

/// A 2x2 option tile.
struct OptionTile: View {
    let key: String
    let symbol: String
    let title: String
    let subtitle: String?
    let state: AddTileState
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                Image(systemName: symbol)
                    .font(.system(size: Theme.AddFlow.tileGlyph, weight: .semibold))
                    .foregroundStyle(state.isEnabled ? Theme.Colors.forest : Theme.Colors.muted)
                    .frame(width: Theme.AddFlow.tileIconTile, height: Theme.AddFlow.tileIconTile)
                    .background(state.isEnabled ? Theme.Colors.limeTint : Theme.Colors.surface,
                                in: RoundedRectangle(cornerRadius: Theme.Radius.avatar, style: .continuous))
                    .accessibilityHidden(true)
                Spacer(minLength: 0)
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(title).font(Theme.Fonts.cardHeading)
                        .foregroundStyle(state.isEnabled ? Theme.Colors.ink : Theme.Colors.muted)
                    if let badge = state.badge {
                        BadgePill(text: badge)
                    } else if let subtitle {
                        Text(subtitle).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                            .multilineTextAlignment(.leading)
                    }
                }
            }
            .padding(Theme.Spacing.tileInner)
            .frame(maxWidth: .infinity, minHeight: Theme.AddFlow.tileMinHeight, alignment: .leading)
            .background(state.isEnabled ? Theme.Colors.surface : Theme.Colors.hairline,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
            .overlay {
                if state.isEnabled {
                    RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous)
                        .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(!state.isEnabled)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
        .accessibilityIdentifier(AccessibilityID.Add.tile(key))
    }

    private var label: String {
        if let badge = state.badge { return "\(title), \(badge)" }
        return [title, subtitle].compactMap { $0 }.joined(separator: ". ")
    }
}
