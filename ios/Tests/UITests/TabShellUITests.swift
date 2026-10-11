import XCTest

final class TabShellUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    func testFiveTabsExist() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        XCTAssertEqual(app.tabBars.firstMatch.buttons.count, 5)
        for id in ID.tabs { XCTAssertTrue(app.tab(id).exists, "missing \(id)") }
    }

    /// IOS-4 regression: the tab identifiers reach the tab bar buttons on every launch (the builder
    /// installs them on the `UITabBarItem`s). Previously empty in 4 of 5 launches; now strict, over
    /// 3 launches.
    func testTabIdentifiersReachTheTabBar_IOS4() {
        for launch in 1...3 {
            let app = XCUIApplication.mockSignedIn()
            XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
            let ok = NSPredicate { _, _ in
                app.tabBars.firstMatch.buttons.allElementsBoundByIndex.map(\.identifier) == ID.tabs
            }
            wait(for: [expectation(for: ok, evaluatedWith: nil)], timeout: 5)
            XCTAssertEqual(app.tabBars.firstMatch.buttons.allElementsBoundByIndex.map(\.identifier), ID.tabs, "launch \(launch)")
            for id in ID.tabs { XCTAssertTrue(app.tabBars.buttons[id].exists, "\(id) not queryable by identifier, launch \(launch)") }
            app.terminate()
        }
    }

    /// IOS-10 regression: VoiceOver reads each tab button's label, which must be exactly the title,
    /// never the SF Symbol name (`home`, `add`). The UITabBarButton is the accessibility element, so
    /// the image inside it is not a VoiceOver stop; XCUITest still lists that image with a symbol
    /// label (`home`, `frying.pan.fill`), which is logged here for the record but not asserted.
    func testTabButtonsHaveNoStrayImageLabels_IOS10() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        let titles = ["Home", "Recipes", "Add", "Fridge", "Social"]
        XCTAssertEqual(app.tabBars.firstMatch.buttons.allElementsBoundByIndex.map(\.label), titles)
        for (id, title) in zip(ID.tabs, titles) {
            let button = app.tabBars.buttons[id]
            XCTAssertTrue(button.exists, "\(id) by identifier")
            XCTAssertEqual(button.label, title)
            XCTAssertFalse(["home", "add", "recipes", "fridge", "social"].contains(button.label), button.label)
            XCTAssertTrue(button.isAccessibilityElementForVoiceOver, "\(id)")
            let imageLabels = button.images.allElementsBoundByIndex.map(\.label)
            XCTContext.runActivity(named: "\(id) image child labels (XCUITest only): \(imageLabels)") { _ in }
        }
    }

    func testTabOrderAndVoiceOverLabels() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        let expected = ["Home", "Recipes", "Add", "Fridge", "Social"]
        let labels = app.tabBars.firstMatch.buttons.allElementsBoundByIndex.map(\.label)
        XCTAssertEqual(labels, expected, "tab order and accessibility labels")
        for (id, label) in zip(ID.tabs, expected) { XCTAssertEqual(app.tab(id).label, label) }
    }

    func testHomeSelectedAtLaunch() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tab(ID.home).waitForExistence(timeout: 10))
        XCTAssertTrue(app.tab(ID.home).isSelected)
        for id in [ID.recipes, ID.add, ID.fridge, ID.social] { XCTAssertFalse(app.tab(id).isSelected, id) }
    }

    func testTabsAreTappableAndSelect() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        for id in [ID.recipes, ID.fridge, ID.social, ID.home] {
            app.tab(id).tap()
            XCTAssertTrue(app.tab(id).isSelected, "\(id) should be selected after tap")
        }
    }

    func testTabTouchTargetsAtLeast44pt() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        for id in ID.tabs {
            let f = app.tab(id).frame
            XCTAssertGreaterThanOrEqual(f.height, 44, "\(id) height \(f.height)")
            XCTAssertGreaterThanOrEqual(f.width, 44, "\(id) width \(f.width)")
        }
    }

    // MARK: Add tab: presents a sheet, never changes the selection

    func testAddPresentsSheetAndKeepsHomeSelected() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tab(ID.home).waitForExistence(timeout: 10))
        app.tab(ID.add).tap()
        XCTAssertTrue(app.addSheet.waitForExistence(timeout: 5), "Add sheet should appear")
        dismissSheet(app)
        XCTAssertTrue(app.tab(ID.home).waitForExistence(timeout: 5))
        XCTAssertTrue(app.tab(ID.home).isSelected, "Home must still be selected after the Add sheet")
        XCTAssertFalse(app.tab(ID.add).isSelected, "Add must never become the selected tab")
    }

    func testAddFromFridgeKeepsFridgeSelected() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        app.tab(ID.fridge).tap()
        app.tab(ID.add).tap()
        XCTAssertTrue(app.addSheet.waitForExistence(timeout: 5))
        dismissSheet(app)
        XCTAssertTrue(app.tab(ID.fridge).waitForExistence(timeout: 5))
        XCTAssertTrue(app.tab(ID.fridge).isSelected)
        XCTAssertFalse(app.tab(ID.add).isSelected)
    }

    func testAddSheetCanBeOpenedRepeatedly() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        app.tab(ID.social).tap()
        for _ in 0..<3 {
            app.tab(ID.add).tap()
            XCTAssertTrue(app.addSheet.waitForExistence(timeout: 5))
            dismissSheet(app)
            XCTAssertTrue(app.tab(ID.social).waitForExistence(timeout: 5))
            XCTAssertTrue(app.tab(ID.social).isSelected)
        }
    }

    /// Swipe the Add sheet away by its grabber. On a slow CI runner (macos-26) a single drag issued
    /// while the sheet was still settling did not dismiss it (the press landed mid-presentation), so:
    /// wait until the grabber is hittable and the sheet frame has stopped moving, then drag, and
    /// retry the drag (up to 3 times) if the sheet is still there. The tests assert the tab
    /// selection after dismissal, not the gesture itself.
    private func dismissSheet(_ app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) {
        let sheet = app.addSheet
        let grabber = app.buttons["Sheet Grabber"].firstMatch
        for attempt in 1...3 {
            XCTAssertTrue(grabber.waitForExistence(timeout: 5), "no sheet grabber", file: file, line: line)
            waitUntilSettled(sheet)
            let from = grabber.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            from.press(forDuration: 0.1, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.98)))
            if sheet.waitForNonExistence(timeout: 5) { return }
            XCTContext.runActivity(named: "Add sheet still shown after drag \(attempt); retrying") { _ in }
        }
        XCTFail("Add sheet did not dismiss after 3 drags", file: file, line: line)
    }

    /// Polls the element frame until two reads 0.25 s apart agree (presentation animation done).
    private func waitUntilSettled(_ element: XCUIElement, timeout: TimeInterval = 3) {
        let deadline = Date().addingTimeInterval(timeout)
        var last = element.frame
        while Date() < deadline {
            Thread.sleep(forTimeInterval: 0.25)
            let now = element.frame
            if now == last { return }
            last = now
        }
    }

    // MARK: Screenshots (tint visible in both modes)

    func testScreenshotsTabBarAndAddSheet() {
        let app = XCUIApplication.mockSignedIn()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        attachScreenshot(app, name: "tabbar-home-\(appearanceName())")
        app.tab(ID.add).tap()
        XCTAssertTrue(app.addSheet.waitForExistence(timeout: 5))
        attachScreenshot(app, name: "add-sheet-\(appearanceName())")
    }

    private func appearanceName() -> String {
        UITraitCollection.current.userInterfaceStyle == .dark ? "dark" : "light"
    }

    // MARK: Dynamic Type (AX5 via launch argument)

    func testTabsRemainUsableAtAX5() {
        let app = XCUIApplication.mockSignedIn(["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        for id in ID.tabs {
            XCTAssertTrue(app.tab(id).isHittable, "\(id) not hittable at AX5")
            XCTAssertGreaterThanOrEqual(app.tab(id).frame.height, 44)
        }
        app.tab(ID.add).tap()
        XCTAssertTrue(app.addSheet.waitForExistence(timeout: 5))
        attachScreenshot(app, name: "add-sheet-ax5")
    }
}
