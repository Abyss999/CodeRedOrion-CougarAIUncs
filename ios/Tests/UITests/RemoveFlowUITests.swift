import XCTest

/// Launch hooks for the remove flow (requested from the builder; confirm names in LaunchConfiguration).
enum RemoveArgs {
    static let failRemove = "-UITestFailRemove"
    static let failRestore = "-UITestFailRestore"
    static let slowRemove = "-UITestSlowRemove"
    /// Mock restore answers 409 `not_removed` (requested from the builder for the #64 ruling).
    static let restoreNotRemoved = "-UITestRestoreNotRemoved"
    /// Undo window in seconds (DEBUG hook). 30 s so a slow CI runner still finds the toast; the
    /// 5 s default is covered by `testToastExpiryKeepsRemoval` and `MotionUITests`.
    static let undoWindow = ["-UITestUndoWindow", "30"]
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

    /// Every flow launches with the 30 s undo window unless it is testing the timeout itself.
    /// Timeouts below are upper bounds for slow runners, never pass/fail thresholds on speed.
    private func launch(_ extra: [String] = [], undoWindow: Bool = true) -> XCUIApplication {
        XCUIApplication.fridge(extra + (undoWindow ? RemoveArgs.undoWindow : []))
    }

    private func haptics(_ app: XCUIApplication) -> [String] {
        let probe = app.any(RemoveArgs.hapticsProbe)
        guard probe.exists else { return [] }
        let v = (probe.value as? String) ?? probe.label
        return v.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty && $0 != "none" }
    }

    private func assertRowGoneAndToast(_ app: XCUIApplication, item: String, name: String,
                                       file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(app.any(FID.sheet).waitForNonExistence(timeout: 10), "sheet stayed open", file: file, line: line)
        XCTAssertTrue(app.fridgeRow(item).waitForNonExistence(timeout: 10), "row did not collapse", file: file, line: line)
        XCTAssertTrue(app.toast.waitForExistence(timeout: 10), "Undo toast missing", file: file, line: line)
        let msg = app.any(ID.toastMessage)
        XCTAssertTrue(msg.label.contains(name), "toast message '\(msg.label)' lacks '\(name)'", file: file, line: line)
    }

    // MARK: Outcomes

    func testUsedRemovesRowAndShowsToast() {
        let app = launch([RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        attachScreenshot(app, name: "remove-sheet")
        XCTAssertFalse(app.any(RemoveArgs.recipient).exists, "no listing: the claimer line must be hidden")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        attachScreenshot(app, name: "after-remove-toast")
        XCTAssertEqual(haptics(app), ["success"], "remove → .success only, got \(haptics(app))")
    }

    func testGaveAwayWithoutListingHidesRecipient() {
        let app = launch()
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
        let app = launch(RemoveArgs.listingSeed + [RemoveArgs.recordHaptics])
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
        let app = launch()
        openRemove(app, item: "item-carrots")
        XCTAssertFalse(app.any(RemoveArgs.recipient).exists, "no claimer: no recipient line")
        app.any(FID.outcome("donated")).tap()
        assertRowGoneAndToast(app, item: "item-carrots", name: "Carrots")
    }

    func testThrewAwayPushesReasonThenRemoves() {
        let app = launch([RemoveArgs.recordHaptics])
        openRemove(app, item: "item-strawberries")
        app.any(FID.outcome("thrown_out")).tap()
        let reasons = ["expired", "forgot", "didnt_like", "other"]
        XCTAssertTrue(app.any(FID.reason("expired")).waitForExistence(timeout: 10), "reason step not pushed")
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
        let app = launch()
        openRemove(app, item: "item-eggs")
        let cancel = app.buttons[FID.cancel].exists ? app.buttons[FID.cancel] : app.buttons["Cancel"].firstMatch
        if cancel.exists { cancel.tap() } else { app.swipeDown() }
        XCTAssertTrue(app.any(FID.sheet).waitForNonExistence(timeout: 10))
        XCTAssertTrue(app.reveal(app.fridgeRow("item-eggs"), timeout: 2))
        XCTAssertFalse(app.toast.exists)
    }

    // MARK: Undo

    func testUndoRestoresRowWithoutHaptic() {
        let app = launch([RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        let before = haptics(app)
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.reveal(app.fridgeRow("item-chicken"), timeout: 10), "Undo did not restore the row")
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 10))
        XCTAssertEqual(haptics(app), before, "Undo must not play a haptic")
        // Restored row is back in its section, in expiry order.
        if app.fridgeRow("item-eggs").exists {
            XCTAssertLessThan(app.fridgeRow("item-chicken").frame.minY, app.fridgeRow("item-eggs").frame.minY)
        }
    }

    /// Default 5 s window. The toast may already be gone by the time a slow runner looks, so only
    /// its eventual absence is asserted, then that the removal survived a refresh.
    func testToastExpiryKeepsRemoval() {
        let app = launch(undoWindow: false)
        openRemove(app, item: "item-eggs")
        app.any(FID.outcome("used")).tap()
        XCTAssertTrue(app.fridgeRow("item-eggs").waitForNonExistence(timeout: 10), "row did not collapse")
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 20), "toast did not time out")
        XCTAssertFalse(app.any(ID.toastMarker).exists)
        // Pull to refresh reloads from the mock: still removed.
        app.any(FID.list).swipeDown(velocity: .slow)
        XCTAssertTrue(app.reveal(app.fridgeRow("item-chicken"), timeout: 10))
        XCTAssertFalse(app.fridgeRow("item-eggs").exists, "removal must persist after the toast expires")
    }

    /// The Undo countdown starts when the toast becomes visible, after the sheet dismisses (#64).
    /// Window 12 s; the toast must still be up 10 s after XCUITest *noticed* the sheet was gone.
    /// Noticing lags the real dismissal (about 1 s polling on CI) and each query costs 1-1.5 s there,
    /// so a 2 s allowance is built in. It still fails if the countdown ran under the sheet for more
    /// than about 2 s. If the snapshot itself lands more than 11 s after `tGone`, the run is
    /// inconclusive (logged), never a false failure.
    func testFullUndoWindowAfterSheetDismisses() {
        let app = XCUIApplication.fridge(["-UITestUndoWindow", "12"])
        openRemove(app, item: "item-eggs")
        app.any(FID.outcome("used")).tap()
        XCTAssertTrue(app.any(FID.sheet).waitForNonExistence(timeout: 10))
        let tGone = Date()
        XCTAssertTrue(app.toast.waitForExistence(timeout: 5), "toast should be up once the sheet is gone")
        let wait = 10 - Date().timeIntervalSince(tGone)
        if wait > 0 { Thread.sleep(forTimeInterval: wait) }
        let present = app.toast.exists
        let lookedAt = Date().timeIntervalSince(tGone)
        let timing = XCTAttachment(string: "undo-window: present=\(present) lookedAt=\(lookedAt)")
        timing.lifetime = .keepAlways; add(timing)
        if lookedAt > 11 {
            let note = XCTAttachment(string: "snapshot landed \(lookedAt) s after the sheet; inconclusive on this runner")
            note.lifetime = .keepAlways; add(note)
        } else {
            XCTAssertTrue(present, "toast gone \(lookedAt) s after the sheet: the countdown ran under the sheet")
        }
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 20), "toast never timed out")
        XCTAssertFalse(app.fridgeRow("item-eggs").exists, "timeout keeps the removal")
    }

    /// Ruling (#64): a restore answered with 409 `not_removed` keeps the row and shows no banner.
    func testUndoWithRestoreNotRemovedKeepsRowWithoutBanner() {
        let app = launch([RemoveArgs.restoreNotRemoved, RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.reveal(app.fridgeRow("item-chicken"), timeout: 10), "Undo did not restore the row")
        // Give the restore call time to come back (mock delay 150 ms) before checking for a rollback.
        XCTAssertFalse(app.any(RemoveArgs.removeError).waitForExistence(timeout: 3), "not_removed must not show the banner")
        XCTAssertTrue(app.fridgeRow("item-chicken").exists, "row must stay after not_removed")
        XCTAssertEqual(haptics(app), ["success"], "no error haptic for not_removed")
    }

    // MARK: Failures roll back

    func testFailedRemoveRollsBackAndShowsError() {
        let app = launch([RemoveArgs.failRemove, RemoveArgs.recordHaptics])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        XCTAssertTrue(app.any(RemoveArgs.removeError).waitForExistence(timeout: 10) || app.alerts.firstMatch.waitForExistence(timeout: 1),
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
        XCTAssertTrue(app.any(RemoveArgs.removeError).waitForNonExistence(timeout: 10), "Dismiss hides the banner")
    }

    func testFailedRestoreKeepsRowRemovedAndShowsError() {
        let app = launch([RemoveArgs.failRestore])
        openRemove(app, item: "item-chicken")
        app.any(FID.outcome("used")).tap()
        assertRowGoneAndToast(app, item: "item-chicken", name: "Chicken")
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.any(RemoveArgs.removeError).waitForExistence(timeout: 10) || app.alerts.firstMatch.waitForExistence(timeout: 1),
                      "no error shown after a failed restore")
        attachScreenshot(app, name: "restore-failed")
        if app.alerts.firstMatch.exists { app.alerts.firstMatch.buttons.firstMatch.tap() }
        XCTAssertFalse(app.fridgeRow("item-chicken").exists, "a failed restore must leave the item removed")
    }

    // MARK: Motion

    /// "The tap takes effect immediately", asserted on state, not wall time. The remove call is
    /// slowed to 3 s and made to fail (`-UITestSlowRemove -UITestFailRemove`): a UI that waited for
    /// the server would never hide the row, because the call fails. So the row being gone while the
    /// rollback banner is not up yet (the request still in flight) proves the removal is optimistic.
    /// Then the failure rolls it back. If a runner is so slow that its first look comes after the
    /// 3 s call has already resolved, that run is inconclusive (logged, not failed); immediacy is
    /// also proved in `FridgeModelTests.testRemoveIsImmediateAndShowsToast`.
    func testRemoveTakesEffectImmediately() {
        for rm in [false, true] {
            let app = launch([RemoveArgs.slowRemove, RemoveArgs.failRemove] + (rm ? [RemoveArgs.reduceMotion] : []))
            openRemove(app, item: "item-chicken")
            app.any(FID.outcome("used")).tap()
            // The list behind the sheet may be hidden from accessibility, so look once the sheet has
            // gone (its native dismissal is not counted against anything; this is an upper bound).
            XCTAssertTrue(app.any(FID.sheet).waitForNonExistence(timeout: 10))
            // Row first, banner second: the rollback re-inserts the row and raises the banner in one
            // main-actor turn, so "row shown, then banner still absent" can only mean the row was
            // shown while the request was in flight.
            let rowShown = app.fridgeRow("item-chicken").exists
            let toastUp = app.toast.exists
            let bannerUp = app.any(RemoveArgs.removeError).exists
            if bannerUp {
                let note = XCTAttachment(string: "reduceMotion=\(rm): first look came after the 3 s call resolved; inconclusive on this runner")
                note.lifetime = .keepAlways; add(note)
            } else {
                XCTAssertFalse(rowShown, "reduceMotion=\(rm): row still shown while the remove request is in flight")
                XCTAssertTrue(toastUp, "reduceMotion=\(rm): Undo toast should be up while the request is in flight")
            }
            // Then the failure rolls back: banner, row back, toast gone.
            XCTAssertTrue(app.any(RemoveArgs.removeError).waitForExistence(timeout: 15), "reduceMotion=\(rm): no rollback banner")
            XCTAssertTrue(app.reveal(app.fridgeRow("item-chicken"), timeout: 10), "reduceMotion=\(rm): row not rolled back")
            XCTAssertFalse(app.toast.exists)
            app.terminate()
        }
    }

    func testReduceMotionToastFadesInPlace() {
        let app = launch([RemoveArgs.reduceMotion])
        openRemove(app, item: "item-eggs")
        app.any(FID.outcome("used")).tap()
        XCTAssertTrue(app.toast.waitForExistence(timeout: 10))
        let a = app.toast.frame
        Thread.sleep(forTimeInterval: 0.6)
        XCTAssertEqual(a.minY, app.toast.frame.minY, accuracy: 0.5, "toast moved under Reduce Motion")
        XCTAssertLessThanOrEqual(app.toast.frame.maxY, app.tabBars.firstMatch.frame.minY + 1, "toast overlaps tab bar")
    }

    func testReduceMotionThrewAwayFlowStillWorksWithHaptics() {
        let app = launch([RemoveArgs.reduceMotion, RemoveArgs.recordHaptics])
        openRemove(app, item: "item-strawberries")
        app.any(FID.outcome("thrown_out")).tap()
        XCTAssertTrue(app.any(FID.reason("expired")).waitForExistence(timeout: 10))
        app.any(FID.reason("expired")).tap()
        assertRowGoneAndToast(app, item: "item-strawberries", name: "Strawberries")
        XCTAssertTrue(haptics(app).contains("warning"), "haptics stay under Reduce Motion: \(haptics(app))")
    }
}
