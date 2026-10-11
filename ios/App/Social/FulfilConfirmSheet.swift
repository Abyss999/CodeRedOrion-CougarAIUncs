import SwiftUI

/// `FulfilConfirm`: "Tell Marcus you have it?" The note comes off the board when confirmed.
struct FulfilConfirmSheet: View {
    let request: HelpRequest
    let confirm: () async throws -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var busy = false
    @State private var error: String?

    private var firstName: String { SocialText.firstName(request.authorName) }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                Text("Tell \(firstName) you have it?")
                    .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                    Text(request.sourceLabel).font(Theme.Fonts.groupHeader).tracking(Theme.Tracking.groupHeader)
                        .foregroundStyle(Theme.Colors.forest)
                    Text(request.text).font(Theme.Fonts.body).foregroundStyle(Theme.Colors.ink)
                    Text(request.whoLine).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                }
                .padding(Theme.Spacing.sm)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Theme.Colors.noteYellow, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Request from \(firstName) in \(request.sourceLabel): \(request.text)")
                VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                    line("eye", "\(firstName) sees that you have it")
                    line("note.text", "The note comes off the board")
                    line("hand.raised", "You and \(firstName) sort out the handoff")
                }
                if let error {
                    BannerView(style: .error, message: error, identifiers: .init(container: AccessibilityID.Fulfil.banner), horizontalInset: 0)
                }
                Button {
                    Task {
                        busy = true; error = nil
                        do { try await confirm(); dismiss() } catch { self.error = error.localizedDescription; Haptics.error() }
                        busy = false
                    }
                } label: {
                    Group { if busy { ProgressView() } else { Text("I have it") } }
                        .font(Theme.Fonts.button)
                        .foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
                        .contentShape(Rectangle())
                }
                .disabled(busy)
                .accessibilityIdentifier(AccessibilityID.Fulfil.confirm)
                Button("Cancel") { dismiss() }
                    .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.forest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.sheetTextButton)
                    .contentShape(Rectangle())
                    .accessibilityIdentifier(AccessibilityID.Fulfil.cancel)
            }
            .padding(Theme.Spacing.gutter)
        }
        .background(Theme.Colors.ground.ignoresSafeArea())
        .accessibilityIdentifier(AccessibilityID.Fulfil.sheet)
    }

    private func line(_ symbol: String, _ text: String) -> some View {
        Label {
            Text(text).font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
        } icon: {
            Image(systemName: symbol).foregroundStyle(Theme.Colors.forestMid).frame(width: Theme.Size.avatarGlyph)
        }
    }
}
