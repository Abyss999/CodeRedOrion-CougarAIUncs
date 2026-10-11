import Foundation

/// `GET /friends/code` → `{code, expires_at, url}`. `url` (`bitedown://friend/<code>`) is what the QR encodes.
struct FriendCodeInfo: Codable, Hashable, Sendable {
    var code: String
    var expiresAt: Date
    var url: String
}

/// Result of `POST /friends {code}`. `alreadyFriends` is true on a 200 (the 201 case is a new friend).
struct FriendAddResult: Hashable, Sendable {
    var friend: Friend
    var alreadyFriends: Bool
}

/// Parses `bitedown://friend/<code>` (or a bare code typed by hand).
enum FriendLink {
    static let scheme = "bitedown"
    static let host = "friend"

    /// The code inside a `bitedown://friend/<code>` URL, or nil for any other URL.
    static func code(from url: URL) -> String? {
        guard url.scheme?.lowercased() == scheme, url.host()?.lowercased() == host else { return nil }
        let code = url.pathComponents.filter { $0 != "/" }.first ?? ""
        return code.isEmpty ? nil : code
    }

    /// Accepts a scanned payload or typed text: a full link, or just the code. Nil when empty or not a friend link.
    static func code(fromPayload text: String) -> String? {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty else { return nil }
        if t.contains("://") {
            guard let url = URL(string: t) else { return nil }
            return code(from: url)
        }
        return t
    }
}
