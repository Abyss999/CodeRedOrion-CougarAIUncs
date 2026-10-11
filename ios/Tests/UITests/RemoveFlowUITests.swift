import XCTest

/// Launch hooks for the remove flow (requested from the builder; confirm names in LaunchConfiguration).
enum RemoveArgs {
    static let failRemove = "-UITestFailRemove"
    static let failRestore = "-UITestFailRestore"
    static let recordHaptics = "-UITestRecordHaptics"
    static let reduceMotion = "-UITestReduceMotion"
    static let listingSeed = ["-UITestSeed", "listing"]
    static let hapticsProbe = "debug.haptics"
    static let removeError = "fridge.remove.error"
    /// Static claimer line under the outcome tiles (claimed open listing only).
    static let recipient = "remove.recipient"
}

/// Swipe → Remove → outcome (→ reason) → the row collapses → Undo toast; and the failure rollbacks.
final class RemoveFlowUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func haptics(_ app: XCUIApplication) -> [String] {
        let probe = app.any(RemoveArgs.hapticsProbe)
        guard probe.exists else { return [] }
        let v = (probe.value as? String) ?? probe.label
        return v.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty && $0 != "none" }
    }

    private func assertRowGoneAndToast(_ app: XCUIApplication, item: String, name: String,
                                       file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(app.any(FID.sheet).waitForNonExistence(timeout: 3), "sheet stayed open", file: file, line: line)
        XCTAssertTrue(app.fridgeRow(item).waitForNonExistence(timeout: 2), "row did not collapse", file: file, line: line)
        XCTAssertTrue(app.toast.waitForExistence(timeout: 2), "Undo toast missing", file: file, line: line)
        let msg = app.any(ID.toastMessage)
        XCTAssertTrue(msg.label.contains(name), "toast message '\(msg.label)' lacks '\(name)'", file: file, line: line)
    }

    // MARK: Outcomes

    func testUsedRemovesRowAndShowsToast() {
        let app = XCUIApplication.fridge([RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        attachScreenshot(app, name: "remove-sheet")
        XCTAssertFalse(app.any(RemoveArgs.recipient).exists, "no listing: the claimer line must be hidden")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        attachScreenshot(app, name: "after-remove-toast")
        XCTAssertEqual(haptics(app), ["success"], "remove → .success only, got \(haptics(app))")
    }

    func testGaveAwayWithoutListingHidesRecipient() {
        let app = XCUIApplication.fridge()
        openRemove(app, item: "item-eggs")
        XCTAssertFalse(app.any(RemoveArgs.recipient).exists)
        XCTAssertTrue(app.any(FID.outcome("donated")).label.contains("Gave it away"))
        app.any(FID.outcome("donated")).tap()
        assertRowGoneAndToast(app, item: "item-eggs", name: "Eggs")
    }

    /// Claimed open listing (spinach → Marcus): a static, non-interactive line names the claimer.
    /// The app sends no recipient_id (the server credits the claimer); that is covered by the
    /// sheet code (`RemoveChoice(outcome:)`) and `RemoveRequestShapeTests.testDonatedWithoutRecipientOmitsKey`.
    func testGaveAwayWithClaimedListingShowsClaimerLine() {
        let app = XCUIApplication.fridge(RemoveArgs.listingSeed + [RemoveArgs.recordHaptics])
        openRemove(app, item: "item-spinach")
        let line = app.any(RemoveArgs.recipient)
        XCTAssertTrue(line.waitForExistence(timeout: 2), "claimer line missing")
        XCTAssertTrue(line.label.contains("Marcus Ojeda"), line.label)
        XCTAssertNotEqual(line.elementType, .button, "the claimer line is static, not a control")
        XCTAssertFalse(line.isSelected)
        XCTAssertFalse(app.any("remove.recipient.other").exists)
        XCTAssertFalse(app.any("remove.recipient.user-marcus").exists)
        let hint = app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Closes your Share listing'")).firstMatch
        XCTAssertTrue(hint.exists || app.any(FID.outcome("donated")).debugDescription.contains("Closes your Share listing"),
                      "Gave away subtitle should mention the Share listing")
        attachScreenshot(app, name: "remove-sheet-listing")
        app.any(FID.outcome("donated")).tap()
        assertRowGoneAndToast(app, item: "item-spinach", name: "spinach")
        XCTAssertEqual(haptics(app), ["success"], "donated → .success only, got \(haptics(app))")
    }

    /// Open listing without a claimer (carrots): no recipient UI at all.
    func testGaveAwayUnclaimedListingShowsNoRecipient() {
        let app = XCUIApplication.fridge()
        openRemove(app, item: "item-carrots")
        XCTAssertFalse(app.any(RemoveArgs.recipient).exists, "no claimer: no recipient line")
        app.any(FID.outcome("donated")).tap()
        assertRowGoneAndToast(app, item: "item-carrots", name: "Carrots")
    }

    func testThrewAwayPushesReasonThenRemoves() {
        let app = XCUIApplication.fridge([RemoveArgs.recordHaptics])
        openRemove(app, item: "item-strawberries")
        app.any(FID.outcome("thrown_out")).tap()
        let reasons = ["expired", "forgot", "didnt_like", "other"]
        XCTAssertTrue(app.any(FID.reason("expired")).waitForExistence(timeout: 3), "reason step not pushed")
        XCTAssertTrue(app.fridgeRow("item-strawberries").exists, "row must stay until a reason is chosen")
        for r in reasons {
            let t = app.any(FID.reason(r))
            XCTAssertTrue(t.exists, "reason \(r) missing")
            XCTAssertGreaterThanOrEqual(t.frame.height, 44)
            XCTAssertFalse(t.label.isEmpty)
        }
        attachScreenshot(app, name: "remove-reason")
        XCTAssertFalse(haptics(app).contains("success"), "no success haptic before the reason")
        app.any(FID.reason("forgot")).tap()
        assertRowGoneAndToast(app, item: "item-strawberries", name: "Strawberries")
        XCTAssertEqual(haptics(app), ["selection", "warning"], "Threw away → .selection (MOTION), reason → .warning")
    }

    func testCancelKeepsRow() {
        let app = XCUIApplication.fridge()
        openRemove(app, item: "item-eggs")
        let cancel = app.buttons[FID.cancel].exists ? app.buttons[FID.cancel] : app.buttons["Cancel"].firstMatch
        if cancel.exists { cancel.tap() } else { app.swipeDown() }
        XCTAssertTrue(app.any(FID.sheet).waitForNonExistence(timeout: 3))
        XCTAssertTrue(app.reveal(app.fridgeRow("item-eggs"), timeout: 2))
        XCTAssertFalse(app.toast.exists)
    }

    // MARK: Undo

    func testUndoRestoresRowWithoutHaptic() {
        let app = XCUIApplication.fridge([RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        let before = haptics(app)
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.reveal(app.fridgeRow("item-chicken"), timeout: 3), "Undo did not restore the row")
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 2))
        XCTAssertEqual(haptics(app), before, "Undo must not play a haptic")
        // Restored row is back in its section, in expiry order.
        if app.fridgeRow("item-eggs").exists {
            XCTAssertLessThan(app.fridgeRow("item-chicken").frame.minY, app.fridgeRow("item-eggs").frame.minY)
        }
    }

    func testToastExpiryKeepsRemoval() {
        let app = XCUIApplication.fridge()
        openRemove(app, item: "item-eggs")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-eggs", name: "Eggs")
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 8), "toast did not time out")
        // Pull to refresh reloads from the mock: still removed.
        app.any(FID.list).swipeDown(velocity: .slow)
        Thread.sleep(forTimeInterval: 1.0)
        XCTAssertTrue(app.reveal(app.fridgeRow("item-chicken"), timeout: 3))
        XCTAssertFalse(app.fridgeRow("item-eggs").exists, "removal must persist after the toast expires")
    }

    // MARK: Failures roll back

    func testFailedRemoveRollsBackAndShowsError() {
        let app = XCUIApplication.fridge([RemoveArgs.failRemove, RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        XCTAssertTrue(app.any(RemoveArgs.removeError).waitForExistence(timeout: 3) || app.alerts.firstMatch.waitForExistence(timeout: 1),
                      "no error shown after a failed remove")
        attachScreenshot(app, name: "remove-failed")
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 3) || app.reveal(app.fridgeRow("item-chicken")), "row must come back")
        let retry = app.buttons["fridge.remove.error.retry"]
        XCTAssertTrue(retry.exists, "rollback banner offers Try again")
        XCTAssertGreaterThanOrEqual(retry.frame.height, 44)
        let dismiss = app.buttons["fridge.remove.error.dismiss"]
        XCTAssertTrue(dismiss.exists)
        XCTAssertEqual(dismiss.label, "Dismiss")
        XCTAssertGreaterThanOrEqual(dismiss.frame.height, 44); XCTAssertGreaterThanOrEqual(dismiss.frame.width, 44)
        XCTAssertGreaterThanOrEqual(retry.frame.width, 44)
        XCTAssertTrue(app.any(RemoveArgs.removeError).label.contains("Chicken") || app.staticTexts.containing(NSPredicate(format: "label CONTAINS 'Chicken'")).count > 0)
        XCTAssertFalse(app.toast.exists, "no Undo toast for a failed remove")
        // Optimistic: .success plays at the tap, then .error when the server refuses.
        XCTAssertEqual(haptics(app), ["success", "error"], "failed remove haptics")
        dismiss.tap()
        XCTAssertTrue(app.any(RemoveArgs.removeError).waitForNonExistence(timeout: 2), "Dismiss hides the banner")
    }

    func testFailedRestoreKeepsRowRemovedAndShowsError() {
        let app = XCUIApplication.fridge([RemoveArgs.failRestore])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.any(RemoveArgs.removeError).waitForExistence(timeout: 3) || app.alerts.firstMatch.waitForExistence(timeout: 1),
                      "no error shown after a failed restore")
        attachScreenshot(app, name: "restore-failed")
        if app.alerts.firstMatch.exists { app.alerts.firstMatch.buttons.firstMatch.tap() }
        XCTAssertFalse(app.fridgeRow("item-chicken").exists, "a failed restore must leave the item removed")
    }

    // MARK: Motion

    /// Smoke check only. `tap()` itself waits for the app to go idle (checkmark hold 0.2 s + sheet
    /// dismissal + collapse), and `waitForNonExistence` polls coarsely, so this measures XCUITest
    /// more than the app. Immediacy is proved by `FridgeModelTests.testRemoveIsImmediateAndShowsToast`
    /// (the row is gone synchronously, before any await) and by the clip.
    func testRemoveTakesEffectImmediately() {
        for rm in [false, true] {
            let app = XCUIApplication.fridge(rm ? [RemoveArgs.reduceMotion] : [])
            openRemove(app, item: "item-chicken")
            let t0 = Date()
            app.any(FID.outcome("used")).tap()
            XCTAssertTrue(app.fridgeRow("item-chicken").waitForNonExistence(timeout: 2))
            let dt = Date().timeIntervalSince(t0)
            XCTAssertLessThan(dt, 3.0, "reduceMotion=\(rm): row took \(dt) s to go")
            XCTAssertTrue(app.toast.waitForExistence(timeout: 1))
            app.terminate()
        }
    }

    func testReduceMotionToastFadesInPlace() {
        let app = XCUIApplication.fridge([RemoveArgs.reduceMotion])
        openRemove(app, item: "item-eggs")
        app.any(FID.outcome("used")).tap()
        XCTAssertTrue(app.toast.waitForExistence(timeout: 2))
        let a = app.toast.frame
        Thread.sleep(forTimeInterval: 0.6)
        XCTAssertEqual(a.minY, app.toast.frame.minY, accuracy: 0.5, "toast moved under Reduce Motion")
        XCTAssertLessThanOrEqual(app.toast.frame.maxY, app.tabBars.firstMatch.frame.minY + 1, "toast overlaps tab bar")
    }

    func testReduceMotionThrewAwayFlowStillWorksWithHaptics() {
        let app = XCUIApplication.fridge([RemoveArgs.reduceMotion, RemoveArgs.recordHaptics])
        openRemove(app, item: "item-strawberries")
        app.any(FID.outcome("thrown_out")).tap()
        XCTAssertTrue(app.any(FID.reason("expired")).waitForExistence(timeout: 3))
        app.any(FID.reason("expired")).tap()
        assertRowGoneAndToast(app, item: "item-strawberries", name: "Strawberries")
        XCTAssertTrue(haptics(app).contains("warning"), "haptics stay under Reduce Motion: \(haptics(app))")
    }
}
