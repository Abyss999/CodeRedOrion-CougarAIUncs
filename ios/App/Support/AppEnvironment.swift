import SwiftUI
import Observation

/// Dependency entry point. Picks Mock vs Live from `LaunchConfiguration` (DEBUG launch args)
/// and is injected with `.environment(env)`; read it with `@Environment(AppEnvironment.self)`.
@MainActor
@Observable
final class AppEnvironment {
    let api: APIClient
    let auth: AuthStore
    let baseURL: BaseURLProvider
    let launch: LaunchConfiguration

    init(api: APIClient, auth: AuthStore, baseURL: BaseURLProvider = BaseURLProvider(),
         launch: LaunchConfiguration = LaunchConfiguration()) {
        self.api = api
        self.auth = auth
        self.baseURL = baseURL
        self.launch = launch
    }

    static func make(launch: LaunchConfiguration = .current) -> AppEnvironment {
        let baseURL = BaseURLProvider()
        if launch.useMockAPI {
            Haptics.provider = NoOpHaptics()
            let auth = AuthStore(storage: InMemorySessionStorage(
                launch.signedIn ? AuthSession(token: "mock-token", user: MockData.priya) : nil))
            let behavior = MockAPIClient.Behavior(delay: launch.mockDelay, failNetwork: launch.failNetwork)
            let api = MockAPIClient(fixture: MockFixture(name: launch.seed), behavior: behavior,
                                    auth: auth, signedIn: launch.signedIn)
            return AppEnvironment(api: api, auth: auth, baseURL: baseURL, launch: launch)
        }
        let auth = AuthStore()
        return AppEnvironment(api: LiveAPIClient(baseURL: baseURL, auth: auth), auth: auth, baseURL: baseURL, launch: launch)
    }

    /// Mock-backed environment for previews and tests.
    static func preview(fixture: MockFixture = .fridge) -> AppEnvironment {
        let auth = AuthStore(storage: InMemorySessionStorage(AuthSession(token: "mock-token", user: MockData.priya)))
        return AppEnvironment(api: MockAPIClient(fixture: fixture, behavior: .init(delay: .zero), auth: auth, signedIn: true), auth: auth)
    }
}
