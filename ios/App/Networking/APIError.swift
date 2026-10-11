import Foundation

/// Server error shape: `{"error": {"code": "...", "message": "..."}}`.
struct APIErrorBody: Codable, Sendable {
    struct Detail: Codable, Sendable { let code: String; let message: String }
    let error: Detail
}

enum APIError: Error, Equatable, LocalizedError, Sendable {
    /// 401 on an authenticated call. The client has already signed the user out.
    case unauthorized
    /// Any other non-2xx with the API error shape (or a synthesised one).
    case server(status: Int, code: String, message: String)
    /// Transport failure (offline, timeout, tunnel down).
    case network(String)
    /// 409 `not_removed`: restore on an active item.
    case notRemoved
    /// 409 `restore_window_expired`: more than 10 minutes since removal.
    case restoreWindowExpired
    case decoding(String)
    case invalidRequest(String)

    var errorDescription: String? {
        switch self {
        case .unauthorized: "Your session ended. Please sign in again."
        case .server(_, _, let message): message
        case .network: "Can't reach the server. Check your connection and try again."
        case .notRemoved: "That item hasn't been removed."
        case .restoreWindowExpired: "It's too late to undo this removal."
        case .decoding: "The server sent something unexpected."
        case .invalidRequest(let m): m
        }
    }

    /// API `code` for `.server`, e.g. `already_removed`, `email_taken`.
    var code: String? {
        if case .server(_, let code, _) = self { return code }
        if case .unauthorized = self { return "unauthorized" }
        if case .notRemoved = self { return "not_removed" }
        if case .restoreWindowExpired = self { return "restore_window_expired" }
        return nil
    }

    var isNetwork: Bool { if case .network = self { return true } else { return false } }
}
