import Foundation

/// Who a donation goes to (`recipient_id` on `POST /items/:id/remove` and `remove-batch`).
/// - `.default`: the field is omitted, so the server uses the claimer of the open listing.
/// - `.none`: an explicit JSON `null`: nobody in particular, even if the listing was claimed.
/// - `.user(id)`: that user.
enum RecipientChoice: Hashable, Sendable {
    case `default`
    case none
    case user(String)

    init(recipientId: String?) { self = recipientId.map(RecipientChoice.user) ?? .default }

    /// The id for `.user`, else nil.
    var userId: String? { if case .user(let id) = self { id } else { nil } }
}

/// Body of `POST /items/:id/remove`. Encodes `recipient_id` per `RecipientChoice`: omitted,
/// `null` or the id. Use with `APICoding.encoder`.
struct RemoveBody: Encodable, Sendable {
    var outcome: RemoveOutcome
    var wasteReason: WasteReason?
    var recipient: RecipientChoice = .default

    private enum CodingKeys: String, CodingKey { case outcome, wasteReason, recipientId }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(outcome, forKey: .outcome)
        try c.encodeIfPresent(wasteReason, forKey: .wasteReason)
        switch recipient {
        case .default: break
        case .none: try c.encodeNil(forKey: .recipientId)
        case .user(let id): try c.encode(id, forKey: .recipientId)
        }
    }
}

/// Body of `POST /items/remove-batch` (`outcome` is used | donated).
struct RemoveBatchBody: Encodable, Sendable {
    var itemIds: [String]
    var outcome: RemoveOutcome
    var recipient: RecipientChoice = .default

    private enum CodingKeys: String, CodingKey { case itemIds, outcome, recipientId }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(itemIds, forKey: .itemIds)
        try c.encode(outcome, forKey: .outcome)
        switch recipient {
        case .default: break
        case .none: try c.encodeNil(forKey: .recipientId)
        case .user(let id): try c.encode(id, forKey: .recipientId)
        }
    }
}

/// Body of `POST /items/restore-batch`.
struct RestoreBatchBody: Encodable, Sendable { var itemIds: [String] }
