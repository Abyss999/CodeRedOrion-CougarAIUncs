import XCTest

/// Auth screens (Launch, Landing, SignUp, LogIn, SessionExpired, GoogleSignInError) against the mock API.
/// Mock-only values; no real credentials. Ids mirror `AccessibilityID.Auth`.
enum AuthID {
    static let launch = "auth.launch", launchError = "auth.launch.error", launchRetry = "auth.launch.error.retry"
    static let landing = "auth.landing", landingSignUp = "auth.landing.signup", landingLogIn = "auth.landing.login"
    static let expiredBanner = "auth.expired.banner"
    static let signUp = "auth.signup", signUpName = "auth.signup.name", signUpEmail = "auth.signup.email"
    static let signUpPassword = "auth.signup.password", signUpSubmit = "auth.signup.submit"
    static let signUpError = "auth.signup.error", signUpToLogIn = "auth.signup.login"
    static let logIn = "auth.login", logInEmail = "auth.login.email", logInPassword = "auth.login.password"
    static let logInSubmit = "auth.login.submit", logInError = "auth.login.error", logInToSignUp = "auth.login.signup"
    static let signUpPasswordToggle = "auth.signup.password.toggle", logInPasswordToggle = "auth.login.password.toggle"
    static let google = "auth.google", googleAlert = "auth.google.alert"
}

extension XCUIApplication {
    static func authLaunch(_ flags: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-UITestMockAPI"] + flags
        app.launch()
        return app
    }

    func authEl(_ id: String) -> XCUIElement { descendants(matching: .any)[id].firstMatch }
    func field(_ id: String) -> XCUIElement {
        let tf = textFields[id].firstMatch
        return tf.exists ? tf : secureTextFields[id].firstMatch
    }
    func typeInto(_ id: String, _ text: String) {
        let f = field(id)
        XCTAssertTrue(f.waitForExistence(timeout: 5), id)
        f.tap()
        // iOS offers "Fill Strong Password" on sign-up forms and swallows typing; choose our own.
        if f.elementType == .secureTextField, buttons["Fill Strong Password"].waitForExistence(timeout: 2) {
            buttons["Close"].firstMatch.tap()
            f.tap()
        }
        f.typeText(text)
    }
    var onTabs: Bool { tabBars.firstMatch.exists }
}

final class AuthUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func openLogIn(_ app: XCUIApplication) {
        let b = app.buttons[AuthID.landingLogIn]
        XCTAssertTrue(b.waitForExistence(timeout: 5)); b.tap()
        XCTAssertTrue(app.authEl(AuthID.logIn).waitForExistence(timeout: 5))
    }
    private func openSignUp(_ app: XCUIApplication) {
        let b = app.buttons[AuthID.landingSignUp]
        XCTAssertTrue(b.waitForExistence(timeout: 5)); b.tap()
        XCTAssertTrue(app.authEl(AuthID.signUp).waitForExistence(timeout: 5))
    }

    // MARK: Launch routing

    func testValidSessionGoesToTabs() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 8))
        XCTAssertFalse(app.authEl(AuthID.landing).exists)
    }

    func testSignedOutShowsLandingNotTabs() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        XCTAssertTrue(app.authEl(AuthID.landing).waitForExistence(timeout: 8))
        XCTAssertFalse(app.onTabs)
        XCTAssertFalse(app.authEl(AuthID.expiredBanner).exists, "a plain sign-out is not 'session expired'")
        XCTAssertTrue(app.buttons[AuthID.landingSignUp].exists)
        XCTAssertTrue(app.buttons[AuthID.landingLogIn].exists)
    }

    func testServerDownShowsRetryAndRetryStaysOnError() {
        let app = XCUIApplication.authLaunch(["-UITestServerDown"])
        XCTAssertTrue(app.authEl(AuthID.launchError).waitForExistence(timeout: 8), "server down -> error state")
        let retry = app.buttons[AuthID.launchRetry]
        XCTAssertTrue(retry.exists)
        XCTAssertGreaterThanOrEqual(retry.frame.height, 44)
        XCTAssertFalse(app.onTabs)
        XCTAssertFalse(app.authEl(AuthID.landing).exists, "an unreachable server must not look like signed out")
        retry.tap()
        XCTAssertTrue(app.authEl(AuthID.launchError).waitForExistence(timeout: 8), "still down -> still the error")
    }

    func testLaunchIndicatorShownWhileChecking() {
        let app = XCUIApplication.authLaunch(["-UITestSignedIn", "-UITestSlowNetwork"])
        XCTAssertTrue(app.authEl(AuthID.launch).waitForExistence(timeout: 2))
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 12))
    }

    // MARK: Session expired (central)

    func testExpiredSessionShowsBannerAndLogInRecovers() {
        let app = XCUIApplication.authLaunch(["-UITestExpiredSession"])
        let banner = app.authEl(AuthID.expiredBanner)
        XCTAssertTrue(banner.waitForExistence(timeout: 8))
        XCTAssertTrue(app.staticTexts["You were signed out. Log in again to pick up where you left off."].exists || banner.label.contains("signed out"))
        XCTAssertFalse(app.onTabs)
        openLogIn(app)
        app.typeInto(AuthID.logInEmail, "priya@example.com")
        app.typeInto(AuthID.logInPassword, "mock-password-1")
        app.buttons[AuthID.logInSubmit].tap()
        // -UITestExpiredSession keeps 401ing authenticated calls, but sign-in itself succeeds and the tabs show.
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 8))
    }

    // MARK: LogIn

    func testLogInWrongPasswordShowsInlineError() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openLogIn(app)
        app.typeInto(AuthID.logInEmail, "priya@example.com")
        app.typeInto(AuthID.logInPassword, "wrong-password")
        app.buttons[AuthID.logInSubmit].tap()
        let err = app.authEl(AuthID.logInPassword + ".error")
        XCTAssertTrue(err.waitForExistence(timeout: 5), "inline error exposed as an accessibility element")
        XCTAssertTrue(err.label.contains("don't match"), err.label)
        XCTAssertFalse(app.onTabs)
        XCTAssertTrue(app.authEl(AuthID.logIn).exists, "stays on Log in")
    }

    func testLogInEmptyAndMalformedEmailValidation() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openLogIn(app)
        app.buttons[AuthID.logInSubmit].tap()
        XCTAssertTrue(app.authEl(AuthID.logInEmail + ".error").waitForExistence(timeout: 3))
        XCTAssertTrue(app.authEl(AuthID.logInPassword + ".error").exists)
        app.typeInto(AuthID.logInEmail, "not-an-email")
        app.buttons[AuthID.logInSubmit].tap()
        XCTAssertTrue(app.authEl(AuthID.logInEmail + ".error").exists)
    }

    func testLogInSuccessGoesToTabs() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openLogIn(app)
        app.typeInto(AuthID.logInEmail, "priya@example.com")
        app.typeInto(AuthID.logInPassword, "mock-password-1")
        app.buttons[AuthID.logInSubmit].tap()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 8))
    }

    func testLogInUnknownEmailShowsGenericMessageNoEnumeration() {
        // -UITestEmailUnknown affects requestFriend only; login with an unknown email must read like a wrong password.
        let app = XCUIApplication.authLaunch(["-UITestSignedOut", "-UITestEmailUnknown"])
        openLogIn(app)
        app.typeInto(AuthID.logInEmail, "nobody@example.com")
        app.typeInto(AuthID.logInPassword, "wrong-password")
        app.buttons[AuthID.logInSubmit].tap()
        let err = app.authEl(AuthID.logInPassword + ".error")
        XCTAssertTrue(err.waitForExistence(timeout: 5))
        XCTAssertTrue(err.label.contains("That email and password don't match"), err.label)
        XCTAssertFalse(app.authEl(AuthID.logInEmail + ".error").exists, "no per-email error that reveals account existence")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'no bitedown account' OR label CONTAINS[c] 'no account'")).firstMatch.exists)
        XCTAssertFalse(app.onTabs)
    }

    func testPasswordToggleRevealsAndHides() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openLogIn(app)
        app.typeInto(AuthID.logInPassword, "mock-password-1")
        XCTAssertTrue(app.secureTextFields[AuthID.logInPassword].exists)
        let toggle = app.buttons[AuthID.logInPasswordToggle]
        XCTAssertTrue(toggle.exists)
        XCTAssertGreaterThanOrEqual(toggle.frame.height, 44)
        toggle.tap()
        XCTAssertTrue(app.textFields[AuthID.logInPassword].waitForExistence(timeout: 3))
        toggle.tap()
        XCTAssertTrue(app.secureTextFields[AuthID.logInPassword].waitForExistence(timeout: 3))
    }

    // MARK: SignUp

    func testSignUpTakenEmailShowsInlineEmailError() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openSignUp(app)
        app.typeInto(AuthID.signUpName, "Mock Person")
        app.typeInto(AuthID.signUpEmail, "taken@example.com")
        app.typeInto(AuthID.signUpPassword, "mock-password-1")
        app.buttons[AuthID.signUpSubmit].tap()
        let err = app.authEl(AuthID.signUpEmail + ".error")
        XCTAssertTrue(err.waitForExistence(timeout: 5))
        XCTAssertTrue(err.label.localizedCaseInsensitiveContains("already registered"), err.label)
        XCTAssertFalse(app.onTabs)
    }

    func testSignUpClientValidation() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openSignUp(app)
        app.buttons[AuthID.signUpSubmit].tap()
        XCTAssertTrue(app.authEl(AuthID.signUpName + ".error").waitForExistence(timeout: 3))
        XCTAssertTrue(app.authEl(AuthID.signUpEmail + ".error").exists)
        XCTAssertTrue(app.authEl(AuthID.signUpPassword + ".error").exists)
    }

    func testSignUpSuccessGoesToTabs() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openSignUp(app)
        app.typeInto(AuthID.signUpName, "Mock Person")
        app.typeInto(AuthID.signUpEmail, "mock.person@example.com")
        app.typeInto(AuthID.signUpPassword, "mock-password-1")
        app.buttons[AuthID.signUpSubmit].tap()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 8))
    }

    func testSignUpAndLogInLinkToEachOther() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        openSignUp(app)
        app.buttons[AuthID.signUpToLogIn].tap()
        XCTAssertTrue(app.authEl(AuthID.logIn).waitForExistence(timeout: 3))
        app.buttons[AuthID.logInToSignUp].tap()
        XCTAssertTrue(app.authEl(AuthID.signUp).waitForExistence(timeout: 3))
    }

    // MARK: Google

    func testGoogleButtonHiddenWhileClientIDIsEmpty() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut"])
        XCTAssertTrue(app.authEl(AuthID.landing).waitForExistence(timeout: 8))
        XCTAssertFalse(app.authEl(AuthID.google).exists, "Landing")
        openLogIn(app)
        XCTAssertFalse(app.authEl(AuthID.google).exists, "LogIn")
        app.navigationBars.buttons.firstMatch.tap()
        openSignUp(app)
        XCTAssertFalse(app.authEl(AuthID.google).exists, "SignUp")
    }

    func testGoogleButtonSitsBelowEmailFormOnLogInAndSignUp() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut", "-UITestGoogle409"])
        openLogIn(app)
        let g = app.authEl(AuthID.google), submit = app.buttons[AuthID.logInSubmit]
        XCTAssertTrue(g.waitForExistence(timeout: 3))
        XCTAssertGreaterThan(g.frame.minY, submit.frame.maxY, "Google is below the email form (round 3)")
        app.buttons[AuthID.logInToSignUp].tap()
        XCTAssertTrue(app.authEl(AuthID.signUp).waitForExistence(timeout: 3))
        XCTAssertGreaterThan(app.authEl(AuthID.google).frame.minY, app.buttons[AuthID.signUpSubmit].frame.maxY)
    }

    func testInlineLinksAndGoogleButtonMeet44ptTargets() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut", "-UITestGoogle409"])
        openLogIn(app)
        XCTAssertGreaterThanOrEqual(app.buttons[AuthID.logInToSignUp].frame.height, 44, "Create an account link (IOS-61)")
        XCTAssertGreaterThanOrEqual(app.authEl(AuthID.google).frame.height, 44, "Google button (IOS-62)")
        app.buttons[AuthID.logInToSignUp].tap()
        XCTAssertTrue(app.authEl(AuthID.signUp).waitForExistence(timeout: 3))
        XCTAssertGreaterThanOrEqual(app.buttons[AuthID.signUpToLogIn].frame.height, 44, "Log in link (IOS-61)")
    }

    func testGoogle409ShowsErrorCardWithPrefilledEmail() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut", "-UITestGoogle409"])
        XCTAssertTrue(app.authEl(AuthID.landing).waitForExistence(timeout: 8))
        app.authEl(AuthID.google).tap()
        XCTAssertTrue(app.authEl(AuthID.logIn).waitForExistence(timeout: 5), "409 sends the user to Log in")
        let card = app.authEl(AuthID.googleAlert)
        XCTAssertTrue(card.waitForExistence(timeout: 3))
        XCTAssertTrue(card.label.contains("already has a BiteDown password"), card.label)
        XCTAssertEqual(app.field(AuthID.logInEmail).value as? String, "priya@example.com", "email prefilled")
        XCTAssertFalse(app.onTabs)
    }

    func testGoogle409OnLogInShowsCardInPlace() {
        let app = XCUIApplication.authLaunch(["-UITestSignedOut", "-UITestGoogle409"])
        openLogIn(app)
        app.authEl(AuthID.google).tap()
        XCTAssertTrue(app.authEl(AuthID.googleAlert).waitForExistence(timeout: 5))
        XCTAssertFalse(app.onTabs)
    }

    // MARK: Shots (attached to the xcresult; exported by the QA run)

    func testAttachScreens() {
        for scheme in ["Light", "Dark"] {
            let style = ["-AppleInterfaceStyle", scheme]
            func launch(_ flags: [String]) -> XCUIApplication {
                let app = XCUIApplication()
                app.launchArguments = ["-UITestMockAPI"] + flags + style
                app.launch()
                return app
            }
            var app = launch(["-UITestServerDown"])
            XCTAssertTrue(app.authEl(AuthID.launchError).waitForExistence(timeout: 8))
            attachScreenshot(app, name: "LaunchError-\(scheme)")
            app.terminate()
            app = launch(["-UITestSignedOut", "-UITestGoogle409"])
            XCTAssertTrue(app.authEl(AuthID.landing).waitForExistence(timeout: 8))
            attachScreenshot(app, name: "Landing-\(scheme)")
            app.authEl(AuthID.google).tap()
            XCTAssertTrue(app.authEl(AuthID.googleAlert).waitForExistence(timeout: 5))
            attachScreenshot(app, name: "GoogleSignInError-\(scheme)")
            app.navigationBars.buttons.firstMatch.tap()
            openLogIn(app); attachScreenshot(app, name: "LogIn-\(scheme)")
            app.navigationBars.buttons.firstMatch.tap(); openSignUp(app); attachScreenshot(app, name: "SignUp-\(scheme)")
            app.terminate()
            app = launch(["-UITestExpiredSession", "-UITestGoogle409"])
            XCTAssertTrue(app.authEl(AuthID.expiredBanner).waitForExistence(timeout: 8))
            attachScreenshot(app, name: "SessionExpired-\(scheme)")
            app.terminate()
        }
    }
}

/// AX5 subset (run on the iPhone SE): forms stay reachable and targets stay 44 pt.
final class AuthAX5UITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }
    private func launch(_ flags: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-UITestMockAPI"] + flags + ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        return app
    }

    func testLandingAndLogInAtAX5() {
        let app = launch(["-UITestSignedOut"])
        let login = app.buttons[AuthID.landingLogIn]
        XCTAssertTrue(login.waitForExistence(timeout: 8))
        XCTAssertGreaterThanOrEqual(app.buttons[AuthID.landingSignUp].frame.height, 44)
        attachScreenshot(app, name: "Landing-AX5")
        login.tap()
        XCTAssertTrue(app.authEl(AuthID.logIn).waitForExistence(timeout: 5))
        XCTAssertTrue(app.field(AuthID.logInEmail).exists)
        let submit = app.buttons[AuthID.logInSubmit]
        XCTAssertTrue(submit.exists)
        XCTAssertGreaterThanOrEqual(submit.frame.height, 44)
        attachScreenshot(app, name: "LogIn-AX5")
        app.typeInto(AuthID.logInEmail, "priya@example.com")
        app.typeInto(AuthID.logInPassword, "mock-password-1")
        app.buttons[AuthID.logInSubmit].tap()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 8))
    }

    func testSignUpAtAX5AndErrorsStayQueryable() {
        let app = launch(["-UITestSignedOut"])
        app.buttons[AuthID.landingSignUp].tap()
        XCTAssertTrue(app.authEl(AuthID.signUp).waitForExistence(timeout: 5))
        attachScreenshot(app, name: "SignUp-AX5")
        let submit = app.buttons[AuthID.signUpSubmit]
        XCTAssertTrue(submit.exists)
        submit.tap()
        XCTAssertTrue(app.authEl(AuthID.signUpName + ".error").waitForExistence(timeout: 3))
        XCTAssertGreaterThanOrEqual(app.buttons[AuthID.signUpPasswordToggle].frame.height, 44)
    }

    func testServerDownAndExpiredAtAX5() {
        var app = launch(["-UITestServerDown"])
        XCTAssertTrue(app.buttons[AuthID.launchRetry].waitForExistence(timeout: 8))
        XCTAssertGreaterThanOrEqual(app.buttons[AuthID.launchRetry].frame.height, 44)
        attachScreenshot(app, name: "LaunchError-AX5")
        app.terminate()
        app = launch(["-UITestExpiredSession"])
        XCTAssertTrue(app.authEl(AuthID.expiredBanner).waitForExistence(timeout: 8))
        attachScreenshot(app, name: "SessionExpired-AX5")
    }
}
