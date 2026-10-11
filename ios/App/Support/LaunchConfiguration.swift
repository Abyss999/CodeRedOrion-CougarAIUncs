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
/// - `-UITestSignedOut`       start signed out (wins over `-UITestSignedIn`); the Auth screens show
/// - `-UITestExpiredSession`  signed in, but every authenticated call 401s and signs out (session-expired path)
/// - `-UITestServerDown`      every call fails like an unreachable server, including `GET /health`
/// - `-UITestPhotoNone`       photo and receipt scans find nothing (empty candidates)
/// - `-UITestPhoto502`        `from-photo` and `from-receipt` fail with 502 `upstream_unavailable`
/// - `-UITestCameraDenied`    screens behave as if camera access is denied (no mock call; read `launch.cameraDenied`)
/// - `-UITestTossFails`       removing with outcome `thrown_out` fails (used / donated still work)
/// - `-UITestReceiptUnavailable` the Add sheet shows the Receipt tile as unavailable (as on the live API while OCR is down)
/// - `-UITestMicDenied`      the Add text "Say it" mic behaves as if microphone access is denied (PermissionCard)
/// - `-UITestRecipes502`      `POST /recipes/suggest` fails with 502 `upstream_unavailable`
/// - `-UITestGoogle409`       Google sign-in fails with 409 `account_exists_use_password`
/// - `-UITestClaimConflict`   claiming a listing fails with 409 `already_claimed`
/// - `-UITestEmailUnknown`    adding a friend fails with 404 `not_found` (unknown email)
/// - `-UITestFailBatch`       `remove-batch` and `restore-batch` fail (network error)
/// - `-UITestFailShare`       `POST /share` fails (network error)
/// - `-UITestOpenImpact`     present ImpactView full screen from RootTabView on launch (until Home links to it)
/// - `-UITestImpactFailOnce` the first `GET /impact` fails (network), the retry succeeds
/// - `-UITestFailSocial`     the Social lists (requests, my requests, Food Pantry) fail with a network error
/// - `-UITestFailFulfil`      `POST /requests/:id/fulfil` and `POST /requests` fail (network error)
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
    var signedOut = false
    var expiredSession = false
    var serverDown = false
    var photoNone = false
    var photo502 = false
    var cameraDenied = false
    var tossFails = false
    var receiptUnavailable = false
    var micDenied = false
    var recipes502 = false
    var google409 = false
    var claimConflict = false
    var emailUnknown = false
    var failBatch = false
    var failShare = false
    var openImpact = false
    var impactFailOnce = false
    var failSocial = false
    var failFulfil = false
    /// `-UITestUndoWindow <seconds>`; nil keeps `UndoToastTiming`.
    var undoWindow: Duration?

    static let slowDelay: Duration = .seconds(3)
    static let defaultDelay: Duration = .milliseconds(150)

    static let flagFailSocial = "-UITestFailSocial"
    static let flagFailFulfil = "-UITestFailFulfil"
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
    static let flagSignedOut = "-UITestSignedOut"
    static let flagExpiredSession = "-UITestExpiredSession"
    static let flagServerDown = "-UITestServerDown"
    static let flagPhotoNone = "-UITestPhotoNone"
    static let flagPhoto502 = "-UITestPhoto502"
    static let flagCameraDenied = "-UITestCameraDenied"
    static let flagTossFails = "-UITestTossFails"
    static let flagReceiptUnavailable = "-UITestReceiptUnavailable"
    static let flagMicDenied = "-UITestMicDenied"
    static let flagRecipes502 = "-UITestRecipes502"
    static let flagGoogle409 = "-UITestGoogle409"
    static let flagClaimConflict = "-UITestClaimConflict"
    static let flagEmailUnknown = "-UITestEmailUnknown"
    static let flagFailBatch = "-UITestFailBatch"
    static let flagFailShare = "-UITestFailShare"
    static let flagOpenImpact = "-UITestOpenImpact"
    static let flagImpactFailOnce = "-UITestImpactFailOnce"
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
        signedOut = arguments.contains(Self.flagSignedOut)
        expiredSession = arguments.contains(Self.flagExpiredSession)
        serverDown = arguments.contains(Self.flagServerDown)
        photoNone = arguments.contains(Self.flagPhotoNone)
        photo502 = arguments.contains(Self.flagPhoto502)
        cameraDenied = arguments.contains(Self.flagCameraDenied)
        tossFails = arguments.contains(Self.flagTossFails)
        receiptUnavailable = arguments.contains(Self.flagReceiptUnavailable)
        micDenied = arguments.contains(Self.flagMicDenied)
        recipes502 = arguments.contains(Self.flagRecipes502)
        google409 = arguments.contains(Self.flagGoogle409)
        claimConflict = arguments.contains(Self.flagClaimConflict)
        emailUnknown = arguments.contains(Self.flagEmailUnknown)
        failBatch = arguments.contains(Self.flagFailBatch)
        failShare = arguments.contains(Self.flagFailShare)
        openImpact = arguments.contains(Self.flagOpenImpact)
        impactFailOnce = arguments.contains(Self.flagImpactFailOnce)
        failSocial = arguments.contains(Self.flagFailSocial)
        failFulfil = arguments.contains(Self.flagFailFulfil)
        if signedOut { signedIn = false }
        if expiredSession { signedIn = true }
        if let i = arguments.firstIndex(of: Self.flagUndoWindow), arguments.indices.contains(i + 1),
           let seconds = Double(arguments[i + 1]), seconds > 0 {
            undoWindow = .milliseconds(Int(seconds * 1000))
        }
        if let i = arguments.firstIndex(of: Self.flagSeed), arguments.indices.contains(i + 1) {
            seed = arguments[i + 1]
        }
        // Seeding or signing in only makes sense against the mock.
        if seed != nil || signedIn || failNetwork || slowNetwork || loadingForever || failList || failListOnce
            || failRemove || failRestore || restoreNotRemoved || slowRemove || slowRestore
            || signedOut || expiredSession || serverDown || photoNone || photo502 || cameraDenied || tossFails || receiptUnavailable || recipes502 || google409 || claimConflict || emailUnknown || failBatch || failShare || impactFailOnce || failSocial || failFulfil || micDenied { useMockAPI = true }
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
        var b = MockAPIClient.Behavior(delay: mockDelay, failNetwork: failNetwork || serverDown)
        let offline = APIError.network("The Internet connection appears to be offline.")
        if failList { b.failures["listItems"] = offline }
        if failListOnce { b.failFirst["listItems"] = 1 }
        if failRemove { b.failures["removeItem"] = offline }
        if failRestore { b.failures["restoreItem"] = offline }
        if restoreNotRemoved { b.failures["restoreItem"] = .notRemoved }
        if loadingForever { b.delays["listItems"] = Self.foreverDelay }
        if slowRemove { b.delays["removeItem"] = Self.slowDelay }
        if slowRestore { b.delays["restoreItem"] = Self.slowDelay }
        let badGateway = APIError.server(status: 502, code: "upstream_unavailable", message: "That service isn't available right now. Try again in a moment.")
        b.expiredSession = expiredSession
        b.photoFindsNothing = photoNone
        if photo502 { b.failures["fromPhoto"] = badGateway; b.failures["fromReceipt"] = badGateway }
        if tossFails { b.failThrownOut = offline }
        if recipes502 { b.failures["recipesSuggest"] = badGateway }
        if google409 {
            b.failures["googleSignIn"] = .server(status: 409, code: "account_exists_use_password",
                                                 message: "An account with that email already exists. Log in with your email and password.")
        }
        if claimConflict {
            b.failures["claimShare"] = .server(status: 409, code: "already_claimed", message: "Someone else just claimed that.")
        }
        if emailUnknown {
            b.failures["requestFriend"] = .server(status: 404, code: "not_found", message: "No BiteDown account has that email.")
        }
        if failBatch { b.failures["removeBatch"] = offline; b.failures["restoreBatch"] = offline }
        if failShare { b.failures["createShare"] = offline }
        b.emptyImpact = seed == "empty"
        if impactFailOnce { b.failFirst["impact"] = 1 }
        if failSocial { for k in ["listRequests", "listMyRequests", "listShares"] { b.failures[k] = offline } }
        if failFulfil { b.failures["fulfilRequest"] = offline; b.failures["createRequest"] = offline }
        if loadingForever { for k in ["listRequests", "listMyRequests", "listShares"] { b.delays[k] = Self.foreverDelay } }
        return b
    }
}
