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
/// - `-UITestLoadingForever`   the item list never returns (skeleton stays up)
/// - `-UITestFailList`         only the item list fails (error state); other calls succeed
/// - `-UITestFailListOnce`     the first item list call fails, the retry succeeds
/// - `-UITestFailRemove`       only `POST /items/:id/remove` fails (rollback)
/// - `-UITestFailRestore`      only `POST /items/:id/restore` fails (Undo rollback)
/// - `-UITestRestoreNotRemoved` restore throws 409 `not_removed` (the item is already active)
/// - `-UITestSlowRemove`       remove takes `slowDelay`
/// - `-UITestSlowRestore`      restore takes `slowDelay`
/// - `-UITestRecordHaptics`    record haptics and expose them on the `debug.haptics` probe
/// - `-UITestUndoWindow <s>`   Undo toast window in seconds (e.g. 30) instead of 5 s (15 s with assistive tech)
struct LaunchConfiguration: Equatable, Sendable {
    var useMockAPI = false
    var seed: String?
    var signedIn = false
    var failNetwork = false
    var slowNetwork = false
    var showToast = false
    var reduceMotion = false
    var loadingForever = false
    var failList = false
    var failListOnce = false
    var failRemove = false
    var failRestore = false
    var restoreNotRemoved = false
    var slowRemove = false
    var slowRestore = false
    var recordHaptics = false
    /// `-UITestUndoWindow <seconds>`; nil keeps `UndoToastTiming`.
    var undoWindow: Duration?

    static let slowDelay: Duration = .seconds(3)
    static let defaultDelay: Duration = .milliseconds(150)

    static let flagMockAPI = "-UITestMockAPI"
    static let flagSeed = "-UITestSeed"
    static let flagSignedIn = "-UITestSignedIn"
    static let flagFailNetwork = "-UITestFailNetwork"
    static let flagSlowNetwork = "-UITestSlowNetwork"
    static let flagShowToast = "-UITestShowToast"
    static let flagReduceMotion = "-UITestReduceMotion"
    static let flagLoadingForever = "-UITestLoadingForever"
    static let flagFailList = "-UITestFailList"
    static let flagFailListOnce = "-UITestFailListOnce"
    static let flagFailRemove = "-UITestFailRemove"
    static let flagFailRestore = "-UITestFailRestore"
    static let flagRestoreNotRemoved = "-UITestRestoreNotRemoved"
    static let flagSlowRemove = "-UITestSlowRemove"
    static let flagSlowRestore = "-UITestSlowRestore"
    static let flagRecordHaptics = "-UITestRecordHaptics"
    static let flagUndoWindow = "-UITestUndoWindow"
    /// Effectively "never" for `-UITestLoadingForever`.
    static let foreverDelay: Duration = .seconds(3600)

    init() {}

    init(arguments: [String]) {
        useMockAPI = arguments.contains(Self.flagMockAPI)
        signedIn = arguments.contains(Self.flagSignedIn)
        failNetwork = arguments.contains(Self.flagFailNetwork)
        slowNetwork = arguments.contains(Self.flagSlowNetwork)
        showToast = arguments.contains(Self.flagShowToast)
        reduceMotion = arguments.contains(Self.flagReduceMotion)
        loadingForever = arguments.contains(Self.flagLoadingForever)
        failList = arguments.contains(Self.flagFailList)
        failListOnce = arguments.contains(Self.flagFailListOnce)
        failRemove = arguments.contains(Self.flagFailRemove)
        failRestore = arguments.contains(Self.flagFailRestore)
        restoreNotRemoved = arguments.contains(Self.flagRestoreNotRemoved)
        slowRemove = arguments.contains(Self.flagSlowRemove)
        slowRestore = arguments.contains(Self.flagSlowRestore)
        recordHaptics = arguments.contains(Self.flagRecordHaptics)
        if let i = arguments.firstIndex(of: Self.flagUndoWindow), arguments.indices.contains(i + 1),
           let seconds = Double(arguments[i + 1]), seconds > 0 {
            undoWindow = .milliseconds(Int(seconds * 1000))
        }
        if let i = arguments.firstIndex(of: Self.flagSeed), arguments.indices.contains(i + 1) {
            seed = arguments[i + 1]
        }
        // Seeding or signing in only makes sense against the mock.
        if seed != nil || signedIn || failNetwork || slowNetwork || loadingForever || failList || failListOnce
            || failRemove || failRestore || restoreNotRemoved || slowRemove || slowRestore { useMockAPI = true }
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

    /// The mock behaviour these flags ask for.
    var mockBehavior: MockAPIClient.Behavior {
        var b = MockAPIClient.Behavior(delay: mockDelay, failNetwork: failNetwork)
        let offline = APIError.network("The Internet connection appears to be offline.")
        if failList { b.failures["listItems"] = offline }
        if failListOnce { b.failFirst["listItems"] = 1 }
        if failRemove { b.failures["removeItem"] = offline }
        if failRestore { b.failures["restoreItem"] = offline }
        if restoreNotRemoved { b.failures["restoreItem"] = .notRemoved }
        if loadingForever { b.delays["listItems"] = Self.foreverDelay }
        if slowRemove { b.delays["removeItem"] = Self.slowDelay }
        if slowRestore { b.delays["restoreItem"] = Self.slowDelay }
        return b
    }
}
