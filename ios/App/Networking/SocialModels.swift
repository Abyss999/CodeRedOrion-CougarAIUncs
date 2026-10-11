import Foundation

// Models for friends, groups, the Food Pantry (share listings) and the request board.
// Decoded with `APICoding.decoder`. Shapes follow docs/API.md.

// MARK: - Shared references

/// `{id, name}`. Also decodes a bare string (name only, empty id) so a looser `groups` list still reads.
struct GroupRef: Codable, Hashable, Sendable, Identifiable {
    var id: String
    var name: String

    init(id: String, name: String) { self.id = id; self.name = name }

    private enum CodingKeys: String, CodingKey { case id, name }

    init(from decoder: Decoder) throws {
        if let name = try? decoder.singleValueContainer().decode(String.self) {
            self = GroupRef(id: "", name: name)
            return
        }
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self = GroupRef(id: try c.decode(String.self, forKey: .id), name: try c.decode(String.self, forKey: .name))
    }
}

// MARK: - Friends

enum FriendStatus: String, Codable, Sendable, Hashable {
    case pending, accepted
}

/// `{user_id (the other person), display_name, status, created_at}`.
struct Friend: Codable, Hashable, Sendable, Identifiable {
    var userId: String
    var displayName: String
    var status: FriendStatus
    var createdAt: Date?
    var id: String { userId }
}

struct FriendResponse: Codable, Sendable { let friend: Friend }

/// `GET /friends`: accepted, pending received, pending sent.
struct FriendsResponse: Codable, Hashable, Sendable {
    var friends: [Friend]
    var incoming: [Friend]
    var outgoing: [Friend]

    static let empty = FriendsResponse(friends: [], incoming: [], outgoing: [])
}

// MARK: - Groups

enum GroupRole: String, Codable, Sendable, Hashable {
    case owner, member
}

/// `{id, name, role (yours), member_count, invite_code, created_by (null after the creator deleted their account), created_at}`.
/// Named `SharingGroup` because a type called `Group` would shadow SwiftUI's `Group` view module-wide.
struct SharingGroup: Codable, Hashable, Sendable, Identifiable {
    var id: String
    var name: String
    var role: GroupRole
    var memberCount: Int
    var inviteCode: String
    var createdBy: String?
    var createdAt: Date?
}

struct GroupMember: Codable, Hashable, Sendable, Identifiable {
    var userId: String
    var displayName: String
    var role: GroupRole
    var joinedAt: Date?
    var id: String { userId }
}

/// `GET /groups/:id`: the group plus `members`.
struct GroupDetail: Codable, Hashable, Sendable, Identifiable {
    var group: SharingGroup
    var members: [GroupMember]
    var id: String { group.id }

    init(group: SharingGroup, members: [GroupMember]) { self.group = group; self.members = members }

    private enum CodingKeys: String, CodingKey { case members }

    init(from decoder: Decoder) throws {
        group = try SharingGroup(from: decoder)
        members = try decoder.container(keyedBy: CodingKeys.self).decodeIfPresent([GroupMember].self, forKey: .members) ?? []
    }

    func encode(to encoder: Encoder) throws {
        try group.encode(to: encoder)
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(members, forKey: .members)
    }
}

struct GroupResponse: Codable, Sendable { let group: SharingGroup }
struct GroupDetailResponse: Codable, Sendable { let group: GroupDetail }
struct GroupsResponse: Codable, Sendable { let groups: [SharingGroup] }
struct LeftResponse: Codable, Sendable { let left: Bool }

/// An item in a group's pantry: the item plus `added_by` (display name).
struct PantryItem: Codable, Hashable, Sendable, Identifiable {
    var item: Item
    var addedBy: String?
    var id: String { item.id }

    init(item: Item, addedBy: String?) { self.item = item; self.addedBy = addedBy }

    private enum CodingKeys: String, CodingKey { case addedBy }

    init(from decoder: Decoder) throws {
        item = try Item(from: decoder)
        addedBy = try decoder.container(keyedBy: CodingKeys.self).decodeIfPresent(String.self, forKey: .addedBy)
    }

    func encode(to encoder: Encoder) throws {
        try item.encode(to: encoder)
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(addedBy, forKey: .addedBy)
    }
}
struct PantryItemsResponse: Codable, Sendable { let items: [PantryItem] }

// MARK: - Share listings

/// Owner-side audience of a listing (`audience`, coming from the backend). Every field is optional
/// on the wire: `friends` false and `groups` empty when absent.
struct ListingAudience: Codable, Hashable, Sendable {
    var friends: Bool
    var groups: [GroupRef]

    init(friends: Bool = false, groups: [GroupRef] = []) { self.friends = friends; self.groups = groups }

    private enum CodingKeys: String, CodingKey { case friends, groups }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        friends = try c.decodeIfPresent(Bool.self, forKey: .friends) ?? false
        groups = try c.decodeIfPresent([GroupRef].self, forKey: .groups) ?? []
    }
}

/// `{id, item_id, owner_id, group_id, status, recipient_id, claimed_by, created_at, fulfilled_at}` from
/// `POST /share`, `DELETE /share/:id` and `POST /share/:id/claim`, plus the optional `audience`.
struct Listing: Codable, Hashable, Sendable, Identifiable {
    var id: String
    var itemId: String
    var ownerId: String
    var groupId: String?
    var status: ShareStatus
    var recipientId: String?
    var claimedBy: String?
    var createdAt: Date?
    var fulfilledAt: Date?
    /// Owner-side audience block; nil until the backend sends it.
    var audience: ListingAudience?
    /// Pickup spot: owner and claimer only (nil for everyone else). Backend `feat/friend-qr-pickup`.
    var pickup: Pickup? = nil
    /// True when a spot exists, whoever can see it. Nil from older backends.
    var pickupSet: Bool? = nil
}
struct ListingResponse: Codable, Sendable { let listing: Listing }

/// An entry of the Food Pantry (`GET /share`), someone else's open listing.
struct PantryListing: Codable, Hashable, Sendable, Identifiable {
    struct Source: Codable, Hashable, Sendable {
        enum Kind: String, Codable, Sendable { case friend, group }
        var type: Kind
        /// Owner's display name for `friend`, group name for `group`.
        var name: String
    }
    struct Food: Codable, Hashable, Sendable {
        var name: String
        var category: FoodCategory
        var quantity: Double
        var unit: String
        var predictedExpiry: Date?
    }
    var id: String
    var itemId: String
    var ownerId: String
    var ownerName: String
    var groupId: String?
    var status: ShareStatus
    var claimedByMe: Bool
    var createdAt: Date?
    var source: Source
    var item: Food
    /// Non-nil only on a listing you claimed. Backend `feat/friend-qr-pickup`.
    var pickup: Pickup? = nil
    var pickupSet: Bool? = nil
}
struct PantryListingsResponse: Codable, Sendable { let listings: [PantryListing] }

// MARK: - Request board

enum RequestStatus: String, Codable, Sendable, Hashable {
    case open, fulfilled, cancelled
}

/// Sticky-note header source: `me` (author is you), `group` (first visible group audience), else `friend`.
enum RequestSource: String, Codable, Sendable, Hashable {
    case me, group, friend

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = RequestSource(rawValue: raw) ?? .friend
    }
}

/// `audiences` on a request, filtered to the caller. `hiddenCount` counts audiences you can't see.
struct RequestAudiences: Codable, Hashable, Sendable {
    var friends: Bool
    var groups: [GroupRef]
    var hiddenCount: Int

    init(friends: Bool = false, groups: [GroupRef] = [], hiddenCount: Int = 0) {
        self.friends = friends; self.groups = groups; self.hiddenCount = hiddenCount
    }

    private enum CodingKeys: String, CodingKey { case friends, groups, hiddenCount }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        friends = try c.decodeIfPresent(Bool.self, forKey: .friends) ?? false
        groups = try c.decodeIfPresent([GroupRef].self, forKey: .groups) ?? []
        hiddenCount = try c.decodeIfPresent(Int.self, forKey: .hiddenCount) ?? 0
    }
}

struct HelpRequest: Codable, Hashable, Sendable, Identifiable {
    var id: String
    var authorId: String
    var authorName: String
    var text: String
    var status: RequestStatus
    var fulfilledBy: String?
    var fulfilledByName: String?
    var createdAt: Date?
    var audiences: RequestAudiences
    var source: RequestSource
    /// Deprecated by the API (first group in `audiences.groups`).
    var groupId: String?
    var groupName: String?
}
struct HelpRequestResponse: Codable, Sendable { let request: HelpRequest }
struct HelpRequestsResponse: Codable, Sendable { let requests: [HelpRequest] }

/// Body of `POST /requests`: `{text, audiences: {friends, group_ids}}`.
struct NewRequestAudiences: Encodable, Hashable, Sendable {
    var friends: Bool
    var groupIds: [String]
}
struct NewRequestBody: Encodable, Sendable {
    var text: String
    var audiences: NewRequestAudiences
}

// MARK: - People

/// `GET /people/reachable` entry: someone you can hand food to.
struct Person: Codable, Hashable, Sendable, Identifiable {
    enum Kind: String, Codable, Sendable {
        case friend
        case groupMember = "group_member"
    }
    var id: String
    var displayName: String
    var kind: Kind
    var groups: [GroupRef]?
    /// True for whoever claimed the item's listing (pre-selected in the recipient picker).
    var isClaimer: Bool?
}
struct PeopleResponse: Codable, Sendable { let people: [Person] }
