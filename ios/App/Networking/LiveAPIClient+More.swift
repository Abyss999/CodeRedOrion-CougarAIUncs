import Foundation

/// The endpoints added after the Fridge: health, Google sign-in, batch remove/restore, receipt and
/// barcode, Food Pantry, request board, friends, groups and people. Same transport as `LiveAPIClient`.
extension LiveAPIClient {
    static func ids(_ s: String) -> String {
        var allowed = CharacterSet.urlPathAllowed; allowed.remove("/")
        return s.addingPercentEncoding(withAllowedCharacters: allowed) ?? s
    }
    private func noBody() -> Empty? { nil }

    // MARK: Health

    func health() async throws -> Bool {
        let r: HealthResponse = try await send("GET", "/health", body: noBody(), authenticated: false)
        return r.isOK
    }

    // MARK: Auth

    func me() async throws -> Me {
        try await send("GET", "/auth/me", body: noBody())
    }

    func googleSignIn(idToken: String) async throws -> GoogleAuthResult {
        let r: GoogleAuthResult = try await send("POST", "/auth/oauth/google", body: ["id_token": idToken], authenticated: false)
        await auth.signIn(r.session)
        return r
    }

    // MARK: Items

    func removeBatch(ids: [String], outcome: RemoveOutcome, recipient: RecipientChoice) async throws -> [Item] {
        let r: ItemsResponse = try await send("POST", "/items/remove-batch",
                                              body: RemoveBatchBody(itemIds: ids, outcome: outcome, recipient: recipient))
        return r.items
    }

    func restoreBatch(ids: [String]) async throws -> [Item] {
        let r: ItemsResponse = try await send("POST", "/items/restore-batch", body: RestoreBatchBody(itemIds: ids))
        return r.items
    }

    func fromReceipt(imageData: Data) async throws -> ReceiptResponse {
        let (body, contentType) = LiveAPIClient.multipart(fields: [], imageData: imageData)
        return try await perform("POST", "/items/from-receipt", query: [], rawBody: body, contentType: contentType, authenticated: true)
    }

    func barcode(_ code: String) async throws -> BarcodeResult {
        // Barcodes are alphanumeric; drop anything else (spaces, slashes) rather than send it in the path.
        let clean = String(code.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) })
        return try await send("GET", "/items/barcode/\(Self.ids(clean))", body: noBody())
    }

    /// multipart/form-data with an `image` part and optional text fields.
    static func multipart(fields: [(String, String)], imageData: Data) -> (Data, String) {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        func add(_ s: String) { body.append(Data(s.utf8)) }
        for (name, value) in fields {
            add("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n")
        }
        add("--\(boundary)\r\nContent-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n")
        body.append(imageData)
        add("\r\n--\(boundary)--\r\n")
        return (body, "multipart/form-data; boundary=\(boundary)")
    }

    // MARK: Share

    private struct ShareBody: Encodable { let itemId: String; let groupId: String? }

    func listShares() async throws -> [PantryListing] {
        let r: PantryListingsResponse = try await send("GET", "/share", body: noBody())
        return r.listings
    }

    func createShare(itemId: String, groupId: String?) async throws -> Listing {
        let r: ListingResponse = try await send("POST", "/share", body: ShareBody(itemId: itemId, groupId: groupId))
        return r.listing
    }

    func cancelShare(id: String) async throws -> Listing {
        let r: ListingResponse = try await send("DELETE", "/share/\(Self.ids(id))", body: noBody())
        return r.listing
    }

    func claimShare(id: String) async throws -> Listing {
        let r: ListingResponse = try await send("POST", "/share/\(Self.ids(id))/claim", body: noBody())
        return r.listing
    }

    // MARK: Requests

    func listRequests() async throws -> [HelpRequest] {
        let r: HelpRequestsResponse = try await send("GET", "/requests", body: noBody())
        return r.requests
    }

    func listMyRequests() async throws -> [HelpRequest] {
        let r: HelpRequestsResponse = try await send("GET", "/requests", query: [.init(name: "mine", value: "1")], body: noBody())
        return r.requests
    }

    func createRequest(text: String, friends: Bool, groupIds: [String]) async throws -> HelpRequest {
        let r: HelpRequestResponse = try await send("POST", "/requests",
            body: NewRequestBody(text: text, audiences: NewRequestAudiences(friends: friends, groupIds: groupIds)))
        return r.request
    }

    func fulfilRequest(id: String) async throws -> HelpRequest {
        let r: HelpRequestResponse = try await send("POST", "/requests/\(Self.ids(id))/fulfil", body: noBody())
        return r.request
    }

    func cancelRequest(id: String) async throws -> HelpRequest {
        let r: HelpRequestResponse = try await send("DELETE", "/requests/\(Self.ids(id))", body: noBody())
        return r.request
    }

    // MARK: Friends

    func listFriends() async throws -> FriendsResponse {
        try await send("GET", "/friends", body: noBody())
    }

    func requestFriend(email: String) async throws -> Friend {
        let r: FriendResponse = try await send("POST", "/friends", body: ["email": email])
        return r.friend
    }

    func acceptFriend(userId: String) async throws -> Friend {
        let r: FriendResponse = try await send("POST", "/friends/\(Self.ids(userId))/accept", body: noBody())
        return r.friend
    }

    func declineFriend(userId: String) async throws { try await removeFriend(userId: userId) }

    func removeFriend(userId: String) async throws {
        let _: Empty = try await send("DELETE", "/friends/\(Self.ids(userId))", body: noBody())
    }

    // MARK: Groups

    func listGroups() async throws -> [SharingGroup] {
        let r: GroupsResponse = try await send("GET", "/groups", body: noBody())
        return r.groups
    }

    func createGroup(name: String) async throws -> SharingGroup {
        let r: GroupResponse = try await send("POST", "/groups", body: ["name": name])
        return r.group
    }

    func joinGroup(inviteCode: String) async throws -> SharingGroup {
        let r: GroupResponse = try await send("POST", "/groups/join", body: ["invite_code": inviteCode])
        return r.group
    }

    func leaveGroup(id: String) async throws {
        let _: LeftResponse = try await send("POST", "/groups/\(Self.ids(id))/leave", body: noBody())
    }

    func groupDetail(id: String) async throws -> GroupDetail {
        let r: GroupDetailResponse = try await send("GET", "/groups/\(Self.ids(id))", body: noBody())
        return r.group
    }

    func groupPantry(id: String) async throws -> [PantryItem] {
        let r: PantryItemsResponse = try await send("GET", "/groups/\(Self.ids(id))/pantry", body: noBody())
        return r.items
    }

    // MARK: People

    func reachablePeople(itemId: String?) async throws -> [Person] {
        var q: [URLQueryItem] = []
        if let itemId { q.append(.init(name: "item_id", value: itemId)) }
        let r: PeopleResponse = try await send("GET", "/people/reachable", query: q, body: noBody())
        return r.people
    }
}
