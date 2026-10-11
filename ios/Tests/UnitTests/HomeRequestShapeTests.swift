import XCTest
@testable import FoodWasteReducer

/// What the Home tab puts on the wire (Live client + `StubURLProtocol`): the Impact pill asks for
/// the month, the list is flat, and tips and recipes are requested once each.
@MainActor
final class HomeRequestShapeTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite = ""

    override func setUp() {
        StubURLProtocol.reset()
        suite = "HomeRequestShapeTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }
    override func tearDown() { defaults.removePersistentDomain(forName: suite); StubURLProtocol.reset() }

    private func client() -> LiveAPIClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let store = AuthStore(storage: InMemorySessionStorage(AuthSession(token: "tok-1", user: MockData.priya)))
        return LiveAPIClient(baseURL: BaseURLProvider(defaults: defaults, infoValue: nil), auth: store,
                             session: URLSession(configuration: cfg))
    }

    private static let item = """
    {"id":"i-1","owner_id":"u","group_id":null,"name":"Milk","category":"dairy","food_group":"dairy","storage":"fridge","quantity":1,
     "unit":"gal","added_at":"2026-10-10T12:00:00Z","predicted_expiry":"2026-10-20","removed_at":null,"outcome":null,
     "waste_reason":null,"removed_after_expiry":null}
    """
    private static let impact = """
    {"range":"month","saved":{"count":3,"kg":9.6,"money":8.5,"co2e_kg":2.1},"wasted":{"count":0,"kg":0,"money":0,"co2e_kg":0},
     "used":{"count":3,"kg":9.6,"money":8.5,"co2e_kg":2.1},"donated":{"count":0,"kg":0,"money":0,"co2e_kg":0},
     "waste_rate":0,"waste_reasons":[],"previous":null,"weekly":[],"last_6_weeks":[]}
    """
    private static let recipe = """
    {"title":"Soup","minutes":30,"servings":2,"uses_items":[{"item_id":"i-1","name":"Milk","predicted_expiry":"2026-10-20"}],
     "missing_items":[],"steps":["Cook."],"macros":null,"macros_estimated":true}
    """

    private func routeEverything() {
        StubURLProtocol.handler = { r in
            switch r.url?.path {
            case "/items": .init(status: 200, body: Data(#"{"items":[\#(Self.item)]}"#.utf8))
            case "/impact": .init(status: 200, body: Data(Self.impact.utf8))
            case "/tips": .init(status: 200, body: Data(#"{"tips":[{"code":"forgot_leafy","message":"Spinach was forgotten twice."}]}"#.utf8))
            case "/recipes/suggest": .init(status: 200, body: Data(#"{"recipes":[\#(Self.recipe)]}"#.utf8))
            default: .init(status: 404, body: Data(#"{"error":{"code":"not_found","message":"x"}}"#.utf8))
            }
        }
    }

    func testImpactPillRequestsRangeMonth() async throws {
        routeEverything()
        let m = HomeModel(api: client())
        await m.loadIfNeeded()
        let impacts = StubURLProtocol.requests.filter { $0.url?.path == "/impact" }
        XCTAssertEqual(impacts.count, 1, "exactly one impact request")
        XCTAssertEqual(impacts.first?.httpMethod, "GET")
        XCTAssertEqual(impacts.first?.url?.query, "range=month")
        XCTAssertEqual(m.savedKg, 9.6)
    }

    func testHomeMakesTheFourDocumentedCallsAndNothingElse() async {
        routeEverything()
        let m = HomeModel(api: client())
        await m.loadIfNeeded()
        let calls = StubURLProtocol.requests.map { "\($0.httpMethod ?? "?") \($0.url?.path ?? "")" }
        XCTAssertEqual(Set(calls), ["GET /items", "GET /impact", "GET /tips", "POST /recipes/suggest"], "\(calls)")
        XCTAssertEqual(calls.count, 4, "each once: \(calls)")
        let items = StubURLProtocol.requests.first { $0.url?.path == "/items" }
        XCTAssertNil(items?.url?.query, "all storages, flat list")
    }

    func testRecipeRequestIsSmallAndNeedsNoDietaryFilter() async throws {
        routeEverything()
        let m = HomeModel(api: client())
        await m.loadIfNeeded()
        let r = try XCTUnwrap(StubURLProtocol.requests.first { $0.url?.path == "/recipes/suggest" })
        var data = r.httpBody ?? Data()
        if data.isEmpty, let s = r.httpBodyStream {
            s.open(); defer { s.close() }
            var buf = [UInt8](repeating: 0, count: 2048)
            while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; data.append(buf, count: n) }
        }
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertLessThanOrEqual(body["max_results"] as? Int ?? 0, 5)
        XCTAssertNil(body["dietary"])
        XCTAssertEqual(m.recipe?.usesItems.first?.itemId, "i-1", "uses_items decode as objects")
    }

    func testEmptyListSkipsTheRecipeRequest() async {
        StubURLProtocol.handler = { r in
            switch r.url?.path {
            case "/items": .init(status: 200, body: Data(#"{"items":[]}"#.utf8))
            case "/impact": .init(status: 200, body: Data(Self.impact.utf8))
            case "/tips": .init(status: 200, body: Data(#"{"tips":[]}"#.utf8))
            default: .init(status: 500, body: Data())
            }
        }
        let m = HomeModel(api: client())
        await m.loadIfNeeded()
        XCTAssertFalse(StubURLProtocol.requests.contains { $0.url?.path == "/recipes/suggest" })
    }
}
