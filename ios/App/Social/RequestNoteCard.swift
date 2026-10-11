import SwiftUI

/// A sticky note on the requests board: source, text clamped to 4 lines with "more", who/when and an
/// "Offer" pill (44 pt hit area). Your own notes have no Offer.
struct RequestNoteCard: View {
    let request: HelpRequest
    let index: Int
    var tilted = true
    let onOffer: () -> Void
    @State private var expanded = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private static let tilts: [Double] = [-1.2, 0.8, -0.6, 1.0]
    private var long: Bool { request.text.count > (dynamicTypeSize.isAccessibilitySize ? 160 : 80) }
    private var firstName: String { SocialText.firstName(request.authorName) }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                Text(request.sourceLabel)
                    .font(Theme.Fonts.groupHeader)
                    .tracking(Theme.Tracking.groupHeader)
                    .foregroundStyle(Theme.Colors.forest)
                    .lineLimit(1)
                Text(request.text)
                    .font(Theme.Fonts.body)
                    .foregroundStyle(Theme.Colors.ink)
                    .lineLimit(expanded ? nil : 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .combine)
            .accessibilityLabel("\(request.source.type == .me ? "Your request" : "Request from \(firstName)") in \(request.sourceLabel): \(request.text)")
            if long {
                Button { withAnimation(Theme.Motion.quick) { expanded.toggle() } } label: {
                    Text(expanded ? "less" : "more")
                        .font(Theme.Fonts.badge)
                        .foregroundStyle(Theme.Colors.forest)
                        .frame(minWidth: Theme.Size.minTouch, minHeight: Theme.Size.minTouch, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel(expanded ? "Show less" : "Show the whole request")
                .accessibilityIdentifier(AccessibilityID.Social.noteMore(request.id))
            }
            Spacer(minLength: 0)
            HStack {
                Text(request.whoLine).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                Spacer(minLength: Theme.Spacing.xs)
                if request.source.type != .me {
                    Button(action: onOffer) {
                        Text("Offer")
                            .font(Theme.Fonts.badge)
                            .foregroundStyle(Theme.Colors.onForest)
                            .padding(.horizontal, Theme.Spacing.sm).padding(.vertical, Theme.Spacing.xs)
                            .background(Theme.Colors.forest, in: Capsule())
                            .frame(minWidth: Theme.Size.minTouch, minHeight: Theme.Size.minTouch)
                            .contentShape(Rectangle())
                    }
                    .accessibilityLabel("Offer to \(firstName)")
                    .accessibilityIdentifier(AccessibilityID.Social.offer(request.id))
                }
            }
        }
        .padding(Theme.Spacing.sm)
        .frame(maxWidth: .infinity, minHeight: Theme.Size.noteMin, alignment: .topLeading)
        .background(index.isMultiple(of: 3) ? Theme.Colors.noteYellow : Theme.Colors.noteLime,
                    in: UnevenRoundedRectangle(topLeadingRadius: Theme.Radius.bar, bottomLeadingRadius: Theme.Radius.bar, bottomTrailingRadius: Theme.Radius.card,
                                               topTrailingRadius: Theme.Radius.bar, style: .continuous))
        .rotationEffect(.degrees(tilted ? Self.tilts[index % Self.tilts.count] : 0))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Social.note(request.id))
    }
}
