import XCTest

/// Shared helpers. The identifier strings mirror `AccessibilityID` in the app (UI tests cannot
/// import the app module). See ios/Tests/README.md for the convention.
enum ID {
    static let tabs = ["tab.home", "tab.recipes", "tab.add", "tab.fridge", "tab.social"]
    static let home = "tab.home", recipes = "tab.recipes", add = "tab.add", fridge = "tab.fridge", social = "tab.social"
    static let tabLabel = ["tab.home": "Home", "tab.recipes": "Recipes", "tab.add": "Add",
                           "tab.fridge": "Fridge", "tab.social": "Social"]
    static let addSheet = "add.sheet"
    static let versionLabel = "debug.versionlabel"
    static let debugSheet = "debug.settings"
    static let urlField = "debug.baseurl.field"
    static let urlSave = "debug.baseurl.save"
    static let urlReset = "debug.baseurl.reset"
    static let urlError = "debug.baseurl.error"
    static let urlCurrent = "debug.baseurl.current"
    static let toast = "toast.undo"
    static let toastButton = "toast.undo.button"
    static let toastMessage = "toast.undo.message"
    static let toastMarker = "toast.undo.marker"
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

    /// Undo toast container (`accessibilityElement(children: .contain)`, so it is an `Other`).
    var toast: XCUIElement { descendants(matching: .any)[ID.toast].firstMatch }

    /// The Debug base-URL error is a `Label`: SwiftUI puts `debug.baseurl.error` on BOTH the icon
    /// (Image, label "Warning", not hittable) and the text. Match the text.
    var urlError: XCUIElement { staticTexts[ID.urlError].firstMatch }

    /// Tab bar button by its identifier constant. Resolved through the tab's accessibility label
    /// because identifiers on the tab bar are unreliable (IOS-4); labels are what VoiceOver reads.
    func tab(_ id: String) -> XCUIElement { tabBars.buttons[ID.tabLabel[id] ?? id] }
}

extension XCUIElement {
    /// A tab bar button is a leaf for VoiceOver: hittable, labelled and a button.
    var isAccessibilityElementForVoiceOver: Bool { elementType == .button && !label.isEmpty && isHittable }
}

extension XCTestCase {
    func attachScreenshot(_ app: XCUIApplication, name: String) {
        let a = XCTAttachment(screenshot: app.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }
}
