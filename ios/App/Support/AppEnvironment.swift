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
    /// Set with `-UITestRecordHaptics` (DEBUG, mock): every haptic is recorded for the `debug.haptics` probe.
    let hapticsRecorder: ObservableRecordingHaptics?

    init(api: APIClient, auth: AuthStore, baseURL: BaseURLProvider = BaseURLProvider(),
         launch: LaunchConfiguration = LaunchConfiguration(), hapticsRecorder: ObservableRecordingHaptics? = nil) {
        self.api = api
        self.hapticsRecorder = hapticsRecorder
        self.auth = auth
        self.baseURL = baseURL
        self.launch = launch
    }

    static func make(launch: LaunchConfiguration = .current) -> AppEnvironment {
        let baseURL = BaseURLProvider()
        if launch.useMockAPI {
            let recorder = launch.recordHaptics ? ObservableRecordingHaptics() : nil
            Haptics.provider = recorder ?? NoOpHaptics()
            let auth = AuthStore(storage: InMemorySessionStorage(
                launch.signedIn ? AuthSession(token: "mock-token", user: MockData.priya) : nil))
            let behavior = launch.mockBehavior
            let api = MockAPIClient(fixture: MockFixture(name: launch.seed), behavior: behavior,
                                    auth: auth, signedIn: launch.signedIn)
            return AppEnvironment(api: api, auth: auth, baseURL: baseURL, launch: launch, hapticsRecorder: recorder)
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
