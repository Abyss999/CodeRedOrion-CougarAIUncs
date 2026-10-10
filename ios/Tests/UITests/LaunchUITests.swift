import XCTest

final class LaunchUITests: XCTestCase {
    func testAppLaunchesToTabBar() {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 5))
    }
}
