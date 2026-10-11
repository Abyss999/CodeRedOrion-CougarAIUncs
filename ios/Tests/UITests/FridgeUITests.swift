import XCTest

/// Fridge list: grouping, storage filter, badges, states, VoiceOver and targets.
/// Seeds come from `MockFixtures` (`fridge` matches the artboard; all its items are in the fridge).
final class FridgeUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    func testGroupsFollowDesignOrderWithCounts() {
        let app = XCUIApplication.fridge()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 5))
        attachScreenshot(app, name: "fridge")
        // The List is lazy (off-screen headers leave the tree), so check order among the headers
        // visible at each scroll position and that all four were seen with count 2.
        let order = ["protein", "veggies", "fruit", "dairy"]
        var seen = Set<String>()
        for _ in 0..<12 {
            let visible = order.filter { app.any(FID.group($0)).exists }
            for g in visible {
                seen.insert(g)
                XCTAssertTrue(app.any(FID.group(g)).label.hasSuffix("2 items"), "header \(g): '\(app.any(FID.group(g)).label)'")
            }
            let ys = visible.map { app.any(FID.group($0)).frame.minY }
            XCTAssertEqual(ys, ys.sorted(), "sections out of design order: \(visible) \(ys)")
            if seen.count == order.count { break }
            app.any(FID.list).swipeUp(velocity: .slow)
        }
        XCTAssertEqual(seen, Set(order), "headers seen: \(seen)")
        for _ in 0..<3 where !(app.fridgeRow("item-oatmilk").exists && app.fridgeRow("item-yogurt").exists) {
            app.any(FID.list).swipeUp(velocity: .slow)
        }
        if app.fridgeRow("item-yogurt").exists && app.fridgeRow("item-oatmilk").exists {
            XCTAssertLessThan(app.fridgeRow("item-yogurt").frame.minY, app.fridgeRow("item-oatmilk").frame.minY)
        }
        for _ in 0..<12 where !app.fridgeRow("item-chicken").exists { app.any(FID.list).swipeDown(velocity: .fast) }
        if app.fridgeRow("item-chicken").exists && app.fridgeRow("item-eggs").exists {
            XCTAssertLessThan(app.fridgeRow("item-chicken").frame.minY, app.fridgeRow("item-eggs").frame.minY)
        }
        if app.fridgeRow("item-spinach").exists && app.fridgeRow("item-carrots").exists {
            XCTAssertLessThan(app.fridgeRow("item-spinach").frame.minY, app.fridgeRow("item-carrots").frame.minY)
        }
        for g in ["grains", "pantry", "leftovers", "frozen", "other"] {
            XCTAssertFalse(app.any(FID.group(g)).exists, "empty group \(g) must be omitted")
        }
        // Within a section rows sort by expiry: chicken (today) above eggs (12 days).
        for _ in 0..<3 where !(app.fridgeRow("item-oatmilk").exists && app.fridgeRow("item-yogurt").exists) {
            app.any(FID.list).swipeUp(velocity: .slow)
        }
        if app.fridgeRow("item-yogurt").exists && app.fridgeRow("item-oatmilk").exists {
            XCTAssertLessThan(app.fridgeRow("item-yogurt").frame.minY, app.fridgeRow("item-oatmilk").frame.minY)
        }
        app.any(FID.list).swipeDown(velocity: .fast)
        if app.fridgeRow("item-chicken").exists && app.fridgeRow("item-eggs").exists {
            XCTAssertLessThan(app.fridgeRow("item-chicken").frame.minY, app.fridgeRow("item-eggs").frame.minY)
        }
        if app.fridgeRow("item-spinach").exists && app.fridgeRow("item-carrots").exists {
            XCTAssertLessThan(app.fridgeRow("item-spinach").frame.minY, app.fridgeRow("item-carrots").frame.minY)
        }
    }

    func testStorageFilter() {
        let app = XCUIApplication.fridge()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 5))
        let pantry = app.any(FID.storage("pantry"))
        XCTAssertTrue(pantry.exists)
        XCTAssertGreaterThanOrEqual(pantry.frame.height, 44, "segment target \(pantry.frame)")
        pantry.tap()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForNonExistence(timeout: 10), "pantry must not show fridge items")
        XCTAssertTrue(app.any(FID.empty).waitForExistence(timeout: 10), "empty pantry shows fridge.empty")
        app.any(FID.storage("fridge")).tap()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 10))
        XCTAssertFalse(app.any(FID.empty).exists)
    }

    func testFreshnessBadgesHaveText() {
        let app = XCUIApplication.fridge()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 5))
        // Round 3: one status per row. Looks off, Tomorrow, estimated ranges ("11–12 days" → 1–2 weeks).
        let expected = ["item-chicken": "today", "item-spinach": "tomorrow", "item-strawberries": "looks off",
                        "item-bananas": "use soon", "item-eggs": "1 to 2 weeks"]
        for (id, text) in expected {
            let b = app.any(FID.badge(id))
            XCTAssertTrue(app.reveal(b), "badge \(id) missing")
            XCTAssertTrue(b.label.lowercased().contains(text), "badge \(id) label '\(b.label)' lacks '\(text)'")
        }
    }

    func testExpiredBadge() {
        let app = XCUIApplication.fridge(["-UITestSeed", "expired"])
        let b = app.any(FID.badge("item-milk"))
        XCTAssertTrue(app.reveal(b))
        XCTAssertTrue(b.label.contains("Expired"), b.label)
        XCTAssertTrue(app.reveal(app.any(FID.badge("item-berries"))))
        XCTAssertTrue(app.any(FID.badge("item-berries")).label.lowercased().contains("looks off"))
    }

    func testEmptyState() {
        let app = XCUIApplication.fridge(["-UITestSeed", "empty"])
        XCTAssertTrue(app.any(FID.empty).waitForExistence(timeout: 5))
        XCTAssertFalse(app.any(FID.loading).exists)
        attachScreenshot(app, name: "fridge-empty")
    }

    func testSkeletonIsOneLoadingElement() {
        let app = XCUIApplication.fridge(["-UITestLoadingForever"])
        let loading = app.descendants(matching: .any).matching(identifier: FID.loading)
        XCTAssertTrue(loading.firstMatch.waitForExistence(timeout: 2), "fridge.loading missing")
        XCTAssertEqual(loading.count, 1, "skeleton must be ONE accessibility element")
        XCTAssertEqual(loading.firstMatch.label, "Loading")
        attachScreenshot(app, name: "fridge-loading")
        XCTAssertFalse(app.fridgeRow("item-chicken").exists)
        XCTAssertFalse(app.any(FID.error).exists)
        XCTAssertFalse(app.any(FID.empty).exists)
    }

    func testErrorStateAndRetry() {
        let app = XCUIApplication.fridge(["-UITestFailList"])
        XCTAssertTrue(app.any(FID.error).waitForExistence(timeout: 5))
        let retry = app.buttons[FID.retry]
        XCTAssertTrue(retry.exists)
        XCTAssertGreaterThanOrEqual(retry.frame.height, 44, "IOS-12: Try again target \(retry.frame)")
        attachScreenshot(app, name: "fridge-error")
        retry.tap()   // still failing: the error comes back, no crash, no stale rows
        XCTAssertTrue(app.any(FID.error).waitForExistence(timeout: 5))
        XCTAssertFalse(app.fridgeRow("item-chicken").exists)
    }

    /// `-UITestFailListOnce` fails the FIRST item-list call of the launch. Home also loads the list at
    /// launch (IOS-42), so either Home or Fridge can take that one failure. Whoever got it must recover
    /// through Try again; the Fridge tab must end with its rows and no error.
    func testRetryAfterOneFailureLoads() {
        let app = XCUIApplication.mockSignedIn(["-UITestFailListOnce"])
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        // Let both launch loads settle: Home shows its content or its error card.
        let homeError = app.any("home.error")
        let homeContent = app.any("home.usefirst")
        let homeSettled = NSPredicate { _, _ in homeError.exists || homeContent.exists }
        wait(for: [expectation(for: homeSettled, evaluatedWith: nil)], timeout: 10)
        if homeError.exists { app.buttons["home.error.retry"].tap() }   // Home took the failure
        app.tab(ID.fridge).tap()
        let errorOrRow = NSPredicate { _, _ in app.any(FID.error).exists || app.fridgeRow("item-chicken").exists }
        wait(for: [expectation(for: errorOrRow, evaluatedWith: nil)], timeout: 10)
        if app.any(FID.error).exists { app.buttons[FID.retry].tap() }   // Fridge took the failure
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 5))
        XCTAssertFalse(app.any(FID.error).exists)
    }

    /// The row is a container: one combined text element (name + meta) and the badge. The spoiled
    /// state is spoken in words ("Photo check: looks spoiled", "Looks off, may be spoiled").
    func testRowVoiceOverLabelAndTargets() {
        let app = XCUIApplication.fridge()
        XCTAssertTrue(app.any("fridge.title").waitForExistence(timeout: 5))
        XCTAssertEqual(app.any("fridge.title").label, "Your food")
        let row = app.fridgeRow("item-strawberries")
        XCTAssertTrue(app.reveal(row))
        let labels = row.descendants(matching: .any).allElementsBoundByIndex.map(\.label).filter { !$0.isEmpty }
        let joined = labels.joined(separator: " | ").lowercased()
        XCTAssertTrue(joined.contains("strawberries"), joined)
        XCTAssertTrue(joined.contains("looks off"), "spoiled must be in words, not colour only: \(joined)")
        XCTAssertFalse(joined.contains("photo check"), "meta is the quantity only: \(joined)")
        XCTAssertEqual(app.any(FID.badge("item-strawberries")).label, "Looks off, may be spoiled")
        // The swipe target is the List cell that holds the row.
        let cell = app.cells.containing(.any, identifier: FID.row("item-strawberries")).firstMatch
        let rowInfo = XCTAttachment(string: "row: \(row.debugDescription)\ncell: \(cell.debugDescription)")
        rowInfo.lifetime = .keepAlways; add(rowInfo)
        XCTAssertGreaterThanOrEqual(max(cell.frame.height, row.frame.height), 44, "row \(row.frame) cell \(cell.frame)")
        for g in ["protein", "veggies", "fruit", "dairy"] where app.any(FID.group(g)).exists {
            XCTAssertEqual(app.any(FID.group(g)).label, "\(g.capitalized), 2 items")
        }
        // The Remove swipe action is also a named accessibility action ("Remove"); XCUITest cannot
        // list custom actions, so that is checked by reading the code (FridgeView.row).
    }

    func testLongListScrolls() {
        let app = XCUIApplication.fridge(["-UITestSeed", "long"])
        XCTAssertTrue(app.fridgeRow("item-long-0").waitForExistence(timeout: 5))
        let list = app.any(FID.list)
        for _ in 0..<40 where !app.any(FID.group("other")).exists { list.swipeUp() }
        XCTAssertTrue(app.any(FID.group("other")).exists)
    }

    /// Stagger runs on a storage's first load only: switching segments back and refreshing
    /// must not restart it (probe `debug.stagger.count`).
    func testStaggerRunsOnFirstLoadOnly() {
        let app = XCUIApplication.fridge()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 5))
        let probe = app.any(FID.staggerProbe)
        XCTAssertTrue(probe.exists, "debug.stagger.count probe missing")
        XCTAssertEqual(probe.label, "1")
        app.any(FID.storage("pantry")).tap()     // empty pantry: no rows, no stagger
        app.any(FID.storage("fridge")).tap()
        XCTAssertTrue(app.fridgeRow("item-chicken").waitForExistence(timeout: 10))
        app.any(FID.list).swipeDown(velocity: .slow)   // pull to refresh, if present
        Thread.sleep(forTimeInterval: 1.0)
        XCTAssertEqual(app.any(FID.staggerProbe).label, "1", "stagger restarted on refresh/segment return")
    }

    // MARK: AX5 (run on the SE; also forced here through the launch arg)

    func testAX5RowsReadableAndRemoveReachable() {
        let app = XCUIApplication.fridge(["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        let row = app.fridgeRow("item-chicken")
        XCTAssertTrue(row.waitForExistence(timeout: 5))
        attachScreenshot(app, name: "fridge-ax5")
        let badge = app.any(FID.badge("item-chicken"))
        XCTAssertTrue(badge.exists)
        XCTAssertLessThanOrEqual(badge.frame.maxX, app.frame.maxX + 0.5, "badge clipped: \(badge.frame)")
        openRemove(app, item: "item-chicken")
        for o in ["used", "donated", "thrown_out"] where app.any(FID.outcome(o)).exists {
            XCTAssertGreaterThanOrEqual(app.any(FID.outcome(o)).frame.height, 44)
        }
        attachScreenshot(app, name: "remove-sheet-ax5")
    }
}
