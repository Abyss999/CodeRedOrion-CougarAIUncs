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
        XCTAssertFalse(app.urlError.exists)

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
        // IOS-5 regression: the error is a `Label` row directly under the field in the "API base URL"
        // section, and the sheet scrolls it to the centre on every failed Save, so it is on screen
        // without the test scrolling, including at AX5 on the iPhone SE with the keyboard up.
        let err = app.urlError
        XCTAssertTrue(err.waitForExistence(timeout: 3), "debug.baseurl.error missing")
        XCTAssertTrue(err.isHittable, "error must be visible without scrolling")
        XCTAssertTrue(err.label.contains("valid http"), "error text: \(err.label)")
        XCTAssertGreaterThan(err.frame.minY, app.textFields[ID.urlField].frame.minY, "error sits under the field")
        let keyboard = app.keyboards.firstMatch
        if keyboard.exists { XCTAssertLessThanOrEqual(err.frame.maxY, keyboard.frame.minY + 1, "error hidden by the keyboard") }
        XCTAssertGreaterThanOrEqual(err.frame.minY, app.windows.firstMatch.frame.minY, "error above the top edge")
        attachScreenshot(app, name: "baseurl-error")
        XCTAssertTrue(app.staticTexts[ID.urlCurrent].label.contains("127.0.0.1:5055"))

        // A valid save clears the error.
        let field2 = app.textFields[ID.urlField]
        field2.tap()
        let typed = (field2.value as? String)?.count ?? 0
        field2.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: typed))
        field2.typeText("https://ok.example.com")
        app.buttons[ID.urlSave].tap()
        XCTAssertTrue(app.staticTexts[ID.urlCurrent].label.contains("https://ok.example.com"),
                      app.staticTexts[ID.urlCurrent].label)
        XCTAssertFalse(app.urlError.exists, "error clears after a valid save")
        resetViaSheet(app)
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
