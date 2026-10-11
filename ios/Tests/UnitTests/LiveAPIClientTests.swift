import XCTest
@testable import FoodWasteReducer

/// Intercepts URLSession traffic so LiveAPIClient can be tested without a server.
final class StubURLProtocol: URLProtocol {
    struct Stub { var status: Int; var body: Data }
    nonisolated(unsafe) static var handler: ((URLRequest) -> Stub)?
    nonisolated(unsafe) static var requests: [URLRequest] = []
    private static let lock = NSLock()

    static func reset() { lock.withLock { handler = nil; requests = [] } }
    static func record(_ r: URLRequest) { lock.withLock { requests.append(r) } }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.record(request)
        let stub = Self.handler?(request) ?? Stub(status: 500, body: Data())
        let resp = HTTPURLResponse(url: request.url!, statusCode: stub.status, httpVersion: nil,
                                   headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: stub.body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class LiveAPIClientTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite = ""

    override func setUp() {
        StubURLProtocol.reset()
        suite = "LiveAPIClientTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }
    override func tearDown() { defaults.removePersistentDomain(forName: suite); StubURLProtocol.reset() }

    private func makeSession() -> URLSession {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        return URLSession(configuration: cfg)
    }

    @MainActor private func make(signedIn: Bool = true, info: String? = nil)
        -> (LiveAPIClient, AuthStore, BaseURLProvider) {
        let store = AuthStore(storage: InMemorySessionStorage(signedIn ? AuthSession(token: "tok-1", user: MockData.priya) : nil))
        let base = BaseURLProvider(defaults: defaults, infoValue: info)
        return (LiveAPIClient(baseURL: base, auth: store, session: makeSession()), store, base)
    }

    private func json(_ s: String) -> Data { Data(s.utf8) }

    func testSendsBearerAndHitsDefaultBaseURL() async throws {
        let (c, _, _) = await make()
        StubURLProtocol.handler = { _ in .init(status: 200, body: self.json("{\"items\":[]}")) }
        _ = try await c.listItems(storage: .fridge, groupBy: nil)
        let req = try XCTUnwrap(StubURLProtocol.requests.first)
        XCTAssertEqual(req.url?.host, "127.0.0.1")
        XCTAssertEqual(req.url?.port, 5055)
        XCTAssertEqual(req.url?.path, "/items")
        XCTAssertEqual(req.url?.query, "storage=fridge")
        XCTAssertEqual(req.value(forHTTPHeaderField: "Authorization"), "Bearer tok-1")
    }

    func testGroupedListUsesGroupByQuery() async throws {
        let (c, _, _) = await make()
        StubURLProtocol.handler = { _ in .init(status: 200, body: self.json("{\"sections\":[]}")) }
        let r = try await c.listItems(storage: nil, groupBy: .foodGroup)
        guard case .grouped(let s) = r else { return XCTFail() }
        XCTAssertTrue(s.isEmpty)
        XCTAssertEqual(StubURLProtocol.requests.first?.url?.query, "group_by=food_group")
    }

    #if DEBUG
    func testOverrideIsUsedOnTheNextRequestWithoutRebuild() async throws {
        let (c, _, base) = await make(info: "https://release.example.com")
        StubURLProtocol.handler = { _ in .init(status: 200, body: self.json("{\"items\":[]}")) }
        _ = try await c.listItems(storage: nil, groupBy: nil)
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.host, "release.example.com")

        XCTAssertTrue(base.setOverride("https://tunnel-abc.trycloudflare.com"))
        _ = try await c.listItems(storage: nil, groupBy: nil)
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.host, "tunnel-abc.trycloudflare.com")
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.scheme, "https")

        base.resetOverride()
        _ = try await c.listItems(storage: nil, groupBy: nil)
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.host, "release.example.com")
    }

    func testOverrideWithPathPrefixKeepsPrefix() async throws {
        let (c, _, base) = await make()
        base.setOverride("https://host.example.com/api/")
        StubURLProtocol.handler = { _ in .init(status: 200, body: self.json("{\"tips\":[]}")) }
        _ = try await c.tips()
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.path, "/api/tips")
    }
    #endif

    func test401SignsOut() async throws {
        let (c, store, _) = await make()
        StubURLProtocol.handler = { _ in .init(status: 401, body: self.json("{\"error\":{\"code\":\"unauthorized\",\"message\":\"Token expired\"}}")) }
        do { _ = try await c.listItems(storage: nil, groupBy: nil); XCTFail("expected throw") }
        catch { XCTAssertEqual(error as? APIError, .unauthorized) }
        let signedIn = await store.isSignedIn
        XCTAssertFalse(signedIn, "a 401 on an authenticated call must sign the user out")
    }

    func testLoginWith401IsInvalidCredentialsNotSignOut() async throws {
        let (c, store, _) = await make(signedIn: false)
        StubURLProtocol.handler = { _ in .init(status: 401, body: self.json("{\"error\":{\"code\":\"invalid_credentials\",\"message\":\"Wrong email or password.\"}}")) }
        do { _ = try await c.login(email: "a@b.com", password: "x"); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e.code, "invalid_credentials") }
        let signedIn = await store.isSignedIn
        XCTAssertFalse(signedIn)
        XCTAssertNil(StubURLProtocol.requests.first?.value(forHTTPHeaderField: "Authorization"))
    }

    func testLoginStoresSession() async throws {
        let (c, store, _) = await make(signedIn: false)
        StubURLProtocol.handler = { _ in .init(status: 200, body: self.json(
            "{\"token\":\"new-tok\",\"user\":{\"id\":\"u1\",\"email\":\"p@x.com\",\"display_name\":\"Priya\",\"created_at\":\"2026-10-01T00:00:00Z\"}}")) }
        _ = try await c.login(email: "p@x.com", password: "password1")
        let token = await store.token
        XCTAssertEqual(token, "new-tok")
        let body = try XCTUnwrap(StubURLProtocol.requests.first)
        XCTAssertEqual(body.url?.path, "/auth/login")
        XCTAssertEqual(body.httpMethod, "POST")
    }

    func testServerErrorShapeBecomesAPIError() async throws {
        let (c, _, _) = await make()
        StubURLProtocol.handler = { _ in .init(status: 409, body: self.json("{\"error\":{\"code\":\"already_removed\",\"message\":\"Already removed.\"}}")) }
        do { _ = try await c.removeItem(id: "i1", outcome: .used); XCTFail() }
        catch { XCTAssertEqual(error as? APIError, .server(status: 409, code: "already_removed", message: "Already removed.")) }
        let req = try XCTUnwrap(StubURLProtocol.requests.last)
        XCTAssertEqual(req.url?.path, "/items/i1/remove")
    }

    func testNonJSONErrorBodyStillMapsToServerError() async throws {
        let (c, _, _) = await make()
        StubURLProtocol.handler = { _ in .init(status: 502, body: Data("<html>bad gateway</html>".utf8)) }
        do { _ = try await c.tips(); XCTFail() }
        catch let e as APIError { XCTAssertEqual(e.code, "http_502") }
    }

    func testUndecodableSuccessBodyIsDecodingError() async throws {
        let (c, _, _) = await make()
        StubURLProtocol.handler = { _ in .init(status: 200, body: self.json("{\"nope\":1}")) }
        do { _ = try await c.tips(); XCTFail() }
        catch let e as APIError { if case .decoding = e {} else { XCTFail("\(e)") } }
    }
}
