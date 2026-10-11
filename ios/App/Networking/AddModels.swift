import Foundation

// Models for the other add-food paths (receipt, barcode) and the account endpoints.

/// A receipt line: a full candidate plus the printed `price` and `receipt_text`.
struct ReceiptCandidate: Codable, Hashable, Sendable, Identifiable {
    var candidate: Candidate
    var price: Double?
    var receiptText: String?
    var id: String { candidate.id + "|" + (receiptText ?? "") }

    init(candidate: Candidate, price: Double? = nil, receiptText: String? = nil) {
        self.candidate = candidate; self.price = price; self.receiptText = receiptText
    }

    private enum CodingKeys: String, CodingKey { case price, receiptText }

    init(from decoder: Decoder) throws {
        candidate = try Candidate(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        price = try c.decodeIfPresent(Double.self, forKey: .price)
        receiptText = try c.decodeIfPresent(String.self, forKey: .receiptText)
    }

    func encode(to encoder: Encoder) throws {
        try candidate.encode(to: encoder)
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(price, forKey: .price)
        try c.encodeIfPresent(receiptText, forKey: .receiptText)
    }
}

/// `POST /items/from-receipt`. `categorizedBy` is `gemini` or `heuristic`.
struct ReceiptResponse: Codable, Hashable, Sendable {
    var candidates: [ReceiptCandidate]
    var total: Double?
    var categorizedBy: String?
}

/// `GET /items/barcode/:code` -> `{candidate}` with `barcode`, `brand` and `quantity_text` on the candidate.
struct BarcodeResult: Codable, Hashable, Sendable {
    var candidate: Candidate
    var barcode: String?
    var brand: String?
    var quantityText: String?

    init(candidate: Candidate, barcode: String? = nil, brand: String? = nil, quantityText: String? = nil) {
        self.candidate = candidate; self.barcode = barcode; self.brand = brand; self.quantityText = quantityText
    }

    private enum OuterKeys: String, CodingKey { case candidate }
    private enum ExtraKeys: String, CodingKey { case barcode, brand, quantityText }

    init(from decoder: Decoder) throws {
        let inner = try decoder.container(keyedBy: OuterKeys.self).superDecoder(forKey: .candidate)
        candidate = try Candidate(from: inner)
        let c = try inner.container(keyedBy: ExtraKeys.self)
        barcode = try c.decodeIfPresent(String.self, forKey: .barcode)
        brand = try c.decodeIfPresent(String.self, forKey: .brand)
        quantityText = try c.decodeIfPresent(String.self, forKey: .quantityText)
    }

    func encode(to encoder: Encoder) throws {
        var outer = encoder.container(keyedBy: OuterKeys.self)
        try outer.encode(candidate, forKey: .candidate)
    }
}

/// `GET /auth/me` (coming): the signed-in profile. Reads either `{user: {...}}` or the user fields at
/// the top level, so it works whichever the backend ships. Extra fields are optional.
struct Me: Codable, Hashable, Sendable {
    var user: User
    /// False for a Google-only account (no password to change).
    var hasPassword: Bool?
    /// Linked sign-in providers, e.g. ["google"].
    var providers: [String]?

    init(user: User, hasPassword: Bool? = nil, providers: [String]? = nil) {
        self.user = user; self.hasPassword = hasPassword; self.providers = providers
    }

    private enum CodingKeys: String, CodingKey { case user, hasPassword, providers }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        user = try c.decodeIfPresent(User.self, forKey: .user) ?? User(from: decoder)
        hasPassword = try c.decodeIfPresent(Bool.self, forKey: .hasPassword)
        providers = try c.decodeIfPresent([String].self, forKey: .providers)
    }
}

/// `POST /auth/oauth/google`: `{token, user, created}`. `created` is true when this call made the account (201).
struct GoogleAuthResult: Codable, Hashable, Sendable {
    var session: AuthSession
    var created: Bool

    init(session: AuthSession, created: Bool) { self.session = session; self.created = created }

    private enum CodingKeys: String, CodingKey { case created }

    init(from decoder: Decoder) throws {
        session = try AuthSession(from: decoder)
        created = try decoder.container(keyedBy: CodingKeys.self).decodeIfPresent(Bool.self, forKey: .created) ?? false
    }

    func encode(to encoder: Encoder) throws {
        try session.encode(to: encoder)
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(created, forKey: .created)
    }
}

struct HealthResponse: Codable, Hashable, Sendable {
    var status: String
    var isOK: Bool { status == "ok" }
}
