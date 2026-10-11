import SwiftUI

/// Who a request is posted to: your friends and/or any of your groups. At least one is required.
struct AudienceSelection: Hashable, Sendable {
    var friends = false
    var groupIds: Set<String> = []

    var isEmpty: Bool { !friends && groupIds.isEmpty }
    /// `group_ids` for `POST /requests`, in the order of `groups` so the body is stable.
    func orderedGroupIds(in groups: [SharingGroup]) -> [String] { groups.map(\.id).filter(groupIds.contains) }
}

/// Multi-select checklist: a Friends row, then one row per group. Each row is a 44 pt+ toggle that
/// reads as "selected / not selected" to VoiceOver and shows a checkmark, so colour is not the only cue.
struct AudienceChecklist: View {
    let groups: [SharingGroup]
    var friendCount: Int?
    @Binding var selection: AudienceSelection
    /// Shown under the list while nothing is chosen.
    var emptyHint = "Choose at least one."

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            row(id: AccessibilityID.Audience.friends, title: "Friends",
                subtitle: friendCount.map { $0 == 1 ? "1 friend" : "\($0) friends" },
                systemImage: "person.2.fill", isOn: selection.friends) { selection.friends.toggle() }
            ForEach(groups) { g in
                row(id: AccessibilityID.Audience.group(g.id), title: g.name,
                    subtitle: g.memberCount == 1 ? "1 member" : "\(g.memberCount) members",
                    systemImage: "house.fill", isOn: selection.groupIds.contains(g.id)) {
                    if selection.groupIds.contains(g.id) { selection.groupIds.remove(g.id) } else { selection.groupIds.insert(g.id) }
                }
            }
            if selection.isEmpty {
                Text(emptyHint)
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.muted)
                    .accessibilityIdentifier(AccessibilityID.Audience.hint)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Audience.list)
    }

    private func row(id: String, title: String, subtitle: String?, systemImage: String, isOn: Bool,
                     action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: systemImage)
                    .foregroundStyle(Theme.Colors.forestMid)
                    .frame(width: Theme.Size.avatarGlyph)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(title).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    if let subtitle { Text(subtitle).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted) }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: isOn ? "checkmark.square.fill" : "square")
                    .font(Theme.Fonts.sheetTitle)
                    .foregroundStyle(isOn ? Theme.Colors.forest : Theme.Colors.muted)
                    .accessibilityHidden(true)
            }
            .padding(.horizontal, Theme.Spacing.sm)
            .padding(.vertical, Theme.Spacing.s)
            .frame(minHeight: Theme.Size.minTouch)
            .background(isOn ? Theme.Colors.limeTint : Theme.Colors.surface,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous)
                    .strokeBorder(isOn ? Theme.Colors.forest : Theme.Colors.border,
                                  lineWidth: isOn ? Theme.Stroke.selected : Theme.Stroke.hairline)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityValue(isOn ? "Selected" : "Not selected")
        .accessibilityAddTraits(isOn ? [.isSelected] : [])
        .accessibilityIdentifier(id)
    }
}
