import XCTest

final class LaunchUITests: XCTestCase {
    func testAppLaunchesToTabBar() {
        let app = XCUIApplication()
        app.launchArguments = ["-UITestMockAPI", "-UITestSignedIn"]
        app.launch()
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 5))
    }
}
