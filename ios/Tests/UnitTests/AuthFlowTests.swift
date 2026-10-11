import XCTest
@testable import FoodWasteReducer

/// Auth screens QA (Launch, SignUp, LogIn, SessionExpired, GoogleSignInError): the data/contract layer.
/// Mock-only values; no real credentials.
final class AuthFlowTests: XCTestCase {
    private func config(_ args: String...) -> LaunchConfiguration { LaunchConfiguration(arguments: args) }

    // MARK: Launch flags -> mock behaviour

    func testSignedOutFlagBeatsSignedInAndUsesMock() {
        let c = config("-UITestSignedIn", "-UITestSignedOut")
        XCTAssertTrue(c.useMockAPI)
        XCTAssertFalse(c.signedIn)
    }

    func testExpiredSessionFlagStartsSignedInButAuthedCallsFail() {
        let c = config("-UITestExpiredSession")
        XCTAssertTrue(c.signedIn)
        XCTAssertTrue(c.mockBehavior.expiredSession)
    }

    func testServerDownFailsEveryCallIncludingHealth() async throws {
        let behavior = config("-UITestServerDown").mockBehavior
        XCTAssertTrue(behavior.failNetwork)
        let store = await AuthStore(storage: InMemorySessionStorage())
        let c = MockAPIClient(behavior: behavior, auth: store, signedIn: false)
        do { _ = try await c.health(); XCTFail("health must fail when the server is down") }
        catch { XCTAssertTrue((error as? APIError)?.isNetwork == true) }
        do { _ = try await c.me(); XCTFail() }
        catch { XCTAssertTrue((error as? APIError)?.isNetwork == true, "Launch must see a network error (retry), not a 401") }
    }

    func testGoogle409FlagMapsToAccountExistsUsePassword() async throws {
        let behavior = config("-UITestGoogle409").mockBehavior
        let c = MockAPIClient(behavior: behavior, auth: nil)
        do { _ = try await c.googleSignIn(idToken: "mock-id-token"); XCTFail("expected 409") }
        catch let APIError.server(status, code, _) {
            XCTAssertEqual(status, 409)
            XCTAssertEqual(code, "account_exists_use_password")
        }
    }

    // MARK: Launch check (GET /auth/me)

    func testMeWithValidSessionSucceeds() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
        let c = MockAPIClient(behavior: .init(delay: .zero), auth: store, signedIn: true)
        let me = try await c.me()
        XCTAssertEqual(me.user.id, MockData.priya.id)
    }

    func testMeSignedOutIs401() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage())
        let c = MockAPIClient(behavior: .init(delay: .zero), auth: store, signedIn: false)
        do { _ = try await c.me(); XCTFail() }
        catch { XCTAssertEqual(error as? APIError, .unauthorized) }
    }

    // MARK: Global 401 (central, from ANY authenticated call)

    func testExpiredSessionSignsOutFromAnyAuthenticatedCall() async throws {
        let calls: [(String, (MockAPIClient) async throws -> Void)] = [
            ("me", { _ = try await $0.me() }),
            ("listItems", { _ = try await $0.listItems(storage: nil, groupBy: nil) }),
            ("tips", { _ = try await $0.tips() }),
        ]
        for (name, call) in calls {
            let store = await AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
            let c = MockAPIClient(behavior: .init(delay: .zero, expiredSession: true), auth: store, signedIn: true)
            do { try await call(c); XCTFail("\(name) should 401") }
            catch { XCTAssertEqual(error as? APIError, .unauthorized, name) }
            let signedIn = await store.isSignedIn
            XCTAssertFalse(signedIn, "\(name): a 401 must flip AuthStore to signed out so the root can show SessionExpired")
        }
    }

    func testExpiredSessionDoesNotBreakLoginOrHealth() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage())
        let c = MockAPIClient(behavior: .init(delay: .zero, expiredSession: true), auth: store, signedIn: false)
        let ok = try await c.health()
        XCTAssertTrue(ok)
        _ = try await c.login(email: "priya@example.com", password: "mock-password-1")
        let signedIn = await store.isSignedIn
        XCTAssertTrue(signedIn, "logging in again after expiry works")
    }

    // MARK: Form errors from the API

    func testLoginWrongPasswordIs401InvalidCredentialsAndStaysSignedOut() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage())
        let c = MockAPIClient(behavior: .init(delay: .zero), auth: store, signedIn: false)
        do { _ = try await c.login(email: "priya@example.com", password: "wrong-password"); XCTFail() }
        catch let APIError.server(status, code, message) {
            XCTAssertEqual(status, 401); XCTAssertEqual(code, "invalid_credentials"); XCTAssertFalse(message.isEmpty)
        }
        let signedIn = await store.isSignedIn
        XCTAssertFalse(signedIn)
    }

    func testSignupTakenEmailIs409EmailTaken() async throws {
        let c = MockAPIClient(behavior: .init(delay: .zero), auth: nil)
        do { _ = try await c.signup(email: "taken@example.com", password: "mock-password-1", displayName: "Mock"); XCTFail() }
        catch { XCTAssertEqual((error as? APIError)?.code, "email_taken") }
    }

    func testSignupShortPasswordIsValidationError() async throws {
        let c = MockAPIClient(behavior: .init(delay: .zero), auth: nil)
        do { _ = try await c.signup(email: "new@example.com", password: "short", displayName: "Mock"); XCTFail() }
        catch { XCTAssertEqual((error as? APIError)?.code, "validation_error") }
    }

    // MARK: Logout clears the token

    func testSignOutClearsTokenAndStorage() async {
        let storage = InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya))
        let store = await AuthStore(storage: storage)
        let before = await store.token
        XCTAssertEqual(before, "mock-token")
        await store.signOut()
        let after = await store.token
        let signedIn = await store.isSignedIn
        XCTAssertNil(after)
        XCTAssertFalse(signedIn)
        XCTAssertNil(storage.load(), "the persisted session is gone, so a relaunch is signed out")
        let reloaded = await AuthStore(storage: storage)
        let reloadedIn = await reloaded.isSignedIn
        XCTAssertFalse(reloadedIn)
    }

    func testRequestsAfterSignOutCarryNoBearer() async throws {
        StubURLProtocol.reset(); defer { StubURLProtocol.reset() }
        let store = await AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let suite = "AuthFlowTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let c = LiveAPIClient(baseURL: BaseURLProvider(defaults: defaults, infoValue: nil), auth: store, session: URLSession(configuration: cfg))
        StubURLProtocol.handler = { _ in .init(status: 401, body: Data("{\"error\":{\"code\":\"unauthorized\",\"message\":\"x\"}}".utf8)) }
        await store.signOut()
        _ = try? await c.me()
        let header = StubURLProtocol.requests.last?.value(forHTTPHeaderField: "Authorization")
        XCTAssertFalse((header ?? "").contains("mock-token"), "no stale token after logout")
    }

    // MARK: Live client: 401 handling

    @MainActor private func live(handler: @escaping (URLRequest) -> StubURLProtocol.Stub) -> (LiveAPIClient, AuthStore, () -> Void) {
        StubURLProtocol.reset()
        StubURLProtocol.handler = handler
        let store = AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let suite = "AuthFlowTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        let c = LiveAPIClient(baseURL: BaseURLProvider(defaults: defaults, infoValue: nil), auth: store, session: URLSession(configuration: cfg))
        return (c, store, { defaults.removePersistentDomain(forName: suite); StubURLProtocol.reset() })
    }

    func testLive401OnMeSignsOut() async throws {
        let (c, store, cleanup) = await live { _ in .init(status: 401, body: Data("{\"error\":{\"code\":\"unauthorized\",\"message\":\"x\"}}".utf8)) }
        defer { cleanup() }
        do { _ = try await c.me(); XCTFail() } catch { XCTAssertEqual(error as? APIError, .unauthorized) }
        let signedIn = await store.isSignedIn
        XCTAssertFalse(signedIn)
        XCTAssertEqual(StubURLProtocol.requests.last?.url?.path, "/auth/me")
    }

    func testLiveGoogle409IsServerErrorNotSignOut() async throws {
        let (c, store, cleanup) = await live { _ in
            .init(status: 409, body: Data("{\"error\":{\"code\":\"account_exists_use_password\",\"message\":\"exists\"}}".utf8)) }
        defer { cleanup() }
        do { _ = try await c.googleSignIn(idToken: "mock-id-token"); XCTFail() }
        catch { XCTAssertEqual((error as? APIError)?.code, "account_exists_use_password") }
        let signedIn = await store.isSignedIn
        XCTAssertTrue(signedIn, "a 409 is a form error, never a sign-out")
    }

    func testLive401OnSignupDoesNotSignOutExistingSession() async throws {
        let (c, store, cleanup) = await live { _ in
            .init(status: 401, body: Data("{\"error\":{\"code\":\"invalid_credentials\",\"message\":\"nope\"}}".utf8)) }
        defer { cleanup() }
        do { _ = try await c.login(email: "a@example.com", password: "mock-password-1"); XCTFail() }
        catch { XCTAssertEqual((error as? APIError)?.code, "invalid_credentials") }
        let signedIn = await store.isSignedIn
        XCTAssertTrue(signedIn)
    }

    // MARK: Google button visibility (client id)

    func testGoogleHiddenWhileClientIDEmptyOrPlaceholder() {
        for raw: Any? in [nil, "", "   ", "$(GOOGLE_IOS_CLIENT_ID)", 42] {
            XCTAssertFalse(GoogleSignInConfig.isEnabled(infoValue: raw), "\(String(describing: raw))")
            XCTAssertNil(GoogleSignInConfig.clientID(infoValue: raw))
        }
    }

    func testGoogleShownWithMockClientID() {
        XCTAssertTrue(GoogleSignInConfig.isEnabled(infoValue: "mock-client-id.apps.example.invalid"))
        XCTAssertEqual(GoogleSignInConfig.clientID(infoValue: "  mock-client-id  "), "mock-client-id")
    }

    // MARK: Error copy for the drawn / undrawn Google errors

    func testGoogleErrorCodesAreStableStrings() {
        // Codes the GoogleSignInError screen must map (SCREENS.md row 31).
        let codes = ["account_exists_use_password", "identity_conflict", "email_not_verified", "oauth_not_configured"]
        for code in codes {
            let e = APIError.server(status: 409, code: code, message: "m")
            XCTAssertEqual(e.code, code)
        }
    }

    // MARK: sessionExpired state

    func testExpireSessionFlagLifecycle() async {
        let store = await AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
        await store.expireSession()
        var expired = await store.sessionExpired, signedIn = await store.isSignedIn
        XCTAssertTrue(expired); XCTAssertFalse(signedIn)
        await store.signIn(AuthSession(token: "mock-token-2", user: MockData.priya))
        expired = await store.sessionExpired
        XCTAssertFalse(expired, "signing in again clears the banner")
        await store.expireSession()
        await store.signOut()
        expired = await store.sessionExpired
        XCTAssertFalse(expired, "a deliberate logout is not an expiry")
    }

    func testExpireSessionWhenAlreadySignedOutIsNotAnExpiry() async {
        let store = await AuthStore(storage: InMemorySessionStorage())
        await store.expireSession()
        let expired = await store.sessionExpired
        XCTAssertFalse(expired, "first launch with no token shows Landing, not SessionExpired")
    }

    func testExpiredMockLaunchSetsSessionExpired() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
        let c = MockAPIClient(behavior: config("-UITestExpiredSession").mockBehavior, auth: store, signedIn: true)
        _ = try? await c.me()
        let expired = await store.sessionExpired
        XCTAssertTrue(expired)
    }

    func testLive401SetsSessionExpiredAndClearsStorage() async throws {
        let (c, store, cleanup) = await live { _ in .init(status: 401, body: Data("{\"error\":{\"code\":\"unauthorized\",\"message\":\"x\"}}".utf8)) }
        defer { cleanup() }
        _ = try? await c.listItems(storage: nil, groupBy: nil)
        let expired = await store.sessionExpired, token = await store.token
        XCTAssertTrue(expired); XCTAssertNil(token)
    }
}
