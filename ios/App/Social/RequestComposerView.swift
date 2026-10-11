import SwiftUI

/// `RequestComposer`: a note of up to 280 characters plus a multi-audience checklist (friends and/or groups).
struct RequestComposerView: View {
    let api: APIClient
    let post: (String, AudienceSelection, [SharingGroup]) async throws -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var selection = AudienceSelection()
    @State private var groups: [SharingGroup] = []
    @State private var friendCount: Int?
    @State private var audienceState: Load<Void> = .loading
    @State private var posting = false
    @State private var error: String?
    private static let limit = 280

    private var canPost: Bool {
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !selection.isEmpty && !posting
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                    if let error {
                        BannerView(style: .error, message: error, retry: { Task { await submit() } },
                                   identifiers: .init(container: AccessibilityID.Composer.banner), horizontalInset: 0)
                    }
                    VStack(alignment: .trailing, spacing: Theme.Spacing.xs) {
                        FormField(label: "Your note", identifier: AccessibilityID.Composer.text) {
                            TextField("Anyone have 2 eggs? Baking tonight.", text: $text, axis: .vertical)
                                .lineLimit(3...8)
                                .font(Theme.Fonts.body)
                                .foregroundStyle(Theme.Colors.ink)
                                .padding(Theme.Spacing.sm)
                                .frame(minHeight: Theme.Size.reasonTile, alignment: .topLeading)
                                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                                    .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                        }
                        Text("\(text.count) / \(Self.limit)")
                            .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                            .accessibilityLabel("\(text.count) of \(Self.limit) characters")
                            .accessibilityIdentifier(AccessibilityID.Composer.count)
                    }
                    VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                        Text("Who can see it").font(Theme.Fonts.cardHeading).foregroundStyle(Theme.Colors.ink)
                            .accessibilityAddTraits(.isHeader)
                        audience
                    }
                }
                .padding(Theme.Spacing.gutter)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.Colors.ground.ignoresSafeArea())
            .navigationTitle("Ask for something")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .frame(minHeight: Theme.Size.minTouch)
                        .accessibilityIdentifier(AccessibilityID.Composer.cancel)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button { Task { await submit() } } label: {
                        if posting { ProgressView() } else { Text("Post").fontWeight(.semibold) }
                    }
                    .disabled(!canPost)
                    .frame(minHeight: Theme.Size.minTouch)
                    .accessibilityIdentifier(AccessibilityID.Composer.post)
                }
            }
            .accessibilityIdentifier(AccessibilityID.Composer.screen)
        }
        .onChange(of: text) { _, new in if new.count > Self.limit { text = String(new.prefix(Self.limit)) } }
        .task { await loadAudiences() }
        .interactiveDismissDisabled(posting)
    }

    @ViewBuilder private var audience: some View {
        switch audienceState {
        case .loading:
            ProgressView().frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                .accessibilityLabel("Loading")
                .accessibilityIdentifier(AccessibilityID.State.loading("composer"))
        case .failed(let e):
            ErrorStateView(screen: "composer", error: e) { Task { await loadAudiences() } }
        case .loaded:
            AudienceChecklist(groups: groups, friendCount: friendCount, selection: $selection, emptyHint: "Pick at least one")
        }
    }

    private func loadAudiences() async {
        audienceState = .loading
        do {
            async let g = api.listGroups()
            async let f = api.listFriends()
            groups = try await g
            friendCount = try await f.friends.count
            audienceState = .loaded(())
        } catch { audienceState = .failed(error) }
    }

    private func submit() async {
        guard canPost else { return }
        posting = true; error = nil
        do {
            try await post(text.trimmingCharacters(in: .whitespacesAndNewlines), selection, groups)
            dismiss()
        } catch {
            self.error = error.localizedDescription
            Haptics.error()
        }
        posting = false
    }
}
