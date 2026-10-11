import SwiftUI

/// `MyRequests`: your requests, Open first, then Done (fulfilled or cancelled). Open ones can be cancelled.
struct MyRequestsView: View {
    let model: SocialModel
    @MotionReduced private var reduceMotion
    @State private var confirming: HelpRequest?
    private let screen = AccessibilityID.MyRequests.screen

    var body: some View {
        Group {
            switch model.mine {
            case .loading:
                ScrollView { SkeletonList(screen: "myrequests", count: 3).padding(Theme.Spacing.gutter) }
            case .failed(let e):
                ScrollView { ErrorStateView(screen: "myrequests", error: e) { Task { await model.loadMine() } } }
            case .loaded(let list) where list.isEmpty:
                EmptyStateView(screen: "myrequests", title: "No requests yet",
                               message: "Tap + on the Social tab to ask your friends and groups for something.",
                               systemImage: "note.text")
            case .loaded(let list):
                content(list)
            }
        }
        .background(Theme.Colors.ground.ignoresSafeArea())
        .navigationTitle("Your requests")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier(screen)
        .task { await model.loadMine() }
        .refreshable { await model.loadMine() }
        .confirmationDialog("Cancel this request?", isPresented: Binding(get: { confirming != nil }, set: { if !$0 { confirming = nil } }),
                            titleVisibility: .visible, presenting: confirming) { r in
            Button("Cancel request", role: .destructive) { Task { await model.cancel(r, reduceMotion: reduceMotion) } }
            Button("Keep it", role: .cancel) {}
        }
    }

    private func content(_ list: [HelpRequest]) -> some View {
        let open = list.filter { $0.status == .open }
        let done = list.filter { $0.status != .open }
        return List {
            if let banner = model.banner {
                BannerView(style: .error, message: banner, dismiss: { model.banner = nil },
                           identifiers: .init(container: AccessibilityID.MyRequests.banner), horizontalInset: 0)
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets()).listRowSeparator(.hidden)
            }
            if !open.isEmpty {
                Section { ForEach(open) { row($0) } } header: { header("Open", open.count) }
            }
            if !done.isEmpty {
                Section { ForEach(done) { row($0) } } header: { header("Done", done.count) }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
    }

    private func header(_ title: String, _ n: Int) -> some View {
        GroupHeaderText(text: "\(title) · \(n)")
    }

    private func row(_ r: HelpRequest) -> some View {
        HStack(alignment: .top, spacing: Theme.Spacing.sm) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(r.text).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                Text("\(r.audienceSummary) · \(SocialText.agoLong(r.createdAt))")
                    .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                switch r.status {
                case .fulfilled:
                    Label("Fulfilled by \(r.fulfilledByName ?? "someone")", systemImage: "checkmark.circle.fill")
                        .font(Theme.Fonts.meta.weight(.medium)).foregroundStyle(Theme.Colors.forest)
                case .cancelled:
                    Label("Cancelled", systemImage: "xmark.circle").font(Theme.Fonts.meta.weight(.medium))
                        .foregroundStyle(Theme.Colors.muted)
                case .open: EmptyView()
                }
            }
            .accessibilityElement(children: .combine)
            Spacer(minLength: Theme.Spacing.xs)
            if r.status == .open {
                Button { confirming = r } label: {
                    Text("Cancel").font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.urgentInk)
                        .padding(.horizontal, Theme.Spacing.s)
                        .frame(minWidth: Theme.Size.minTouch, minHeight: Theme.Size.minTouch)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Cancel request: \(r.text)")
                .accessibilityIdentifier(AccessibilityID.MyRequests.cancel(r.id))
            }
        }
        .padding(.vertical, Theme.Spacing.xs)
        .listRowBackground(Theme.Colors.surface)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.MyRequests.row(r.id))
    }
}
