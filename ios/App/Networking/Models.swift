import Foundation

// Codable models for docs/API.md. Decoding uses `APICoding.decoder`
// (snake_case keys, ISO-8601 timestamps, `yyyy-MM-dd` dates). Properties are camelCase.

// MARK: - Enums

enum FoodGroup: String, Codable, CaseIterable, Sendable, Hashable {
    case protein, veggies, fruit, dairy, grains, pantry, leftovers, frozen, other

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = FoodGroup(rawValue: raw) ?? .other
    }

    var displayName: String {
        switch self {
        case .protein: "Protein"
        case .veggies: "Veggies"
        case .fruit: "Fruit"
        case .dairy: "Dairy"
        case .grains: "Grains"
        case .pantry: "Pantry"
        case .leftovers: "Leftovers"
        case .frozen: "Frozen"
        case .other: "Other"
        }
    }
}

enum FoodCategory: String, Codable, CaseIterable, Sendable, Hashable {
    case produceLeafy = "produce_leafy", produceHardy = "produce_hardy", dairy, meat, seafood,
         bakery, eggs, leftovers, pantryDry = "pantry_dry", frozen, other

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = FoodCategory(rawValue: raw) ?? .other
    }
}

enum Storage: String, Codable, CaseIterable, Sendable, Hashable {
    case fridge, pantry, freezer
}

enum Freshness: String, Codable, Sendable, Hashable {
    case fresh
    case semiFresh = "semi_fresh"
    case spoiled
}

enum RemoveOutcome: String, Codable, CaseIterable, Sendable, Hashable {
    case used, donated
    case thrownOut = "thrown_out"
}

enum WasteReason: String, Codable, CaseIterable, Sendable, Hashable {
    case expired
    case didntLike = "didnt_like"
    case forgot, other
}

enum ShareStatus: String, Codable, Sendable, Hashable {
    case open, fulfilled, cancelled
}

enum ImpactRange: String, Sendable, CaseIterable {
    case week, month, all
}

enum ItemGrouping: String, Sendable {
    case foodGroup = "food_group"
}

enum PhotoMode: String, Sendable {
    case fridge, single
}

// MARK: - Users and auth

struct User: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let email: String
    let displayName: String
    let createdAt: Date?
}

struct AuthSession: Codable, Hashable, Sendable {
    let token: String
    let user: User
}

// MARK: - Items

/// `share` is added by backend PR 1 (the owner's own open listing on the item).
struct ItemShare: Codable, Hashable, Sendable {
    struct Claimant: Codable, Hashable, Sendable {
        let id: String
        let name: String
    }
    let id: String
    let status: ShareStatus  // open | fulfilled
    let claimedBy: Claimant?
}

struct Item: Codable, Identifiable, Hashable, Sendable {
    let id: String
    var ownerId: String?
    var groupId: String?
    var name: String
    var category: FoodCategory
    var foodGroup: FoodGroup
    var storage: Storage
    var quantity: Double
    var unit: String
    var estWeightKg: Double?
    var estPrice: Double?
    var source: String?
    var addedAt: Date?
    /// Calendar date (local midnight).
    var predictedExpiry: Date?
    var expirySource: String?
    var removedAt: Date?
    var outcome: RemoveOutcome?
    var wasteReason: WasteReason?
    var removedAfterExpiry: Bool?
    /// Backend PR 1. Absent for items never photo-checked.
    var freshness: Freshness?
    var freshnessCheckedAt: Date?
    /// Detector score 0..1; nil for manual items.
    var confidence: Double?
    /// Present on the owner's own items: most recent non-cancelled listing.
    var share: ItemShare?

    var isRemoved: Bool { removedAt != nil }
}

struct ItemsResponse: Codable, Sendable { let items: [Item] }
struct ItemResponse: Codable, Sendable { let item: Item }

struct ItemSection: Codable, Hashable, Sendable, Identifiable {
    let foodGroup: FoodGroup
    var items: [Item]
    var id: FoodGroup { foodGroup }
}
struct SectionsResponse: Codable, Sendable { let sections: [ItemSection] }

/// Result of `listItems`: flat, or grouped by food group when `groupBy` is set.
enum ItemListing: Sendable {
    case flat([Item])
    case grouped([ItemSection])

    var allItems: [Item] {
        switch self {
        case .flat(let items): items
        case .grouped(let sections): sections.flatMap(\.items)
        }
    }
}

/// Body for `POST /items` (one element of `items`). `predictedExpiry` is `yyyy-MM-dd`;
/// use `APIDate.dayString(_:)`.
enum ExpirySource: String, Codable, Sendable, Hashable {
    case `default`, gemini, ml, user
}

struct NewItem: Codable, Hashable, Sendable {
    var name: String
    var category: FoodCategory?
    var foodGroup: FoodGroup?
    var storage: Storage?
    var quantity: Double?
    var unit: String?
    var estPrice: Double?
    var estWeightKg: Double?
    var predictedExpiry: String?
    /// Kept by the server when `predictedExpiry` is sent. Use `.user` (or nil) once the person edited the date.
    var expirySource: ExpirySource?
    var freshness: Freshness?
    var confidence: Double?
    var source: String?
    var groupId: String?

    /// Post a candidate back as-is. Pass `expiryEdited: true` if the user changed the date.
    init(candidate c: Candidate, expiryEdited: Bool = false, source: String? = nil) {
        name = c.name; category = c.category; foodGroup = c.foodGroup; storage = c.storage
        quantity = c.quantity; unit = c.unit; estPrice = c.estPrice
        predictedExpiry = c.predictedExpiry.map { APIDate.dayString($0) }
        expirySource = predictedExpiry == nil ? nil : (expiryEdited ? .user : c.expirySource.flatMap(ExpirySource.init(rawValue:)))
        freshness = c.freshness; confidence = c.confidence
        self.source = source
    }

    init(name: String, category: FoodCategory? = nil, foodGroup: FoodGroup? = nil, storage: Storage? = nil,
         quantity: Double? = nil, unit: String? = nil, estPrice: Double? = nil, estWeightKg: Double? = nil,
         predictedExpiry: String? = nil, expirySource: ExpirySource? = nil, freshness: Freshness? = nil,
         confidence: Double? = nil, source: String? = nil, groupId: String? = nil) {
        self.name = name; self.category = category; self.foodGroup = foodGroup; self.storage = storage
        self.quantity = quantity; self.unit = unit; self.estPrice = estPrice; self.estWeightKg = estWeightKg
        self.predictedExpiry = predictedExpiry; self.expirySource = expirySource; self.freshness = freshness
        self.confidence = confidence; self.source = source; self.groupId = groupId
    }
}

struct CreateItemsRequest: Encodable, Sendable {
    var items: [NewItem]
    var groupId: String?
}

/// Body for `PATCH /items/:id`; nil fields are omitted.
struct ItemPatch: Encodable, Hashable, Sendable {
    var name: String?
    var quantity: Double?
    var unit: String?
    var storage: Storage?
    var category: FoodCategory?
    var foodGroup: FoodGroup?
    var predictedExpiry: String?
    var estPrice: Double?
    var estWeightKg: Double?
    var freshness: Freshness?
    /// Sends `"freshness": null`, clearing freshness and `freshness_checked_at`.
    var clearFreshness = false

    enum CodingKeys: String, CodingKey {
        case name, quantity, unit, storage, category, foodGroup, predictedExpiry, estPrice, estWeightKg, freshness
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(name, forKey: .name)
        try c.encodeIfPresent(quantity, forKey: .quantity)
        try c.encodeIfPresent(unit, forKey: .unit)
        try c.encodeIfPresent(storage, forKey: .storage)
        try c.encodeIfPresent(category, forKey: .category)
        try c.encodeIfPresent(foodGroup, forKey: .foodGroup)
        try c.encodeIfPresent(predictedExpiry, forKey: .predictedExpiry)
        try c.encodeIfPresent(estPrice, forKey: .estPrice)
        try c.encodeIfPresent(estWeightKg, forKey: .estWeightKg)
        if clearFreshness { try c.encodeNil(forKey: .freshness) }
        else { try c.encodeIfPresent(freshness, forKey: .freshness) }
    }
}

struct RemoveRequest: Codable, Hashable, Sendable {
    var outcome: RemoveOutcome
    /// Required iff `outcome == .thrownOut`, rejected otherwise.
    var wasteReason: WasteReason?
    /// Donated only.
    var recipientId: String?
}

// MARK: - Adding food

struct Candidate: Codable, Identifiable, Hashable, Sendable {
    var name: String
    var category: FoodCategory
    var foodGroup: FoodGroup
    var confidence: Double?
    var freshness: Freshness?
    var bbox: [Double]?
    var storage: Storage?
    var quantity: Double?
    var unit: String?
    var estPrice: Double?
    var predictedExpiry: Date?
    var expirySource: String?

    /// Candidates have no server id; this is stable within one response.
    var id: String {
        let box: String = (bbox ?? []).map { String($0) }.joined(separator: ",")
        return name + "|" + box
    }
}

struct CandidatesResponse: Codable, Sendable {
    let candidates: [Candidate]
    let source: String?
}

// MARK: - Impact, tips, recipes

struct ImpactTotals: Codable, Hashable, Sendable {
    var count: Int
    var kg: Double
    var money: Double
    var co2eKg: Double
}

struct WeeklyBucket: Codable, Hashable, Sendable {
    var week: Date
    var saved: Int
    var wasted: Int
}

struct Impact: Codable, Hashable, Sendable {
    var saved: ImpactTotals
    var wasted: ImpactTotals
    var wasteRate: Double
    var weekly: [WeeklyBucket]
}

struct Tip: Codable, Hashable, Sendable, Identifiable {
    let code: String
    let message: String
    var id: String { code }
}
struct TipsResponse: Codable, Sendable { let tips: [Tip] }

struct Macros: Codable, Hashable, Sendable {
    var kcal: Int
    var proteinG: Double
    var carbsG: Double
    var fatG: Double
}

struct Recipe: Codable, Hashable, Sendable, Identifiable {
    var title: String
    var minutes: Int
    /// Item names today. Gap-analysis #12 asks for structured refs (item id + expiry) later.
    var usesItems: [String]
    var missingItems: [String]
    var steps: [String]
    var macros: Macros?
    var macrosEstimated: Bool
    var id: String { title }
}
struct RecipesResponse: Codable, Sendable { let recipes: [Recipe] }

struct RecipeSuggestRequest: Encodable, Sendable {
    var maxResults: Int?
    var dietary: [String]?
}
