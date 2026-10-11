import Foundation

/// UI-test launch arguments, parsed once at app start. Only honoured in DEBUG builds.
///
/// - `-UITestMockAPI`          use `MockAPIClient` instead of `LiveAPIClient`
/// - `-UITestSeed <fixture>`   mock fixture name (see `MockFixture`); default `fridge`
/// - `-UITestSignedIn`         start signed in as Priya (no Keychain access)
/// - `-UITestFailNetwork`      every mock call fails with a network error
/// - `-UITestSlowNetwork`      every mock call takes `slowDelay` seconds
/// - `-UITestShowToast`        show the Undo toast on launch inside the Home tab (marker `toast.undo.marker` after Undo)
/// - `-UITestReduceMotion`     force Reduce Motion on (simctl has no reduce_motion switch)
struct LaunchConfiguration: Equatable, Sendable {
    var useMockAPI = false
    var seed: String?
    var signedIn = false
    var failNetwork = false
    var slowNetwork = false
    var showToast = false
    var reduceMotion = false

    static let slowDelay: Duration = .seconds(3)
    static let defaultDelay: Duration = .milliseconds(150)

    static let flagMockAPI = "-UITestMockAPI"
    static let flagSeed = "-UITestSeed"
    static let flagSignedIn = "-UITestSignedIn"
    static let flagFailNetwork = "-UITestFailNetwork"
    static let flagSlowNetwork = "-UITestSlowNetwork"
    static let flagShowToast = "-UITestShowToast"
    static let flagReduceMotion = "-UITestReduceMotion"

    init() {}

    init(arguments: [String]) {
        useMockAPI = arguments.contains(Self.flagMockAPI)
        signedIn = arguments.contains(Self.flagSignedIn)
        failNetwork = arguments.contains(Self.flagFailNetwork)
        slowNetwork = arguments.contains(Self.flagSlowNetwork)
        showToast = arguments.contains(Self.flagShowToast)
        reduceMotion = arguments.contains(Self.flagReduceMotion)
        if let i = arguments.firstIndex(of: Self.flagSeed), arguments.indices.contains(i + 1) {
            seed = arguments[i + 1]
        }
        // Seeding or signing in only makes sense against the mock.
        if seed != nil || signedIn || failNetwork || slowNetwork { useMockAPI = true }
    }

    /// Parsed from the process arguments in DEBUG; always empty in Release.
    static var current: LaunchConfiguration {
        #if DEBUG
        LaunchConfiguration(arguments: ProcessInfo.processInfo.arguments)
        #else
        LaunchConfiguration()
        #endif
    }

    var mockDelay: Duration { slowNetwork ? Self.slowDelay : Self.defaultDelay }
}
