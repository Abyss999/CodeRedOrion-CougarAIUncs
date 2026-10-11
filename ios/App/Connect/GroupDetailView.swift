import SwiftUI
import Observation

@MainActor
@Observable
final class GroupDetailModel {
    enum Load { case loading, loaded, failed(Error) }
    private(set) var load: Load = .loading
    private(set) var detail: GroupDetail
    private(set) var isLeaving = false
    var banner: String?
    private let api: APIClient

    init(api: APIClient, group: SharingGroup) {
        self.api = api
        detail = GroupDetail(group: group, members: [])
    }

    func reload() async {
        do {
            detail = try await api.groupDetail(id: detail.group.id)
            load = .loaded
        } catch is CancellationError {
        } catch {
            if case .loaded = load { banner = error.localizedDescription } else { load = .failed(error) }
        }
    }

    func retry() async { load = .loading; await reload() }

    func leave() async -> Bool {
        guard !isLeaving else { return false }
        isLeaving = true
        defer { isLeaving = false }
        do {
            try await api.leaveGroup(id: detail.group.id)
            Haptics.success()
            return true
        } catch is CancellationError {
        } catch {
            banner = error.localizedDescription
            Haptics.error()
        }
        return false
    }
}

/// GroupDetail artboard: members, the invite code (placed low, with room around it), Show QR, Share, Leave.
struct GroupDetailView: View {
    @State private var model: GroupDetailModel
    @State private var showQR = false
    @State private var confirmLeave = false
    let finish: (_ left: Bool) -> Void
    private let screen = AccessibilityID.GroupDetailScreen.screen

    init(api: APIClient, group: SharingGroup, finish: @escaping (_ left: Bool) -> Void) {
        _model = State(initialValue: GroupDetailModel(api: api, group: group))
        self.finish = finish
    }

    private var group: SharingGroup { model.detail.group }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(group.name)
                        .font(Theme.Fonts.screenTitle)
                        .foregroundStyle(Theme.Colors.ink)
                        .accessibilityAddTraits(.isHeader)
                    Text("\(group.memberCount) \(group.memberCount == 1 ? "member" : "members")\(group.role == .owner ? " · you are the owner" : "")")
                        .font(Theme.Fonts.sheetMeta)
                        .foregroundStyle(Theme.Colors.muted)
                }
                if let banner = model.banner {
                    BannerView(style: .error, message: banner, dismiss: { model.banner = nil },
                               identifiers: BannerIdentifiers(container: "groupdetail.banner"), horizontalInset: 0)
                }
                members
                invite
                    .padding(.top, Theme.Spacing.inviteGap)
                leaveButton
                    .padding(.top, Theme.Spacing.l)
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.vertical, Theme.Spacing.m)
        }
        .background(Theme.Colors.ground.ignoresSafeArea())
        .navigationTitle("Group")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier(screen)
        .refreshable { await model.reload() }
        .task { await model.reload() }
        .confirmationDialog("Leave \(group.name)?", isPresented: $confirmLeave, titleVisibility: .visible) {
            Button("Leave group", role: .destructive) {
                Task { if await model.leave() { finish(true) } }
            }
            .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.leaveConfirm)
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Your open listings in this group will be taken down.")
        }
    }

    @ViewBuilder private var members: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            GroupHeaderText(text: "Members")
            switch model.load {
            case .loading:
                SkeletonList(screen: screen, count: 3)
            case .failed(let error):
                ErrorStateView(screen: screen, error: error) { Task { await model.retry() } }
            case .loaded:
                if model.detail.members.isEmpty {
                    EmptyStateView(screen: screen, title: "No members", message: "Members will show up here.", systemImage: "person.3")
                } else {
                    VStack(spacing: 0) {
                        ForEach(model.detail.members) { m in
                            ConnectRow(initials: m.displayName.split(separator: " ").prefix(2).compactMap { $0.first }.map(String.init).joined().uppercased(),
                                       title: m.displayName,
                                       subtitle: m.role == .owner ? "Owner" : (m.joinedAt.map { "Joined \($0.formatted(.dateTime.month(.abbreviated).day()))" } ?? "Member"))
                            Divider().overlay(Theme.Colors.hairline)
                        }
                    }
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.members)
                }
            }
        }
    }

    private var displayCode: String {
        let c = group.inviteCode
        guard c.count == 8 else { return c }
        return c.prefix(4) + "-" + c.suffix(4)
    }

    private var invite: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            GroupHeaderText(text: "Invite code")
            Text(displayCode)
                .font(Theme.Fonts.sheetTitle)
                .monospaced()
                .foregroundStyle(Theme.Colors.ink)
                .textSelection(.enabled)
                .accessibilityLabel("Invite code \(group.inviteCode.map(String.init).joined(separator: " "))")
                .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.inviteCode)
            if showQR {
                QRCodeImage(text: group.inviteCode, size: Theme.Size.qrLarge, label: "QR code for invite code \(group.inviteCode)")
                    .frame(maxWidth: .infinity)
                    .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.qr)
                    .transition(.opacity)
            }
            HStack(spacing: Theme.Spacing.s) {
                Button { showQR.toggle() } label: {
                    Label(showQR ? "Hide QR" : "Show QR", systemImage: "qrcode")
                        .font(Theme.Fonts.badge)
                        .foregroundStyle(Theme.Colors.forest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.connectControl)
                        .overlay { RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                }
                .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.showQR)
                ShareLink(item: "Join \(group.name) on BiteDown with invite code \(displayCode)") {
                    Label("Share invite", systemImage: "square.and.arrow.up")
                        .font(Theme.Fonts.badge)
                        .foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.connectControl)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                }
                .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.share)
            }
        }
    }

    private var leaveButton: some View {
        Button { confirmLeave = true } label: {
            Text(model.isLeaving ? "Leaving…" : "Leave group")
                .font(Theme.Fonts.button)
                .foregroundStyle(Theme.Colors.urgentInk)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                .background(Theme.Colors.urgentBg, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
        }
        .disabled(model.isLeaving)
        .accessibilityIdentifier(AccessibilityID.GroupDetailScreen.leave)
    }
}
