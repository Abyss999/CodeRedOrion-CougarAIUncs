import SwiftUI
import Observation

/// State for `ConnectView`: friends (accepted / incoming / outgoing) and groups, plus the add / create / join forms.
@MainActor
@Observable
final class ConnectModel {
    enum Load { case loading, loaded, failed(Error) }

    private(set) var load: Load = .loading
    private(set) var friends = FriendsResponse.empty
    private(set) var groups: [SharingGroup] = []
    var banner: String?

    // Add friend by email
    var email = ""
    private(set) var emailError: String?
    private(set) var emailSent: String?
    private(set) var isSendingEmail = false
    // Create / join group
    var newGroupName = ""
    private(set) var createError: String?
    private(set) var isCreating = false
    var joinCode = ""
    private(set) var joinError: String?
    private(set) var isJoining = false
    /// Ids with an accept / decline / withdraw in flight.
    private(set) var busy: Set<String> = []

    private let api: APIClient
    init(api: APIClient) { self.api = api }

    func loadIfNeeded() async {
        if case .loaded = load { return }
        await reload()
    }

    func reload() async {
        do {
            async let f = api.listFriends()
            async let g = api.listGroups()
            let (fr, gr) = try await (f, g)
            friends = fr
            groups = gr
            load = .loaded
        } catch is CancellationError {
        } catch {
            if case .loaded = load { banner = error.localizedDescription } else { load = .failed(error) }
        }
    }

    func retry() async {
        load = .loading
        await reload()
    }

    // MARK: Requests

    func accept(_ f: Friend) async {
        await perform(f.userId) {
            let accepted = try await api.acceptFriend(userId: f.userId)
            friends.incoming.removeAll { $0.userId == f.userId }
            friends.friends.append(accepted)
            Haptics.success()
        }
    }

    func decline(_ f: Friend) async {
        await perform(f.userId) {
            try await api.declineFriend(userId: f.userId)
            friends.incoming.removeAll { $0.userId == f.userId }
        }
    }

    func withdraw(_ f: Friend) async {
        await perform(f.userId) {
            try await api.removeFriend(userId: f.userId)
            friends.outgoing.removeAll { $0.userId == f.userId }
        }
    }

    private func perform(_ id: String, _ work: () async throws -> Void) async {
        guard !busy.contains(id) else { return }
        busy.insert(id)
        defer { busy.remove(id) }
        do { try await work() } catch is CancellationError {} catch {
            banner = error.localizedDescription
            Haptics.error()
            await reload()
        }
    }

    // MARK: Add friend by email

    func sendEmail() async {
        let value = email.trimmingCharacters(in: .whitespacesAndNewlines)
        emailSent = nil
        guard !value.isEmpty else { emailError = "Enter your friend's email."; return }
        guard !isSendingEmail else { return }
        isSendingEmail = true
        defer { isSendingEmail = false }
        do {
            let f = try await api.requestFriend(email: value)
            friends.outgoing.append(f)
            email = ""
            emailError = nil
            emailSent = "Request sent to \(f.displayName)."
            Haptics.success()
        } catch is CancellationError {} catch {
            emailError = Self.emailMessage(error)
            Haptics.error()
        }
    }

    static func emailMessage(_ error: Error) -> String {
        guard let e = error as? APIError else { return error.localizedDescription }
        switch e.code {
        case "not_found": return "No BiteDown account uses that email."
        case "already_friends": return "You're already friends."
        case "request_pending": return "A request is already pending."
        default: return e.localizedDescription
        }
    }

    func clearEmailMessages() { emailError = nil; emailSent = nil }

    // MARK: Groups

    func createGroup() async -> SharingGroup? {
        let name = newGroupName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { createError = "Give the group a name."; return nil }
        guard !isCreating else { return nil }
        isCreating = true
        defer { isCreating = false }
        do {
            let g = try await api.createGroup(name: name)
            groups.append(g)
            newGroupName = ""
            createError = nil
            Haptics.success()
            return g
        } catch is CancellationError {} catch {
            createError = error.localizedDescription
            Haptics.error()
        }
        return nil
    }

    func joinGroup() async -> SharingGroup? {
        let code = joinCode.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !code.isEmpty else { joinError = "Enter the invite code."; return nil }
        guard !isJoining else { return nil }
        isJoining = true
        defer { isJoining = false }
        do {
            let g = try await api.joinGroup(inviteCode: code)
            groups.append(g)
            joinCode = ""
            joinError = nil
            Haptics.success()
            return g
        } catch is CancellationError {} catch {
            joinError = Self.joinMessage(error)
            Haptics.error()
        }
        return nil
    }

    static func joinMessage(_ error: Error) -> String {
        guard let e = error as? APIError else { return error.localizedDescription }
        switch e.code {
        case "not_found": return "No group uses that code."
        case "already_member": return "You're already in that group."
        default: return e.localizedDescription
        }
    }

    func clearGroupErrors() { createError = nil; joinError = nil }

    func removeGroup(id: String) { groups.removeAll { $0.id == id } }
}
