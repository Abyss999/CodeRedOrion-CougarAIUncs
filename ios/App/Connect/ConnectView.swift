import SwiftUI

/// Connect / ConnectPending artboards (SCREENS 9, 37): "Friends and groups". Present it as a sheet
/// from the Social tab: `.sheet(isPresented:) { ConnectView() }`.
/// Order (round 3/4): incoming requests, Friends (+ Sent, My code, Add by email), Groups (Create, Join).
struct ConnectView: View {
    @Environment(AppEnvironment.self) private var env

    var body: some View {
        ConnectContent(api: env.api)
    }
}

private enum ConnectRoute: Hashable {
    case group(SharingGroup)
    case scan
}

private struct ConnectContent: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model: ConnectModel
    @State private var path: [ConnectRoute] = []
    @State private var showAllFriends = false
    @State private var showEmail = false
    @State private var showCreate = false
    @State private var showJoin = false
    let api: APIClient

    private let screen = AccessibilityID.Connect.screen
    private let friendPreview = 5

    init(api: APIClient) {
        self.api = api
        _model = State(initialValue: ConnectModel(api: api))
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                    header
                    if let banner = model.banner {
                        BannerView(style: .error, message: banner, dismiss: { model.banner = nil },
                                   identifiers: BannerIdentifiers(container: "connect.banner"), horizontalInset: 0)
                    }
                    content
                }
                .padding(.horizontal, Theme.Spacing.gutter)
                .padding(.vertical, Theme.Spacing.m)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.Colors.ground.ignoresSafeArea())
            .refreshable { await model.reload() }
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: ConnectRoute.self) { route in
                switch route {
                case .group(let g):
                    GroupDetailView(api: api, group: g) { left in
                        if left { model.removeGroup(id: g.id) }
                        path.removeAll()
                    }
                case .scan:
                    FriendScanView(api: api) {
                        path.removeAll()
                        Task { await model.reload() }
                    }
                }
            }
        }
        .tint(Theme.Colors.forest)
        .accessibilityIdentifier(screen)
        .task { await model.loadIfNeeded() }
        .onChange(of: path) { old, new in
            // Coming back from a scan or a group: the lists may have changed.
            if new.count < old.count { Task { await model.reload() } }
        }
    }

    // MARK: Header

    private var header: some View {
        HStack {
            Text("Friends and groups")
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: Theme.Spacing.s)
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(Theme.Fonts.badge)
                    .foregroundStyle(Theme.Colors.ink)
                    .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                    .background(Theme.Colors.surface, in: Circle())
                    .overlay { Circle().strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
            }
            .accessibilityLabel("Close")
            .accessibilityIdentifier(AccessibilityID.Connect.close)
        }
    }

    // MARK: Content states

    @ViewBuilder private var content: some View {
        switch model.load {
        case .loading:
            SkeletonList(screen: screen, count: 4)
        case .failed(let error):
            ErrorStateView(screen: screen, error: error) { Task { await model.retry() } }
        case .loaded:
            requestsSection
            friendsSection
            sentSection
            MyCodeCard(api: api) { path.append(.scan) }
            addByEmail
            groupsSection
        }
    }

    // MARK: Incoming requests

    @ViewBuilder private var requestsSection: some View {
        if !model.friends.incoming.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.stack) {
                Label("Friend request", systemImage: "person.badge.plus")
                    .font(Theme.Fonts.badge)
                    .foregroundStyle(Theme.Colors.inkSecondary)
                ForEach(model.friends.incoming) { f in
                    requestRow(f)
                }
            }
            .padding(.horizontal, Theme.Spacing.m)
            .padding(.vertical, Theme.Spacing.sm)
            .background(Theme.Colors.lime, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .accessibilityElement(children: .contain)
            .accessibilityLabel("Friend requests")
            .accessibilityIdentifier(AccessibilityID.Connect.requests)
        }
    }

    private func requestRow(_ f: Friend) -> some View {
        let disabled = model.busy.contains(f.userId)
        return ViewThatFits(in: .horizontal) {
            HStack(spacing: Theme.Spacing.s) {
                requestText(f)
                requestButtons(f, disabled: disabled)
            }
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                requestText(f)
                HStack(spacing: Theme.Spacing.s) { requestButtons(f, disabled: disabled) }
            }
        }
    }

    private func requestText(_ f: Friend) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(f.displayName).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
            Text("wants to be friends").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.inkSecondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func requestButtons(_ f: Friend, disabled: Bool) -> some View {
        // Decline is ink text on lime (round 3/4); Accept is the filled forest button.
        Button { Task { await model.decline(f) } } label: {
            Text("Decline")
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.ink)
                .padding(.horizontal, Theme.Spacing.sm)
                .frame(minHeight: Theme.Size.minTouch)
                .contentShape(Rectangle())
        }
        .disabled(disabled)
        .accessibilityLabel("Decline friend request from \(f.displayName)")
        .accessibilityIdentifier(AccessibilityID.Connect.decline(f.userId))
        Button { Task { await model.accept(f) } } label: {
            Text("Accept")
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.onForest)
                .padding(.horizontal, Theme.Spacing.m)
                .frame(minHeight: Theme.Size.minTouch)
                .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
        }
        .disabled(disabled)
        .accessibilityLabel("Accept friend request from \(f.displayName)")
        .accessibilityIdentifier(AccessibilityID.Connect.accept(f.userId))
    }

    // MARK: Friends

    private var friendsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            sectionHeader("Friends · \(model.friends.friends.count)")
            if model.friends.friends.isEmpty {
                Text("No friends yet. Show your code, scan a friend's, or add one by email.")
                    .font(Theme.Fonts.callout)
                    .foregroundStyle(Theme.Colors.muted)
                    .padding(Theme.Spacing.m)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .accessibilityIdentifier(AccessibilityID.State.empty(screen))
            } else {
                let all = model.friends.friends
                let shown = showAllFriends ? all : Array(all.prefix(friendPreview))
                VStack(spacing: 0) {
                    ForEach(shown) { f in
                        ConnectRow(initials: initials(f.displayName), title: f.displayName,
                                   subtitle: f.createdAt.map { "Friends since \($0.formatted(.dateTime.month(.abbreviated).day()))" } ?? "Friend")
                            .accessibilityIdentifier(AccessibilityID.Connect.friend(f.userId))
                        Divider().overlay(Theme.Colors.hairline)
                    }
                    if all.count > friendPreview {
                        Button { showAllFriends.toggle() } label: {
                            Text(showAllFriends ? "Show fewer" : "See all \(all.count) friends")
                                .font(Theme.Fonts.button)
                                .foregroundStyle(Theme.Colors.forest)
                                .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                        }
                    }
                }
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            }
        }
    }

    // MARK: Sent (ConnectPending)

    @ViewBuilder private var sentSection: some View {
        if !model.friends.outgoing.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                sectionHeader("Sent · \(model.friends.outgoing.count)")
                VStack(spacing: 0) {
                    ForEach(model.friends.outgoing) { f in
                        HStack(spacing: Theme.Spacing.sm) {
                            VStack(alignment: .leading, spacing: 0) {
                                Text(f.displayName).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                                Text("Pending").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            Button { Task { await model.withdraw(f) } } label: {
                                Text("Withdraw")
                                    .font(Theme.Fonts.badge)
                                    .foregroundStyle(Theme.Colors.forest)
                                    .padding(.horizontal, Theme.Spacing.sm)
                                    .frame(minHeight: Theme.Size.minTouch)
                                    .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous).strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                            }
                            .disabled(model.busy.contains(f.userId))
                            .accessibilityLabel("Withdraw friend request to \(f.displayName)")
                            .accessibilityIdentifier(AccessibilityID.Connect.withdraw(f.userId))
                        }
                        .padding(.horizontal, Theme.Spacing.sm + Theme.Spacing.xxs)
                        .padding(.vertical, Theme.Spacing.s)
                        .accessibilityElement(children: .contain)
                        .accessibilityIdentifier(AccessibilityID.Connect.sent(f.userId))
                        Divider().overlay(Theme.Colors.hairline)
                    }
                }
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            }
        }
    }

    // MARK: Add by email

    private var addByEmail: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            ExpandRow(title: "Add by email", systemImage: "envelope", expanded: showEmail,
                      identifier: AccessibilityID.Connect.addFriendToggle) {
                showEmail.toggle()
                model.clearEmailMessages()
            }
            if showEmail {
                VStack(alignment: .leading, spacing: Theme.Spacing.stack) {
                    FormField(label: "Friend's email", error: model.emailError, identifier: AccessibilityID.Connect.addFriendField) {
                        HStack(spacing: Theme.Spacing.s) {
                            TextField("name@school.edu", text: $model.email)
                                .keyboardType(.emailAddress)
                                .textContentType(.emailAddress)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                                .submitLabel(.send)
                                .onSubmit { Task { await model.sendEmail() } }
                                .inputStyle(hasError: model.emailError != nil)
                            sendButton(title: "Send", busy: model.isSendingEmail, identifier: AccessibilityID.Connect.addFriendSend) {
                                Task { await model.sendEmail() }
                            }
                        }
.accessibilityElement(children: .contain)
                    }
                    if let sent = model.emailSent {
                        Label(sent, systemImage: "checkmark.circle.fill")
                            .font(Theme.Fonts.meta.weight(.semibold))
                            .foregroundStyle(Theme.Colors.forest)
                    }
                }
                .padding(.horizontal, Theme.Spacing.xxs)
                .transition(.opacity)
            }
        }
    }

    // MARK: Groups

    private var groupsSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            sectionHeader("Groups · \(model.groups.count)")
            if !model.groups.isEmpty {
                VStack(spacing: 0) {
                    ForEach(model.groups) { g in
                        Button { path.append(.group(g)) } label: {
                            ConnectRow(systemImage: "person.3.fill", title: g.name,
                                       subtitle: "\(g.memberCount) \(g.memberCount == 1 ? "member" : "members")\(g.role == .owner ? " · you are the owner" : "")",
                                       chevron: true)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier(AccessibilityID.Connect.group(g.id))
                        Divider().overlay(Theme.Colors.hairline)
                    }
                }
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            }
            ExpandRow(title: "Create a group", systemImage: "plus.circle", expanded: showCreate,
                      identifier: AccessibilityID.Connect.createGroup) {
                showCreate.toggle(); if showCreate { showJoin = false }
                model.clearGroupErrors()
            }
            if showCreate {
                FormField(label: "Group name", error: model.createError, identifier: AccessibilityID.Connect.createGroupField) {
                    HStack(spacing: Theme.Spacing.s) {
                        TextField("Flat 4B", text: $model.newGroupName)
                            .submitLabel(.done)
                            .onSubmit { Task { await createGroup() } }
                            .inputStyle(hasError: model.createError != nil)
                        sendButton(title: "Create", busy: model.isCreating, identifier: AccessibilityID.Connect.createGroupSubmit) {
                            Task { await createGroup() }
                        }
                    }
.accessibilityElement(children: .contain)
                }
                .padding(.horizontal, Theme.Spacing.xxs)
            }
            ExpandRow(title: "Join a group", systemImage: "key", expanded: showJoin,
                      identifier: AccessibilityID.Connect.joinGroup) {
                showJoin.toggle(); if showJoin { showCreate = false }
                model.clearGroupErrors()
            }
            if showJoin {
                FormField(label: "Invite code", error: model.joinError, identifier: AccessibilityID.Connect.joinGroupField) {
                    HStack(spacing: Theme.Spacing.s) {
                        TextField("K7PQ-M2XR", text: $model.joinCode)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .submitLabel(.join)
                            .onSubmit { Task { await joinGroup() } }
                            .inputStyle(hasError: model.joinError != nil)
                        sendButton(title: "Join", busy: model.isJoining, identifier: AccessibilityID.Connect.joinGroupSubmit) {
                            Task { await joinGroup() }
                        }
                    }
.accessibilityElement(children: .contain)
                }
                .padding(.horizontal, Theme.Spacing.xxs)
            }
        }
    }

    private func createGroup() async {
        if let g = await model.createGroup() { showCreate = false; path.append(.group(g)) }
    }

    private func joinGroup() async {
        if let g = await model.joinGroup() { showJoin = false; path.append(.group(g)) }
    }

    // MARK: Pieces

    private func sectionHeader(_ text: String) -> some View {
        GroupHeaderText(text: text)
    }

    private func sendButton(title: String, busy: Bool, identifier: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Group {
                if busy { ProgressView().tint(Theme.Colors.onForest) } else { Text(title) }
            }
            .font(Theme.Fonts.badge)
            .foregroundStyle(Theme.Colors.onForest)
            .padding(.horizontal, Theme.Spacing.m)
            .frame(minHeight: Theme.Size.connectControl)
            .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
        }
        .disabled(busy)
        .accessibilityLabel(title)
        .accessibilityIdentifier(identifier)
    }

    private func initials(_ name: String) -> String {
        name.split(separator: " ").prefix(2).compactMap { $0.first }.map(String.init).joined().uppercased()
    }
}

// MARK: - Shared row pieces

/// Friend / group row: 36 pt circle (initials or SF Symbol), title, subtitle, optional chevron. 52 pt minimum.
struct ConnectRow: View {
    var initials: String?
    var systemImage: String?
    let title: String
    let subtitle: String
    var chevron = false

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Group {
                if let initials { Text(initials).font(Theme.Fonts.badge) }
                else if let systemImage { Image(systemName: systemImage).font(.footnote) }
            }
            .foregroundStyle(Theme.Colors.forest)
            .frame(width: Theme.Size.rowIcon, height: Theme.Size.rowIcon)
            .background(Theme.Colors.limeTint, in: Circle())
            .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 0) {
                Text(title).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                Text(subtitle).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if chevron {
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(Theme.Colors.muted)
                    .accessibilityHidden(true)
            }
        }
        .padding(.horizontal, Theme.Spacing.sm + Theme.Spacing.xxs)
        .padding(.vertical, Theme.Spacing.stack)
        .frame(minHeight: Theme.Size.connectRow)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// White outlined action row ("Add by email", "Create a group", "Join a group").
struct ExpandRow: View {
    let title: String
    let systemImage: String
    let expanded: Bool
    let identifier: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: systemImage)
                Text(title).frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.down").rotationEffect(.degrees(expanded ? 180 : 0)).font(.footnote.weight(.semibold))
            }
            .font(Theme.Fonts.button.weight(.semibold))
            .foregroundStyle(Theme.Colors.forest)
            .padding(.horizontal, Theme.Spacing.sm + Theme.Spacing.xxs)
            .frame(minHeight: Theme.Size.connectControl)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous).strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
        }
        .accessibilityValue(expanded ? "Expanded" : "Collapsed")
        .accessibilityIdentifier(identifier)
    }
}

extension View {
    /// Bordered text field styling shared by the Connect forms.
    func inputStyle(hasError: Bool) -> some View {
        self.font(Theme.Fonts.body)
            .foregroundStyle(Theme.Colors.ink)
            .padding(.horizontal, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.connectControl)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                    .strokeBorder(hasError ? Theme.Colors.urgentInk : Theme.Colors.border,
                                  lineWidth: hasError ? Theme.Stroke.selected : Theme.Stroke.hairline)
            }
    }
}
