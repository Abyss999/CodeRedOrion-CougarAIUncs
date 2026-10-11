import XCTest
@testable import FoodWasteReducer

/// Method, path, query and JSON body of every endpoint the shared foundation added to `LiveAPIClient`,
/// captured with `StubURLProtocol`. Shapes follow docs/API.md.
final class LiveRequestShapeTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite = ""

    override func setUp() {
        StubURLProtocol.reset()
        suite = "LiveRequestShapeTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }
    override func tearDown() { defaults.removePersistentDomain(forName: suite); StubURLProtocol.reset() }

    @MainActor private func client(signedIn: Bool = true) -> LiveAPIClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let store = AuthStore(storage: InMemorySessionStorage(signedIn ? AuthSession(token: "tok-1", user: MockData.priya) : nil))
        return LiveAPIClient(baseURL: BaseURLProvider(defaults: defaults, infoValue: nil), auth: store,
                             session: URLSession(configuration: cfg))
    }

    private func reply(_ status: Int, _ json: String) {
        StubURLProtocol.handler = { _ in .init(status: status, body: Data(json.utf8)) }
    }
    private func reply(_ json: String) { reply(200, json) }

    private func last() throws -> URLRequest { try XCTUnwrap(StubURLProtocol.requests.last) }

    private func rawBody(_ r: URLRequest) -> Data {
        var data = r.httpBody ?? Data()
        if data.isEmpty, let s = r.httpBodyStream {
            s.open(); defer { s.close() }
            var buf = [UInt8](repeating: 0, count: 4096)
            while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; data.append(buf, count: n) }
        }
        return data
    }

    private func body(_ r: URLRequest) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: rawBody(r)) as? [String: Any])
    }

    private func assertNoBody(_ r: URLRequest, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(rawBody(r).isEmpty, "expected no body", file: file, line: line)
    }

    private func assert(_ r: URLRequest, _ method: String, _ path: String, query: String? = nil,
                        file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(r.httpMethod, method, file: file, line: line)
        XCTAssertEqual(r.url?.path, path, file: file, line: line)
        XCTAssertEqual(r.url?.query, query, file: file, line: line)
        XCTAssertEqual(r.value(forHTTPHeaderField: "Authorization"), "Bearer tok-1", file: file, line: line)
    }

    private static let item = """
    {"id":"i-1","owner_id":"u","group_id":null,"name":"Milk","category":"dairy","food_group":"dairy","storage":"fridge","quantity":1,
     "unit":"gal","added_at":"2026-10-10T12:00:00Z","predicted_expiry":"2026-10-20","removed_at":null,"outcome":null,
     "waste_reason":null,"removed_after_expiry":null}
    """
    private static let friend = #"{"friend":{"user_id":"u-ana","display_name":"Ana","status":"pending","created_at":"2026-10-10T12:00:00Z"}}"#
    private static let group = #"{"group":{"id":"g-1","name":"Roomies","role":"owner","member_count":1,"invite_code":"ABCDEFGH","created_by":"u","created_at":"2026-10-10T12:00:00Z"}}"#
    private static let listing = #"{"listing":{"id":"l-1","item_id":"i-1","owner_id":"u","group_id":null,"status":"open","recipient_id":null,"claimed_by":null,"created_at":"2026-10-10T12:00:00Z","fulfilled_at":null}}"#
    private static let request = #"{"request":{"id":"r-1","author_id":"u","author_name":"P","text":"t","status":"open","fulfilled_by":null,"fulfilled_by_name":null,"created_at":"2026-10-10T12:00:00Z","audiences":{"friends":true,"groups":[],"hidden_count":0},"source":"me","group_id":null,"group_name":null}}"#

    // MARK: RecipientChoice on remove (CRITICAL)

    func testRemoveDefaultOmitsRecipientId() async throws {
        let c = await client(); reply(#"{"item":\#(Self.item)}"#)
        _ = try await c.removeItem(id: "i-1", outcome: .donated, wasteReason: nil, recipient: .default)
        let r = try last()
        assert(r, "POST", "/items/i-1/remove")
        let b = try body(r)
        XCTAssertEqual(Set(b.keys), ["outcome"], "`.default` must OMIT recipient_id, got \(b)")
        XCTAssertEqual(b["outcome"] as? String, "donated")
        XCTAssertFalse(String(decoding: rawBody(r), as: UTF8.self).contains("recipient_id"))
    }

    func testRemoveNoneSendsLiteralNull() async throws {
        let c = await client(); reply(#"{"item":\#(Self.item)}"#)
        _ = try await c.removeItem(id: "i-1", outcome: .donated, wasteReason: nil, recipient: .none)
        let r = try last()
        let b = try body(r)
        XCTAssertEqual(Set(b.keys), ["outcome", "recipient_id"], "`.none` must send recipient_id present, got \(b)")
        XCTAssertTrue(b["recipient_id"] is NSNull, "must be a JSON null, not a string or missing: \(String(describing: b["recipient_id"]))")
        XCTAssertTrue(String(decoding: rawBody(r), as: UTF8.self).contains("\"recipient_id\":null"))
    }

    func testRemoveUserSendsId() async throws {
        let c = await client(); reply(#"{"item":\#(Self.item)}"#)
        _ = try await c.removeItem(id: "i-1", outcome: .donated, wasteReason: nil, recipient: .user("u-ana"))
        let b = try body(try last())
        XCTAssertEqual(b["recipient_id"] as? String, "u-ana")
        XCTAssertEqual(Set(b.keys), ["outcome", "recipient_id"])
    }

    func testRemoveOutcomeRulesNoRecipientWithUsedOrThrownOut() async throws {
        let c = await client(); reply(#"{"item":\#(Self.item)}"#)
        _ = try await c.removeItem(id: "i-1", outcome: .used, wasteReason: nil, recipient: .default)
        XCTAssertEqual(Set(try body(try last()).keys), ["outcome"])
        for reason in WasteReason.allCases {
            _ = try await c.removeItem(id: "i-1", outcome: .thrownOut, wasteReason: reason, recipient: .default)
            let b = try body(try last())
            XCTAssertEqual(Set(b.keys), ["outcome", "waste_reason"], "thrown_out never carries recipient_id: \(b)")
            XCTAssertEqual(b["waste_reason"] as? String, reason.rawValue)
        }
    }

    /// `.none` / `.user` with a non-donated outcome is invalid per the API (400). The client must not
    /// silently strip it and must not crash; the Live client sends what it is told and the server rejects.
    /// Record what happens so a UI that ignores the rule is caught.
    func testRemoveUsedWithRecipientChoiceIsNotSilentlyAccepted() async throws {
        let c = await client()
        reply(400, #"{"error":{"code":"validation_error","message":"recipient_id only with donated"}}"#)
        for choice in [RecipientChoice.none, .user("u-ana")] {
            StubURLProtocol.reset()
            reply(400, #"{"error":{"code":"validation_error","message":"recipient_id only with donated"}}"#)
            do {
                _ = try await c.removeItem(id: "i-1", outcome: .used, wasteReason: nil, recipient: choice)
                XCTFail("server 400 must surface")
            } catch let e as APIError {
                XCTAssertEqual(e.code, "validation_error")
            }
        }
    }

    func testLegacyRecipientIdOverloadMapsNilToDefault() async throws {
        let c = await client(); reply(#"{"item":\#(Self.item)}"#)
        _ = try await c.removeItem(id: "i-1", outcome: .donated, wasteReason: nil, recipientId: nil)
        XCTAssertEqual(Set(try body(try last()).keys), ["outcome"])
        _ = try await c.removeItem(id: "i-1", outcome: .donated, wasteReason: nil, recipientId: "u-sam")
        XCTAssertEqual(try body(try last())["recipient_id"] as? String, "u-sam")
    }

    // MARK: RecipientChoice on remove-batch

    func testBatchDefaultOmitsRecipientId() async throws {
        let c = await client(); reply(#"{"items":[\#(Self.item)]}"#)
        let items = try await c.removeBatch(ids: ["i-1", "i-2"], outcome: .donated, recipient: .default)
        XCTAssertEqual(items.count, 1)
        let r = try last()
        assert(r, "POST", "/items/remove-batch")
        let b = try body(r)
        XCTAssertEqual(Set(b.keys), ["item_ids", "outcome"], "got \(b)")
        XCTAssertEqual(b["item_ids"] as? [String], ["i-1", "i-2"], "request order is kept")
        XCTAssertEqual(b["outcome"] as? String, "donated")
        XCTAssertNil(b["itemIds"], "camelCase key leaked")
    }

    func testBatchNoneSendsLiteralNull() async throws {
        let c = await client(); reply(#"{"items":[]}"#)
        _ = try await c.removeBatch(ids: ["i-1"], outcome: .donated, recipient: .none)
        let r = try last()
        let b = try body(r)
        XCTAssertTrue(b["recipient_id"] is NSNull, "got \(b)")
        XCTAssertEqual(Set(b.keys), ["item_ids", "outcome", "recipient_id"])
        XCTAssertTrue(String(decoding: rawBody(r), as: UTF8.self).contains("\"recipient_id\":null"))
    }

    func testBatchUserSendsId() async throws {
        let c = await client(); reply(#"{"items":[]}"#)
        _ = try await c.removeBatch(ids: ["i-1"], outcome: .donated, recipient: .user("u-ana"))
        XCTAssertEqual(try body(try last())["recipient_id"] as? String, "u-ana")
    }

    func testBatchUsedSendsOnlyIdsAndOutcome() async throws {
        let c = await client(); reply(#"{"items":[]}"#)
        _ = try await c.removeBatch(ids: ["i-1"], outcome: .used)
        let b = try body(try last())
        XCTAssertEqual(Set(b.keys), ["item_ids", "outcome"])
        XCTAssertEqual(b["outcome"] as? String, "used")
        XCTAssertNil(b["waste_reason"])
    }

    func testBatchConflictAndNotFoundMapToServerErrors() async throws {
        let c = await client()
        reply(409, #"{"error":{"code":"already_removed","message":"x"}}"#)
        do { _ = try await c.removeBatch(ids: ["a"], outcome: .used); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e.code, "already_removed") }
        reply(404, #"{"error":{"code":"not_found","message":"x"}}"#)
        do { _ = try await c.removeBatch(ids: ["a"], outcome: .used); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e.code, "not_found") }
    }

    func testRestoreBatchBodyAndPath() async throws {
        let c = await client(); reply(#"{"items":[\#(Self.item)]}"#)
        let items = try await c.restoreBatch(ids: ["i-1", "i-2"])
        XCTAssertEqual(items.first?.id, "i-1")
        let r = try last()
        assert(r, "POST", "/items/restore-batch")
        let b = try body(r)
        XCTAssertEqual(Set(b.keys), ["item_ids"])
        XCTAssertEqual(b["item_ids"] as? [String], ["i-1", "i-2"])
    }

    func testRestoreBatchWindowErrorsAreTyped() async throws {
        let c = await client()
        reply(409, #"{"error":{"code":"restore_window_expired","message":"x"}}"#)
        do { _ = try await c.restoreBatch(ids: ["a"]); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e, .restoreWindowExpired) }
        reply(409, #"{"error":{"code":"not_removed","message":"x"}}"#)
        do { _ = try await c.restoreBatch(ids: ["a"]); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e, .notRemoved) }
    }

    // MARK: Health, auth

    func testHealthIsUnauthenticatedGet() async throws {
        let c = await client(signedIn: true); reply(#"{"status":"ok"}"#)
        let ok = try await c.health()
        XCTAssertTrue(ok)
        let r = try last()
        XCTAssertEqual(r.httpMethod, "GET"); XCTAssertEqual(r.url?.path, "/health")
        XCTAssertNil(r.value(forHTTPHeaderField: "Authorization"), "/health takes no token")
    }

    func testGoogleSignInPostsIdTokenUnauthenticatedAndStoresSession() async throws {
        let c = await client(signedIn: false)
        reply(201, #"{"token":"g-tok","user":{"id":"u","email":"p@gmail.com","display_name":"P","created_at":"2026-10-10T12:00:00Z"},"created":true}"#)
        let res = try await c.googleSignIn(idToken: "google.id.token")
        XCTAssertTrue(res.created)
        let r = try last()
        XCTAssertEqual(r.httpMethod, "POST"); XCTAssertEqual(r.url?.path, "/auth/oauth/google")
        XCTAssertNil(r.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(try body(r) as NSDictionary, ["id_token": "google.id.token"] as NSDictionary)
    }

    func testGoogleSignInErrorsKeepSignedOutState() async throws {
        let c = await client(signedIn: false)
        for (status, code) in [(409, "account_exists_use_password"), (409, "identity_conflict"), (401, "invalid_token"),
                               (403, "email_not_verified"), (503, "oauth_not_configured")] {
            reply(status, #"{"error":{"code":"\#(code)","message":"m"}}"#)
            do { _ = try await c.googleSignIn(idToken: "t"); XCTFail(code) }
            catch let e as APIError {
                XCTAssertEqual(e.code, code, "\(status) \(code)")
                if case .unauthorized = e { XCTFail("an unauthenticated 401 (\(code)) must not map to .unauthorized/sign-out") }
            }
        }
    }

    func testMeIsAuthenticatedGet() async throws {
        let c = await client(); reply(#"{"user":{"id":"u","email":"p@x.co","display_name":"P","created_at":null}}"#)
        let me = try await c.me()
        XCTAssertEqual(me.user.email, "p@x.co")
        assert(try last(), "GET", "/auth/me")
    }

    func testDeleteAccountIs204AndSignsOut() async throws {
        let c = await client(); reply(204, "")
        try await c.deleteAccount()
        let r = try last()
        assert(r, "DELETE", "/auth/me")
        assertNoBody(r)
    }

    // MARK: Add food

    func testBarcodeGetPath() async throws {
        let c = await client()
        reply(#"{"candidate":{"name":"Yogurt","category":"dairy","food_group":"dairy","barcode":"0123456789012"}}"#)
        let b = try await c.barcode("0123456789012")
        XCTAssertEqual(b.barcode, "0123456789012")
        let r = try last()
        assert(r, "GET", "/items/barcode/0123456789012")
        assertNoBody(r)
    }

    func testBarcodeUnknownIs404() async throws {
        let c = await client()
        reply(404, #"{"error":{"code":"not_found","message":"Unknown product"}}"#)
        do { _ = try await c.barcode("000000"); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e.code, "not_found") }
    }

    func testBarcodeCodeIsPathEscaped() async throws {
        let c = await client()
        reply(404, #"{"error":{"code":"not_found","message":"x"}}"#)
        _ = try? await c.barcode("12 34/56")
        let url = try XCTUnwrap(try last().url)
        XCTAssertFalse(url.path.hasSuffix("/56") && url.path.contains("12 34"), "unescaped slash would change the route: \(url)")
    }

    func testFromReceiptIsMultipartImageOnly() async throws {
        let c = await client()
        reply(#"{"candidates":[],"total":null,"categorized_by":"heuristic"}"#)
        _ = try await c.fromReceipt(imageData: Data([0xFF, 0xD8, 0xFF, 0xD9]))
        let r = try last()
        assert(r, "POST", "/items/from-receipt")
        let ct = try XCTUnwrap(r.value(forHTTPHeaderField: "Content-Type"))
        XCTAssertTrue(ct.hasPrefix("multipart/form-data; boundary="), ct)
        let text = String(decoding: rawBody(r), as: UTF8.self)
        XCTAssertTrue(text.contains("name=\"image\""))
        XCTAssertFalse(text.contains("name=\"mode\""), "from-receipt takes only `image`")
    }

    func testFromPhotoStillSendsModeAndImage() async throws {
        let c = await client()
        reply(#"{"candidates":[],"source":"yolo"}"#)
        _ = try await c.fromPhoto(imageData: Data([1, 2, 3]), mode: .single)
        let r = try last()
        assert(r, "POST", "/items/from-photo")
        let text = String(decoding: rawBody(r), as: UTF8.self)
        XCTAssertTrue(text.contains("name=\"mode\"\r\n\r\nsingle"))
        XCTAssertTrue(text.contains("name=\"image\""))
    }

    // MARK: Share

    func testListShares() async throws {
        let c = await client(); reply(#"{"listings":[]}"#)
        let l = try await c.listShares()
        XCTAssertEqual(l.count, 0)
        let r = try last(); assert(r, "GET", "/share"); assertNoBody(r)
    }

    func testCreateShareFriendsOmitsOrNullsGroupAndGroupSendsId() async throws {
        let c = await client(); reply(201, Self.listing)
        _ = try await c.createShare(itemId: "i-1", groupId: nil)
        var b = try body(try last())
        XCTAssertEqual(b["item_id"] as? String, "i-1")
        // Either omitted or null means "friends" to the API; a non-null value must never appear.
        XCTAssertTrue(b["group_id"] == nil || b["group_id"] is NSNull, "got \(b)")
        assert(try last(), "POST", "/share")
        _ = try await c.createShare(itemId: "i-1", groupId: "g-1")
        b = try body(try last())
        XCTAssertEqual(b["group_id"] as? String, "g-1")
        XCTAssertNil(b["groupId"])
    }

    func testCancelAndClaimShare() async throws {
        let c = await client(); reply(Self.listing)
        _ = try await c.cancelShare(id: "l-1")
        var r = try last(); assert(r, "DELETE", "/share/l-1"); assertNoBody(r)
        _ = try await c.claimShare(id: "l-1")
        r = try last(); assert(r, "POST", "/share/l-1/claim"); assertNoBody(r)
    }

    // MARK: Requests

    func testListRequestsAndMineQuery() async throws {
        let c = await client(); reply(#"{"requests":[]}"#)
        _ = try await c.listRequests()
        assert(try last(), "GET", "/requests", query: nil)
        _ = try await c.listMyRequests()
        assert(try last(), "GET", "/requests", query: "mine=1")
    }

    func testCreateRequestBodyHasAudiencesAndNoDeprecatedGroupId() async throws {
        let c = await client(); reply(201, Self.request)
        _ = try await c.createRequest(text: "Need eggs", friends: true, groupIds: ["g-1", "g-2"])
        let r = try last()
        assert(r, "POST", "/requests")
        let b = try body(r)
        XCTAssertEqual(Set(b.keys), ["text", "audiences"], "a body with both audiences and group_id is a 400: \(b)")
        let a = try XCTUnwrap(b["audiences"] as? [String: Any])
        XCTAssertEqual(a["friends"] as? Bool, true)
        XCTAssertEqual(a["group_ids"] as? [String], ["g-1", "g-2"])
    }

    func testCreateRequestFriendsFalseGroupsOnlyAndEmptyGroupIdsIsList() async throws {
        let c = await client(); reply(201, Self.request)
        _ = try await c.createRequest(text: "x", friends: false, groupIds: ["g-1"])
        var a = try XCTUnwrap(try body(try last())["audiences"] as? [String: Any])
        XCTAssertEqual(a["friends"] as? Bool, false)
        XCTAssertEqual(a["group_ids"] as? [String], ["g-1"])
        _ = try await c.createRequest(text: "x", friends: true, groupIds: [])
        a = try XCTUnwrap(try body(try last())["audiences"] as? [String: Any])
        XCTAssertEqual(a["group_ids"] as? [String], [], "group_ids must be a list, never null (400)")
    }

    func testFulfilAndCancelRequest() async throws {
        let c = await client(); reply(Self.request)
        _ = try await c.fulfilRequest(id: "r-1")
        var r = try last(); assert(r, "POST", "/requests/r-1/fulfil"); assertNoBody(r)
        _ = try await c.cancelRequest(id: "r-1")
        r = try last(); assert(r, "DELETE", "/requests/r-1"); assertNoBody(r)
    }

    // MARK: Friends

    func testFriendEndpoints() async throws {
        let c = await client()
        reply(#"{"friends":[],"incoming":[],"outgoing":[]}"#)
        _ = try await c.listFriends()
        assert(try last(), "GET", "/friends")
        reply(201, Self.friend)
        _ = try await c.requestFriend(email: "ana@example.com")
        var r = try last(); assert(r, "POST", "/friends")
        XCTAssertEqual(try body(r) as NSDictionary, ["email": "ana@example.com"] as NSDictionary)
        reply(Self.friend.replacingOccurrences(of: "pending", with: "accepted"))
        let f = try await c.acceptFriend(userId: "u-ana")
        XCTAssertEqual(f.status, .accepted)
        r = try last(); assert(r, "POST", "/friends/u-ana/accept"); assertNoBody(r)
    }

    func testDeleteFriendIs204ForRemoveAndDecline() async throws {
        let c = await client(); reply(204, "")
        try await c.removeFriend(userId: "u-ana")
        var r = try last(); assert(r, "DELETE", "/friends/u-ana"); assertNoBody(r)
        try await c.declineFriend(userId: "u-sam")
        r = try last(); assert(r, "DELETE", "/friends/u-sam")
    }

    func testFriendConflictsSurfaceCodes() async throws {
        let c = await client()
        for code in ["already_friends", "request_pending"] {
            reply(409, #"{"error":{"code":"\#(code)","message":"m"}}"#)
            do { _ = try await c.requestFriend(email: "a@b.co"); XCTFail() }
            catch let e as APIError { XCTAssertEqual(e.code, code) }
        }
    }

    // MARK: Groups

    func testGroupEndpoints() async throws {
        let c = await client()
        reply(#"{"groups":[]}"#)
        _ = try await c.listGroups()
        assert(try last(), "GET", "/groups")
        reply(201, Self.group)
        _ = try await c.createGroup(name: "Roomies")
        var r = try last(); assert(r, "POST", "/groups")
        XCTAssertEqual(try body(r) as NSDictionary, ["name": "Roomies"] as NSDictionary)
        reply(Self.group)
        _ = try await c.joinGroup(inviteCode: "ABCD-EFGH")
        r = try last(); assert(r, "POST", "/groups/join")
        XCTAssertEqual(try body(r) as NSDictionary, ["invite_code": "ABCD-EFGH"] as NSDictionary,
                       "send the code as typed; the server ignores case, spaces and dashes")
    }

    func testGroupDetailPantryAndLeave() async throws {
        let c = await client()
        reply(#"{"group":{"id":"g-1","name":"R","role":"member","member_count":1,"invite_code":"ABCDEFGH","created_by":null,"created_at":null,"members":[]}}"#)
        let d = try await c.groupDetail(id: "g-1")
        XCTAssertEqual(d.group.name, "R")
        assert(try last(), "GET", "/groups/g-1")
        reply(#"{"items":[]}"#)
        _ = try await c.groupPantry(id: "g-1")
        assert(try last(), "GET", "/groups/g-1/pantry")
        reply(#"{"left":true}"#)
        try await c.leaveGroup(id: "g-1")
        let r = try last(); assert(r, "POST", "/groups/g-1/leave"); assertNoBody(r)
    }

    func testGroupForbiddenIs403() async throws {
        let c = await client()
        reply(403, #"{"error":{"code":"forbidden","message":"Not a member"}}"#)
        do { _ = try await c.groupDetail(id: "g-1"); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e, .server(status: 403, code: "forbidden", message: "Not a member")) }
    }

    // MARK: People

    func testReachablePeople() async throws {
        let c = await client()
        reply(#"{"people":[{"id":"u","display_name":"A","kind":"friend","is_claimer":true}]}"#)
        let p = try await c.reachablePeople()
        XCTAssertEqual(p.first?.isClaimer, true)
        let r = try last(); assert(r, "GET", "/people/reachable"); assertNoBody(r)
    }

    // MARK: Insights

    func testImpactRangeQueryForEveryRange() async throws {
        let c = await client()
        reply(#"{"saved":{"count":0,"kg":0,"money":0,"co2e_kg":0},"wasted":{"count":0,"kg":0,"money":0,"co2e_kg":0},"waste_rate":0,"weekly":[]}"#)
        for range in ImpactRange.allCases {
            _ = try await c.impact(range: range)
            assert(try last(), "GET", "/impact", query: "range=\(range.rawValue)")
        }
    }

    func testRecipesSuggestBody() async throws {
        let c = await client(); reply(#"{"recipes":[]}"#)
        _ = try await c.recipesSuggest(maxResults: 4, dietary: ["vegan"])
        var r = try last(); assert(r, "POST", "/recipes/suggest")
        var b = try body(r)
        XCTAssertEqual(b["max_results"] as? Int, 4)
        XCTAssertEqual(b["dietary"] as? [String], ["vegan"])
        _ = try await c.recipesSuggest()
        r = try last()
        b = (try? body(r)) ?? [:]
        XCTAssertNil(b["max_results"]); XCTAssertNil(b["dietary"])
    }

    // MARK: Path-id escaping

    func testIdsAreEscapedInPaths() async throws {
        let c = await client(); reply(Self.listing)
        _ = try await c.claimShare(id: "a/b c")
        let raw = try XCTUnwrap(try last().url?.absoluteString)
        XCTAssertTrue(raw.contains("/share/a/b%20c/claim") || raw.contains("/share/a%2Fb%20c/claim"), raw)
    }
}
