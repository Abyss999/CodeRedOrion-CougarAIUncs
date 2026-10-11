import XCTest

/// Debug-only runtime API base URL entry point (long-press the version label on Home).
final class BaseURLDebugUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func openSheet(_ app: XCUIApplication) {
        let label = app.buttons[ID.versionLabel]
        XCTAssertTrue(label.waitForExistence(timeout: 10), "version label missing on Home")
        label.press(forDuration: 1.2)
        XCTAssertTrue(app.textFields[ID.urlField].waitForExistence(timeout: 5), "debug sheet did not open")
    }

    /// The override persists in UserDefaults across launches, so each test resets it through the
    /// sheet first to start from the default regardless of earlier runs.
    private func launch() -> XCUIApplication { .mockSignedIn() }

    private func resetViaSheet(_ app: XCUIApplication) {
        app.buttons[ID.urlReset].tap()
        XCTAssertTrue(app.staticTexts[ID.urlCurrent].label.contains("127.0.0.1:5055"))
    }

    func testVersionLabelHasLabelAndHint() {
        let app = launch()
        let label = app.buttons[ID.versionLabel]
        XCTAssertTrue(label.waitForExistence(timeout: 10))
        XCTAssertTrue(label.label.hasPrefix("v"), label.label)
    }

    func testSaveValidOverrideUpdatesInUseAndResetRestoresDefault() {
        let app = launch()
        openSheet(app)
        resetViaSheet(app)
        let current = app.staticTexts[ID.urlCurrent]

        let field = app.textFields[ID.urlField]
        field.tap()
        field.typeText("https://demo-tunnel.trycloudflare.com")
        app.buttons[ID.urlSave].tap()
        XCTAssertTrue(current.label.contains("https://demo-tunnel.trycloudflare.com"), current.label)
        XCTAssertFalse(app.staticTexts[ID.urlError].exists)

        app.buttons[ID.urlReset].tap()
        XCTAssertTrue(current.label.contains("127.0.0.1:5055"), "reset should restore the default: \(current.label)")
    }

    func testInvalidSchemeShowsErrorAndKeepsDefault() {
        let app = launch()
        openSheet(app)
        resetViaSheet(app)
        let field = app.textFields[ID.urlField]
        field.tap()
        field.typeText("ftp://nope.example.com")
        app.buttons[ID.urlSave].tap()
        // At AX5 on a small phone the keyboard and large text push the error off screen (form rows are
        // lazy), so scroll for it before asserting.
        let err = app.staticTexts[ID.urlError]
        if !err.waitForExistence(timeout: 2) { app.swipeUp() }
        XCTAssertTrue(err.waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts[ID.urlCurrent].label.contains("127.0.0.1:5055"))
    }

    func testOverridePersistsAcrossRelaunchUntilReset() {
        var app = launch()
        openSheet(app)
        resetViaSheet(app)
        var field = app.textFields[ID.urlField]
        field.tap()
        field.typeText("http://192.168.1.20:5055")
        app.buttons[ID.urlSave].tap()
        app.terminate()

        app = XCUIApplication.mockSignedIn()
        openSheet(app)
        field = app.textFields[ID.urlField]
        XCTAssertEqual(field.value as? String, "http://192.168.1.20:5055")
        app.buttons[ID.urlReset].tap()
        XCTAssertTrue(app.staticTexts[ID.urlCurrent].label.contains("127.0.0.1:5055"))
    }
}
