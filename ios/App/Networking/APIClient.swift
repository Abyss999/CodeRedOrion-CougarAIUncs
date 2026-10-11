import Foundation

/// Everything the screens need from the backend (shapes follow docs/API.md).
/// Implemented by `LiveAPIClient` (URLSession) and `MockAPIClient` (in-memory fixtures).
/// The method name is also the key for `MockAPIClient.Behavior` (failures, delays).
protocol APIClient: Sendable {
    // MARK: Health
    /// `GET /health` (no auth). `true` when the API answers `{"status": "ok"}`.
    func health() async throws -> Bool

    // MARK: Auth
    func signup(email: String, password: String, displayName: String) async throws -> AuthSession
    func login(email: String, password: String) async throws -> AuthSession
    /// `GET /auth/me` (coming).
    func me() async throws -> Me
    /// `POST /auth/oauth/google` with the Google Sign-In SDK's `idToken`. Signs in on success.
    /// 409 `account_exists_use_password` / `identity_conflict`, 401 `invalid_token`, 403 `email_not_verified`,
    /// 503 `oauth_not_configured`.
    func googleSignIn(idToken: String) async throws -> GoogleAuthResult
    /// `DELETE /auth/me` (204). App Store account deletion.
    func deleteAccount() async throws

    // MARK: Items
    func listItems(storage: Storage?, groupBy: ItemGrouping?) async throws -> ItemListing
    func createItems(_ items: [NewItem]) async throws -> [Item]
    func patchItem(id: String, _ patch: ItemPatch) async throws -> Item
    /// `POST /items/:id/remove`. `wasteReason` is required iff `outcome == .thrownOut`.
    /// `recipient` is donated only: `.default` omits `recipient_id`, `.none` sends `null`, `.user` sends the id.
    func removeItem(id: String, outcome: RemoveOutcome, wasteReason: WasteReason?, recipient: RecipientChoice) async throws -> Item
    /// `POST /items/:id/restore`. Throws `.notRemoved` (409) or `.restoreWindowExpired` (409, after 10 minutes).
    func restoreItem(id: String) async throws -> Item
    /// `POST /items/remove-batch` (1-100 unique ids; `used` or `donated`). All or nothing, in request order.
    func removeBatch(ids: [String], outcome: RemoveOutcome, recipient: RecipientChoice) async throws -> [Item]
    /// `POST /items/restore-batch`. All or nothing.
    func restoreBatch(ids: [String]) async throws -> [Item]

    // MARK: Adding food (candidates are not saved until `createItems`)
    func fromPhoto(imageData: Data, mode: PhotoMode) async throws -> CandidatesResponse
    func parseText(_ text: String) async throws -> [Candidate]
    /// `POST /items/from-receipt` (multipart `image`).
    func fromReceipt(imageData: Data) async throws -> ReceiptResponse
    /// `GET /items/barcode/:code` (6-14 digits). 404 `not_found` for an unknown product.
    func barcode(_ code: String) async throws -> BarcodeResult

    // MARK: Share / Food Pantry
    /// `GET /share`: the Food Pantry (other people's open listings you can see).
    func listShares() async throws -> [PantryListing]
    /// `POST /share`. No `groupId` = your accepted friends; `groupId` = that group only.
    func createShare(itemId: String, groupId: String?) async throws -> Listing
    /// `DELETE /share/:id` (owner only).
    func cancelShare(id: String) async throws -> Listing
    /// `POST /share/:id/claim`. 409 `already_claimed` / `listing_closed`.
    func claimShare(id: String) async throws -> Listing

    // MARK: Request board
    /// `GET /requests`: open requests you can see.
    func listRequests() async throws -> [HelpRequest]
    /// `GET /requests?mine=1`: your own requests.
    func listMyRequests() async throws -> [HelpRequest]
    /// `POST /requests` with one or more audiences (`friends` and/or `groupIds`, at least one).
    func createRequest(text: String, friends: Bool, groupIds: [String]) async throws -> HelpRequest
    /// `POST /requests/:id/fulfil`.
    func fulfilRequest(id: String) async throws -> HelpRequest
    /// `DELETE /requests/:id` (author only).
    func cancelRequest(id: String) async throws -> HelpRequest

    // MARK: Friends
    func listFriends() async throws -> FriendsResponse
    /// `POST /friends` by email. 404 unknown email, 409 `already_friends` / `request_pending`.
    func requestFriend(email: String) async throws -> Friend
    /// `POST /friends/:user_id/accept`.
    func acceptFriend(userId: String) async throws -> Friend
    /// `DELETE /friends/:user_id` for a pending request sent to you (decline). Same call as unfriend.
    func declineFriend(userId: String) async throws
    /// `DELETE /friends/:user_id` to unfriend, or cancel a request you sent.
    func removeFriend(userId: String) async throws
    /// `GET /friends/code`: your shareable friend code (10 minutes). The QR encodes `url`.
    func friendCode() async throws -> FriendCodeInfo
    /// `POST /friends {code}` (a scanned friend QR). 201 = instant friends; 200 = already friends
    /// (`alreadyFriends`); 400 `invalid_code` expired / forged / malformed.
    func addFriend(code: String) async throws -> FriendAddResult

    // MARK: Groups
    func listGroups() async throws -> [SharingGroup]
    func createGroup(name: String) async throws -> SharingGroup
    /// `POST /groups/join`. 404 bad code, 409 `already_member`.
    func joinGroup(inviteCode: String) async throws -> SharingGroup
    func leaveGroup(id: String) async throws
    /// `GET /groups/:id` (members included). 403 when not a member.
    func groupDetail(id: String) async throws -> GroupDetail
    /// `GET /groups/:id/pantry`.
    func groupPantry(id: String) async throws -> [PantryItem]

    // MARK: Pickup spot (feat/friend-qr-pickup)
    /// `POST /share {item_id, group_id?, pickup?}`. Friends audience sends no `group_id`.
    /// 400 `validation_error` for a pickup with neither a note nor a lat+lng pair.
    func share(itemId: String, audience: ShareAudience, pickup: Pickup?) async throws -> Listing
    /// `PATCH /share/:id {pickup | null}`. Owner only, while the listing is open (409 `listing_closed` otherwise).
    func updatePickup(listingId: String, pickup: Pickup?) async throws -> Listing

    // MARK: People
    /// `GET /people/reachable` (coming): friends and members of your groups.
    /// With `itemId` (an item you own), the person who claimed its open listing has `is_claimer: true`.
    func reachablePeople(itemId: String?) async throws -> [Person]

    // MARK: Insights
    func impact(range: ImpactRange) async throws -> Impact
    func tips() async throws -> [Tip]
    func recipesSuggest(maxResults: Int?, dietary: [String]?) async throws -> [Recipe]
}

extension APIClient {
    func reachablePeople() async throws -> [Person] { try await reachablePeople(itemId: nil) }
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
        try await removeItem(id: id, outcome: outcome, wasteReason: wasteReason, recipient: .default)
    }
    /// Existing call shape: nil omits `recipient_id` (`.default`), an id sends it (`.user`).
    func removeItem(id: String, outcome: RemoveOutcome, wasteReason: WasteReason?, recipientId: String?) async throws -> Item {
        try await removeItem(id: id, outcome: outcome, wasteReason: wasteReason, recipient: RecipientChoice(recipientId: recipientId))
    }
    func removeBatch(ids: [String], outcome: RemoveOutcome) async throws -> [Item] {
        try await removeBatch(ids: ids, outcome: outcome, recipient: .default)
    }
    /// Fallbacks so other conformers (test spies) keep compiling; Live and Mock override both.
    func share(itemId: String, audience: ShareAudience, pickup: Pickup?) async throws -> Listing {
        let listing = try await createShare(itemId: itemId, groupId: audience.groupId)
        guard let pickup else { return listing }
        return try await updatePickup(listingId: listing.id, pickup: pickup)
    }
    func updatePickup(listingId: String, pickup: Pickup?) async throws -> Listing {
        throw APIError.invalidRequest("Pickup spots aren't supported by this client.")
    }
    func createShare(itemId: String) async throws -> Listing { try await createShare(itemId: itemId, groupId: nil) }
    func recipesSuggest() async throws -> [Recipe] { try await recipesSuggest(maxResults: nil, dietary: nil) }
}
