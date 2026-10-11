import XCTest
@testable import FoodWasteReducer

/// Wire shape of `POST /items/:id/remove` and `POST /items/:id/restore` (docs/API.md, Items):
/// `outcome` is one of used | donated | thrown_out, `waste_reason` only with thrown_out,
/// `recipient_id` only with donated, and nil fields are omitted (not sent as null).
final class RemoveRequestShapeTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite = ""

    override func setUp() {
        StubURLProtocol.reset()
        suite = "RemoveRequestShapeTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }
    override func tearDown() { defaults.removePersistentDomain(forName: suite); StubURLProtocol.reset() }

    @MainActor private func client() -> LiveAPIClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let store = AuthStore(storage: InMemorySessionStorage(AuthSession(token: "tok-1", user: MockData.priya)))
        return LiveAPIClient(baseURL: BaseURLProvider(defaults: defaults, infoValue: nil), auth: store,
                             session: URLSession(configuration: cfg))
    }

    private static let itemJSON = """
    {"item": {"id": "item-spinach", "name": "Baby spinach", "category": "produce_leafy", "food_group": "veggies",
      "storage": "fridge", "quantity": 5, "unit": "oz", "added_at": "2026-10-04T12:00:00+00:00",
      "predicted_expiry": "2026-10-11", "expiry_source": "default", "removed_at": null, "outcome": null,
      "waste_reason": null, "removed_after_expiry": null, "share": null}}
    """

    private func ok() { StubURLProtocol.handler = { _ in .init(status: 200, body: Data(Self.itemJSON.utf8)) } }

    /// URLProtocol sees `httpBody` as a stream.
    private func body(_ r: URLRequest) throws -> [String: Any] {
        var data = r.httpBody ?? Data()
        if data.isEmpty, let s = r.httpBodyStream {
            s.open(); defer { s.close() }
            var buf = [UInt8](repeating: 0, count: 4096)
            while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; data.append(buf, count: n) }
        }
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func lastRequest() throws -> URLRequest { try XCTUnwrap(StubURLProtocol.requests.last) }

    func testUsedSendsOnlyOutcome() async throws {
        let c = await client(); ok()
        _ = try await c.removeItem(id: "item-spinach", outcome: .used, wasteReason: nil, recipientId: nil)
        let r = try lastRequest()
        XCTAssertEqual(r.httpMethod, "POST")
        XCTAssertEqual(r.url?.path, "/items/item-spinach/remove")
        XCTAssertEqual(r.value(forHTTPHeaderField: "Content-Type"), "application/json")
        let b = try body(r)
        XCTAssertEqual(b["outcome"] as? String, "used")
        XCTAssertEqual(Set(b.keys), ["outcome"], "nil waste_reason / recipient_id must be omitted, got \(b)")
    }

    func testThrownOutSendsSnakeCaseWasteReasonForEveryReason() async throws {
        let c = await client(); ok()
        for (reason, raw) in [(WasteReason.expired, "expired"), (.forgot, "forgot"), (.didntLike, "didnt_like"), (.other, "other")] {
            _ = try await c.removeItem(id: "item-spinach", outcome: .thrownOut, wasteReason: reason, recipientId: nil)
            let b = try body(try lastRequest())
            XCTAssertEqual(b["outcome"] as? String, "thrown_out")
            XCTAssertEqual(b["waste_reason"] as? String, raw)
            XCTAssertNil(b["wasteReason"], "camelCase key leaked")
            XCTAssertNil(b["recipient_id"])
        }
    }

    func testDonatedWithRecipientSendsRecipientId() async throws {
        let c = await client(); ok()
        _ = try await c.removeItem(id: "item-spinach", outcome: .donated, wasteReason: nil, recipientId: "user-marcus")
        let b = try body(try lastRequest())
        XCTAssertEqual(b["outcome"] as? String, "donated")
        XCTAssertEqual(b["recipient_id"] as? String, "user-marcus")
        XCTAssertNil(b["waste_reason"])
        XCTAssertEqual(Set(b.keys), ["outcome", "recipient_id"])
    }

    /// "Someone else" (or no listing): donated with no recipient; the server defaults to the claimer.
    func testDonatedWithoutRecipientOmitsKey() async throws {
        let c = await client(); ok()
        _ = try await c.removeItem(id: "item-spinach", outcome: .donated, wasteReason: nil, recipientId: nil)
        XCTAssertEqual(Set(try body(try lastRequest()).keys), ["outcome"])
    }

    func testRestoreIsBodylessPost() async throws {
        let c = await client(); ok()
        let item = try await c.restoreItem(id: "item-spinach")
        XCTAssertEqual(item.id, "item-spinach")
        let r = try lastRequest()
        XCTAssertEqual(r.httpMethod, "POST")
        XCTAssertEqual(r.url?.path, "/items/item-spinach/restore")
        XCTAssertTrue((r.httpBody ?? Data()).isEmpty && r.httpBodyStream == nil, "restore takes no body")
    }

    func testRestoreConflictsMapToTypedErrors() async throws {
        let c = await client()
        StubURLProtocol.handler = { _ in .init(status: 409, body: Data(#"{"error":{"code":"restore_window_expired","message":"Too late."}}"#.utf8)) }
        do { _ = try await c.restoreItem(id: "x"); XCTFail("expected throw") }
        catch let e as APIError { XCTAssertEqual(e, .restoreWindowExpired) }
        StubURLProtocol.handler = { _ in .init(status: 409, body: Data(#"{"error":{"code":"not_removed","message":"Active."}}"#.utf8)) }
        do { _ = try await c.restoreItem(id: "x"); XCTFail("expected throw") }
        catch let e as APIError { XCTAssertEqual(e, .notRemoved) }
    }

    func testRemoveConflictIsServerError() async throws {
        let c = await client()
        StubURLProtocol.handler = { _ in .init(status: 409, body: Data(#"{"error":{"code":"already_removed","message":"Already removed."}}"#.utf8)) }
        do { _ = try await c.removeItem(id: "x", outcome: .used, wasteReason: nil, recipientId: nil); XCTFail("expected throw") }
        catch let e as APIError {
            guard case .server(let status, let code, _) = e else { return XCTFail("\(e)") }
            XCTAssertEqual(status, 409); XCTAssertEqual(code, "already_removed")
        }
    }

    /// The encoder itself (also used by the mock path and any batch code).
    func testRemoveRequestEncoderOmitsNil() throws {
        let data = try APICoding.encoder.encode(RemoveRequest(outcome: .thrownOut, wasteReason: .didntLike, recipientId: nil))
        let o = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(o as NSDictionary, ["outcome": "thrown_out", "waste_reason": "didnt_like"] as NSDictionary)
    }
}
