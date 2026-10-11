import XCTest

/// Undo toast and Reduce Motion, driven by the DEBUG launch hooks `-UITestShowToast` (shows one
/// "Baby spinach removed" toast in the Home tab) and `-UITestReduceMotion` (forces Reduce Motion).
final class MotionUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func launch(reduceMotion: Bool) -> XCUIApplication {
        XCUIApplication.mockSignedIn(["-UITestShowToast"] + (reduceMotion ? ["-UITestReduceMotion"] : []))
    }

    private func assertToastLayout(_ app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) {
        let toast = app.toast
        XCTAssertTrue(toast.waitForExistence(timeout: 5), "toast.undo missing", file: file, line: line)
        let message = app.descendants(matching: .any)[ID.toastMessage].firstMatch
        XCTAssertTrue(message.exists, file: file, line: line)
        XCTAssertEqual(message.label, "Baby spinach removed", file: file, line: line)
        let button = app.buttons[ID.toastButton]
        XCTAssertTrue(button.exists, file: file, line: line)
        XCTAssertEqual(button.label, "Undo", file: file, line: line)
        XCTAssertTrue(button.isHittable, file: file, line: line)
        XCTAssertGreaterThanOrEqual(button.frame.height, 44, "Undo target height \(button.frame.height)", file: file, line: line)
        XCTAssertGreaterThanOrEqual(button.frame.width, 44, "Undo target width \(button.frame.width)", file: file, line: line)
        // The toast lives in the tab content, above the glass tab bar, never covering it.
        let bar = app.tabBars.firstMatch.frame
        XCTAssertLessThanOrEqual(toast.frame.maxY, bar.minY + 1, "toast \(toast.frame) overlaps tab bar \(bar)", file: file, line: line)
    }

    func testToastShowsMessageUndoAnd44ptTarget() {
        let app = launch(reduceMotion: false)
        assertToastLayout(app)
        attachScreenshot(app, name: "toast")
    }

    func testUndoCallsBackAndDismisses() {
        let app = launch(reduceMotion: false)
        XCTAssertTrue(app.toast.waitForExistence(timeout: 5))
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.descendants(matching: .any)[ID.toastMarker].waitForExistence(timeout: 3), "onUndo not called")
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 3), "toast should dismiss after Undo")
    }

    /// The toast starts counting when it appears during launch, before `launch()` returns, so time is
    /// measured from just before launch: it cannot be gone before 5 s from there, and it must be gone
    /// within a few seconds of first being seen (measured locally: launch 2.9 s, seen 4.0 s, gone 7.2 s).
    func testToastAutoDismissesAfterAboutFiveSecondsWithoutUndo() {
        assertAutoDismiss(reduceMotion: false)
    }

    private func assertAutoDismiss(reduceMotion: Bool, file: StaticString = #filePath, line: UInt = #line) {
        let t0 = Date()
        let app = launch(reduceMotion: reduceMotion)
        XCTAssertTrue(app.toast.waitForExistence(timeout: 5), file: file, line: line)
        let seen = Date()
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 8), "toast did not auto-dismiss", file: file, line: line)
        let gone = Date()
        XCTAssertGreaterThanOrEqual(gone.timeIntervalSince(t0), 5.0, "dismissed before 5 s", file: file, line: line)
        XCTAssertLessThan(gone.timeIntervalSince(seen), 7.0, "lingered: \(gone.timeIntervalSince(seen)) s after seen", file: file, line: line)
        XCTAssertFalse(app.descendants(matching: .any)[ID.toastMarker].exists, "timeout must not call Undo", file: file, line: line)
    }

    /// IOS-11 regression: at AX5 the toast kept message and Undo side by side, so on narrow phones the
    /// message broke mid-word ("spinac / h", "re- / move / d" on the iPhone SE). Expect a stacked
    /// layout (Undo below the message) or a message at least 60% of the toast's width.
    func testToastMessageIsNotSqueezedAtAX5_IOS11() {
        let app = XCUIApplication.mockSignedIn(["-UITestShowToast", "-UIPreferredContentSizeCategoryName",
                                                "UICTContentSizeCategoryAccessibilityXXXL"])
        XCTAssertTrue(app.toast.waitForExistence(timeout: 5))
        let toast = app.toast.frame
        let message = app.descendants(matching: .any)[ID.toastMessage].firstMatch.frame
        let undo = app.buttons[ID.toastButton].frame
        attachScreenshot(app, name: "toast-ax5")
        XCTAssertGreaterThanOrEqual(undo.minY, message.maxY - 1, "Undo must sit below the message at AX5: message \(message) undo \(undo)")
        XCTAssertGreaterThanOrEqual(message.width, toast.width * 0.8, "message is full width: \(message) in \(toast)")
        XCTAssertGreaterThanOrEqual(undo.height, 44)
        XCTAssertGreaterThanOrEqual(undo.width, 44)
        XCTAssertEqual(app.descendants(matching: .any)[ID.toastMessage].firstMatch.label, "Baby spinach removed")
        XCTAssertLessThanOrEqual(toast.maxY, app.tabBars.firstMatch.frame.minY + 1, "toast overlaps the tab bar")
    }

    // MARK: Reduce Motion (forced through -UITestReduceMotion)

    func testReduceMotionToastStillAppearsAndUndoWorks() {
        let app = launch(reduceMotion: true)
        assertToastLayout(app)
        attachScreenshot(app, name: "toast-reduce-motion")
        app.buttons[ID.toastButton].tap()
        XCTAssertTrue(app.descendants(matching: .any)[ID.toastMarker].waitForExistence(timeout: 3))
        XCTAssertTrue(app.toast.waitForNonExistence(timeout: 3))
    }

    /// Reduce Motion turns the slide into a fade: the toast never moves, so its frame is the same at
    /// the first sighting and after the animation would have settled. Without Reduce Motion the
    /// final frame is the same too (same layout), only the path differs.
    func testReduceMotionToastDoesNotMove() {
        let app = launch(reduceMotion: true)
        XCTAssertTrue(app.toast.waitForExistence(timeout: 5))
        let first = app.toast.frame
        Thread.sleep(forTimeInterval: 0.6)
        let settled = app.toast.frame
        XCTAssertEqual(first.minY, settled.minY, accuracy: 0.5, "moved from \(first) to \(settled)")
        XCTAssertTrue(app.toast.exists, "a fade must not leave it invisible")
    }

    func testReduceMotionTimeoutStillAboutFiveSeconds() {
        assertAutoDismiss(reduceMotion: true)
    }
}
