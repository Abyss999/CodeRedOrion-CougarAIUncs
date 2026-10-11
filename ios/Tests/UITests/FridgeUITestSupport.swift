import XCTest

/// Fridge / Remove identifiers. They mirror `AccessibilityID.Fridge`, `.Remove` and `.State` in the app.
enum FID {
    static let list = "fridge.list"
    static func storage(_ s: String) -> String { "fridge.storage.\(s)" }
    static func group(_ g: String) -> String { "fridge.group.\(g)" }
    static func row(_ id: String) -> String { "fridge.row.\(id)" }
    static func rowRemove(_ id: String) -> String { "fridge.row.\(id).remove" }
    static func badge(_ id: String) -> String { "fridge.row.\(id).badge" }
    static let empty = "fridge.empty", error = "fridge.error", retry = "fridge.error.retry", loading = "fridge.loading"
    static let sheet = "remove.sheet"
    static let staggerProbe = "debug.stagger.count"
    static let reasonScreen = "removereason.screen", reasonTip = "removereason.tip"
    static let cancel = "remove.cancel"
    static func check(_ raw: String) -> String { "remove.outcome.\(raw).check" }
    static func outcome(_ raw: String) -> String { "remove.outcome.\(raw)" }
    static func reason(_ raw: String) -> String { "remove.reason.\(raw)" }
}

extension XCUIApplication {
    func any(_ id: String) -> XCUIElement { descendants(matching: .any)[id].firstMatch }

    /// Launch signed in on the mock, then select the Fridge tab.
    static func fridge(_ extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication.mockSignedIn(extra)
        app.tab(ID.fridge).tap()
        return app
    }

    func fridgeRow(_ itemID: String) -> XCUIElement { any(FID.row(itemID)) }

    /// Scroll the (lazy) Fridge list until `element` is hittable: needed at AX5 on the SE, where a
    /// row is taller than half the screen. Tries the current position, then from the top down.
    @discardableResult
    func reveal(_ element: XCUIElement, timeout: TimeInterval = 5) -> Bool {
        // "Clear" = hittable and its centre above the floating glass tab bar: a swipe that starts
        // under the bar drags the bar instead (seen on the SE at AX5: it switched to Home).
        func clear() -> Bool {
            guard element.exists, element.isHittable else { return false }
            let bar = tabBars.firstMatch
            return !bar.exists || element.frame.midY < bar.frame.minY - 8
        }
        _ = element.waitForExistence(timeout: timeout)
        if clear() { return true }
        let list = any(FID.list)
        guard list.exists else { return element.exists }
        // Small drags from the middle of the screen, so a row is not scrolled past.
        let from = list.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55))
        if !element.exists { for _ in 0..<3 where !element.exists { list.swipeDown(velocity: .fast) } }
        let up = list.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.35))
        for _ in 0..<16 where !clear() {
            if element.exists && element.frame.midY < frame.midY * 0.5 {
                up.press(forDuration: 0.05, thenDragTo: from)     // it is above: scroll back a little
            } else {
                from.press(forDuration: 0.05, thenDragTo: up)
            }
        }
        return element.exists
    }
}

extension XCTestCase {
    /// Swipe the row left and tap its Remove action (falls back to the action by label).
    func openRemove(_ app: XCUIApplication, item: String, file: StaticString = #filePath, line: UInt = #line) {
        let row = app.fridgeRow(item)
        XCTAssertTrue(app.reveal(row), "row \(item) missing", file: file, line: line)
        row.swipeLeft()
        // A long swipe is a full swipe (`allowsFullSwipe: true`), which opens the sheet directly.
        if !app.any(FID.sheet).waitForExistence(timeout: 1) {
            let byID = app.buttons[FID.rowRemove(item)]
            var action = byID.waitForExistence(timeout: 2) ? byID : app.buttons["Remove"].firstMatch
            if !action.exists && row.exists {   // a swipe on a tall AX5 row can be read as a scroll
                app.reveal(row)
                row.swipeLeft()
                action = byID.waitForExistence(timeout: 2) ? byID : app.buttons["Remove"].firstMatch
            }
            if !app.any(FID.sheet).exists {
                XCTAssertTrue(action.exists, "Remove swipe action missing", file: file, line: line)
                action.tap()
            }
        }
        XCTAssertTrue(app.any(FID.sheet).waitForExistence(timeout: 3), "remove.sheet did not open", file: file, line: line)
    }
}
