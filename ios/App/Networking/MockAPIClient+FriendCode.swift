import Foundation

/// Mock friend QR. `friendCode()` issues `MOCKCODE<n>`; `addFriend(code:)` accepts `friend-<first name>`
/// for anyone in `MockSocialState.directory` (friend-ana, friend-sam, friend-marcus is already a friend),
/// and answers `invalid_code` for anything else (try `friend-expired`).
extension MockAPIClient {
    func friendCode() async throws -> FriendCodeInfo {
        try await gate("friendCode")
        defer { nextID += 1 }
        let code = "MOCKCODE\(String(format: "%08d", nextID))"
        return FriendCodeInfo(code: code, expiresAt: Date().addingTimeInterval(10 * 60), url: "bitedown://friend/\(code)")
    }

    func addFriend(code: String) async throws -> FriendAddResult {
        try await gate("addFriend")
        let key = code.trimmingCharacters(in: .whitespacesAndNewlines)
        let invalid = APIError.server(status: 400, code: "invalid_code", message: "That code isn't valid any more.")
        if key.hasPrefix("MOCKCODE") { throw validation("That's your own code.") }
        guard key.lowercased().hasPrefix("friend-") else { throw invalid }
        let first = String(key.dropFirst("friend-".count)).lowercased()
        guard let user = social.directory.values.first(where: {
            $0.displayName.split(separator: " ").first.map { $0.lowercased() == first } ?? false
        }) else { throw invalid }
        if let existing = social.friends.friends.first(where: { $0.userId == user.id }) {
            return FriendAddResult(friend: existing, alreadyFriends: true)
        }
        social.friends.incoming.removeAll { $0.userId == user.id }
        social.friends.outgoing.removeAll { $0.userId == user.id }
        let f = Friend(userId: user.id, displayName: user.displayName, status: .accepted, createdAt: Date())
        social.friends.friends.append(f)
        return FriendAddResult(friend: f, alreadyFriends: false)
    }
}
