import SwiftUI
import Observation

/// Turns a scanned / typed / deep-linked friend code into friendship (`POST /friends {code}`).
@MainActor
@Observable
final class FriendAddModel {
    enum Phase: Equatable {
        case idle
        case adding
        case added(FriendAddResult)
        case failed(String)
    }

    private(set) var phase: Phase = .idle
    var manualText = ""
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    var isAdding: Bool { phase == .adding }
    var errorMessage: String? { if case .failed(let m) = phase { m } else { nil } }
    var result: FriendAddResult? { if case .added(let r) = phase { r } else { nil } }

    /// Accepts a full `bitedown://friend/<code>` link or a bare code. Ignores a second scan while one is in flight.
    func submit(payload: String) {
        guard !isAdding else { return }
        guard let code = FriendLink.code(fromPayload: payload) else {
            phase = .failed(Self.invalidMessage)
            Haptics.error()
            return
        }
        phase = .adding
        Task {
            do {
                let r = try await api.addFriend(code: code)
                phase = .added(r)
                Haptics.success()
            } catch is CancellationError {
                phase = .idle
            } catch {
                phase = .failed(Self.message(for: error))
                Haptics.error()
            }
        }
    }

    func reset() {
        phase = .idle
        manualText = ""
    }

    static let invalidMessage = "That code isn't valid any more."

    static func message(for error: Error) -> String {
        guard let e = error as? APIError else { return error.localizedDescription }
        if e.code == "invalid_code" { return invalidMessage }
        return e.localizedDescription
    }
}
