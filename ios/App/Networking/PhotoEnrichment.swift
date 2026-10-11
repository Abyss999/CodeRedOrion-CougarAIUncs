import Foundation

// Photo enrichment (backend PR #79): `POST /items/from-photo` takes an optional `enrich` form field and then
// returns `nutrition` on each candidate. Everything here is optional, so the app works against a backend
// without #79 (the field is ignored, `nutrition` stays nil).

/// Per-100 g nutrition estimate. `estimated` is always true. Posted back unchanged with the candidate.
struct Nutrition: Codable, Hashable, Sendable {
    var basis: String
    var kcal: Int
    var proteinG: Double
    var carbsG: Double
    var fatG: Double
    var fiberG: Double?
    var sugarG: Double?
    var sodiumMg: Double?
    var estimated: Bool
}

/// What `enrich` asks Gemini for.
enum PhotoEnrichment: String, Sendable, CaseIterable {
    case expiry, nutrition
}

/// Clients that can send `enrich`. `LiveAPIClient` and `MockAPIClient` adopt it; the `APIClient` protocol
/// is unchanged, so callers fall back to plain `fromPhoto` for any other client.
protocol PhotoEnrichingClient: Sendable {
    func fromPhoto(imageData: Data, mode: PhotoMode, enrich: [PhotoEnrichment]) async throws -> CandidatesResponse
}

enum PhotoRequestTiming {
    /// Detection (skipped past 30 s) plus one 25 s enrich call; BE-20's worst case is about 80 s.
    static let enrichTimeout: TimeInterval = 90
}

extension LiveAPIClient: PhotoEnrichingClient {
    func fromPhoto(imageData: Data, mode: PhotoMode, enrich: [PhotoEnrichment]) async throws -> CandidatesResponse {
        var fields: [(String, String)] = [("mode", mode.rawValue)]
        if !enrich.isEmpty { fields.append(("enrich", enrich.map(\.rawValue).joined(separator: ","))) }
        let (body, contentType) = LiveAPIClient.multipart(fields: fields, imageData: imageData)
        return try await perform("POST", "/items/from-photo", query: [], rawBody: body, contentType: contentType,
                                 authenticated: true, timeout: enrich.isEmpty ? nil : PhotoRequestTiming.enrichTimeout)
    }
}
