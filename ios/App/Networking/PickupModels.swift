import Foundation

/// A pickup spot on a share listing (docs/API.md "Pickup spot"): a note (1-120 chars) and/or a pin
/// (`lat` + `lng` together). `placeName` is an optional label for the pin. Only the listing's owner
/// and its claimer ever receive it; everyone else gets `pickup_set`.
struct Pickup: Codable, Hashable, Sendable {
    static let noteLimit = 120

    var note: String?
    var lat: Double?
    var lng: Double?
    var placeName: String?

    init(note: String? = nil, lat: Double? = nil, lng: Double? = nil, placeName: String? = nil) {
        self.note = note; self.lat = lat; self.lng = lng; self.placeName = placeName
    }

    private enum CodingKeys: String, CodingKey { case note, lat, lng, placeName }

    /// Omits nil keys (the server treats a blank string as absent, but a missing key is cleaner).
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(note, forKey: .note)
        try c.encodeIfPresent(lat, forKey: .lat)
        try c.encodeIfPresent(lng, forKey: .lng)
        try c.encodeIfPresent(placeName, forKey: .placeName)
    }

    var hasPin: Bool { lat != nil && lng != nil }
    var trimmedNote: String? {
        let t = note?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return t.isEmpty ? nil : t
    }
    /// The server accepts a spot only with a note or a lat+lng pair.
    var isValid: Bool {
        if let n = trimmedNote, n.count > Pickup.noteLimit { return false }
        return trimmedNote != nil || hasPin
    }
    /// Short label: the place name, else the note, else "Dropped pin".
    var title: String {
        if let p = placeName?.trimmingCharacters(in: .whitespacesAndNewlines), !p.isEmpty { return p }
        if let n = trimmedNote { return n }
        return "Dropped pin"
    }
}

/// Who a new listing is offered to. The API takes one audience per listing: your friends
/// (no `group_id`) or a single group (`group_id`).
enum ShareAudience: Hashable, Sendable {
    case friends
    case group(id: String, name: String)

    var groupId: String? {
        if case .group(let id, _) = self { return id }
        return nil
    }
    var listingAudience: ListingAudience {
        switch self {
        case .friends: ListingAudience(friends: true)
        case .group(let id, let name): ListingAudience(groups: [GroupRef(id: id, name: name)])
        }
    }
}

extension ListingAudience {
    /// "Friends", "Moody Towers", or "Friends, Flat 4B".
    var summary: String {
        var parts: [String] = []
        if friends { parts.append("Friends") }
        parts.append(contentsOf: groups.map(\.name))
        return parts.isEmpty ? "Friends" : parts.joined(separator: ", ")
    }
}
