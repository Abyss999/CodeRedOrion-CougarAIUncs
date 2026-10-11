import XCTest

/// Shared helpers. The identifier strings mirror `AccessibilityID` in the app (UI tests cannot
/// import the app module). See ios/Tests/README.md for the convention.
enum ID {
    static let tabs = ["tab.home", "tab.recipes", "tab.add", "tab.fridge", "tab.social"]
    static let home = "tab.home", recipes = "tab.recipes", add = "tab.add", fridge = "tab.fridge", social = "tab.social"
    static let tabLabel = ["tab.home": "Home", "tab.recipes": "Recipes", "tab.add": "Add",
                           "tab.fridge": "Fridge", "tab.social": "Social"]
    static let addSheet = "add.sheet"
    static let versionLabel = "debug.versionLabel"
    static let debugSheet = "debug.settings"
    static let urlField = "debug.baseURL.field"
    static let urlSave = "debug.baseURL.save"
    static let urlReset = "debug.baseURL.reset"
    static let urlError = "debug.baseURL.error"
    static let urlCurrent = "debug.baseURL.current"
}

extension XCUIApplication {
    /// Launch against the mock API, signed in, with the given extra arguments.
    static func mockSignedIn(_ extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-UITestMockAPI", "-UITestSignedIn"] + extra
        app.launch()
        return app
    }

    /// The Add sheet's content carries `add.sheet` (a static text today); match any element type.
    var addSheet: XCUIElement { descendants(matching: .any)[ID.addSheet].firstMatch }

    /// Tab bar button by its identifier constant. Resolved through the tab's accessibility label
    /// because identifiers on the tab bar are unreliable (IOS-4); labels are what VoiceOver reads.
    func tab(_ id: String) -> XCUIElement { tabBars.buttons[ID.tabLabel[id] ?? id] }
}

extension XCTestCase {
    func attachScreenshot(_ app: XCUIApplication, name: String) {
        let a = XCTAttachment(screenshot: app.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }
}
