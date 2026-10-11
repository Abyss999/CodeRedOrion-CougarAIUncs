import Foundation

extension MockAPIClient: PhotoEnrichingClient {
    /// Same behaviour flags as `fromPhoto` (`-UITestPhotoNone`, `-UITestPhoto502`); with `nutrition` the
    /// candidates carry a sample per-100 g estimate so the round trip can be tested.
    func fromPhoto(imageData: Data, mode: PhotoMode, enrich: [PhotoEnrichment]) async throws -> CandidatesResponse {
        let plain = try await fromPhoto(imageData: imageData, mode: mode)
        guard enrich.contains(.nutrition) else { return plain }
        let sample = Nutrition(basis: "per_100g", kcal: 40, proteinG: 2, carbsG: 6, fatG: 0.5, fiberG: nil, sugarG: nil, sodiumMg: nil, estimated: true)
        return CandidatesResponse(candidates: plain.candidates.map { var c = $0; c.nutrition = sample; return c }, source: plain.source)
    }
}
