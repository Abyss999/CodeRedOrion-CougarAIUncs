import Foundation

/// Everything Wave 2 screens need from the backend (shapes follow docs/API.md).
/// Implemented by `LiveAPIClient` (URLSession) and `MockAPIClient` (in-memory fixtures).
protocol APIClient: Sendable {
    // Auth
    func signup(email: String, password: String, displayName: String) async throws -> AuthSession
    func login(email: String, password: String) async throws -> AuthSession
    /// `DELETE /auth/me` (204). App Store account deletion.
    func deleteAccount() async throws

    // Items
    func listItems(storage: Storage?, groupBy: ItemGrouping?) async throws -> ItemListing
    func createItems(_ items: [NewItem]) async throws -> [Item]
    func patchItem(id: String, _ patch: ItemPatch) async throws -> Item
    /// `POST /items/:id/remove`. `wasteReason` is required iff `outcome == .thrownOut`.
    func removeItem(id: String, outcome: RemoveOutcome, wasteReason: WasteReason?, recipientId: String?) async throws -> Item
    /// `POST /items/:id/restore`. Throws `.notRemoved` (409) or `.restoreWindowExpired` (409, after 10 minutes).
    func restoreItem(id: String) async throws -> Item

    // Adding food (candidates are not saved until `createItems`)
    func fromPhoto(imageData: Data, mode: PhotoMode) async throws -> CandidatesResponse
    func parseText(_ text: String) async throws -> [Candidate]

    // Insights
    func impact(range: ImpactRange) async throws -> Impact
    func tips() async throws -> [Tip]
    func recipesSuggest(maxResults: Int?, dietary: [String]?) async throws -> [Recipe]
}

extension APIClient {
    func createItem(_ item: NewItem) async throws -> Item {
        guard let first = try await createItems([item]).first else {
            throw APIError.decoding("Empty create response")
        }
        return first
    }
    func listItems(storage: Storage? = nil) async throws -> ItemListing {
        try await listItems(storage: storage, groupBy: nil)
    }
    func removeItem(id: String, outcome: RemoveOutcome, wasteReason: WasteReason? = nil) async throws -> Item {
        try await removeItem(id: id, outcome: outcome, wasteReason: wasteReason, recipientId: nil)
    }
    func recipesSuggest() async throws -> [Recipe] { try await recipesSuggest(maxResults: nil, dietary: nil) }
}
