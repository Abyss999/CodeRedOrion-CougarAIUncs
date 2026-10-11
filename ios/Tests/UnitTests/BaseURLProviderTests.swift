import XCTest
@testable import FoodWasteReducer

final class BaseURLProviderTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suite: String!

    override func setUp() {
        suite = "BaseURLProviderTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suite)
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suite)
    }

    private func provider(info: String? = nil) -> BaseURLProvider {
        BaseURLProvider(defaults: defaults, infoValue: info)
    }

    // MARK: precedence: override > Info.plist > Simulator default

    func testFallsBackToSimulatorDefault() {
        XCTAssertEqual(provider().current.absoluteString, "http://127.0.0.1:5055")
    }

    func testInfoPlistBeatsFallback() {
        XCTAssertEqual(provider(info: "https://api.example.com").current.absoluteString, "https://api.example.com")
    }

    func testInvalidInfoPlistValueFallsBack() {
        XCTAssertEqual(provider(info: "ftp://nope").current, BaseURLProvider.fallback)
        XCTAssertEqual(provider(info: "").current, BaseURLProvider.fallback)
    }

    #if DEBUG
    func testOverrideBeatsInfoPlist() {
        let p = provider(info: "https://api.example.com")
        XCTAssertTrue(p.setOverride("https://abc.trycloudflare.com"))
        XCTAssertEqual(p.current.absoluteString, "https://abc.trycloudflare.com")
        XCTAssertEqual(p.defaultURL.absoluteString, "https://api.example.com")
    }

    func testResetReturnsToDefault() {
        let p = provider(info: "https://api.example.com")
        p.setOverride("http://192.168.1.5:5055")
        p.resetOverride()
        XCTAssertNil(p.overrideURL)
        XCTAssertEqual(p.current.absoluteString, "https://api.example.com")
    }

    func testInvalidOverrideIsRejectedAndNotStored() {
        let p = provider()
        XCTAssertFalse(p.setOverride("ftp://x.com"))
        XCTAssertNil(defaults.string(forKey: BaseURLProvider.overrideKey))
        XCTAssertEqual(p.current, BaseURLProvider.fallback)
    }

    func testPreviouslyValidOverrideSurvivesRejectedOne() {
        let p = provider()
        p.setOverride("https://ok.example.com")
        XCTAssertFalse(p.setOverride("javascript:alert(1)"))
        XCTAssertEqual(p.current.absoluteString, "https://ok.example.com")
    }

    func testCorruptStoredOverrideIsIgnored() {
        defaults.set("not a url", forKey: BaseURLProvider.overrideKey)
        XCTAssertEqual(provider().current, BaseURLProvider.fallback)
    }

    func testOverrideAppliesToExistingProviderWithoutRebuild() {
        let p = provider()
        let before = p.current
        p.setOverride("https://later.example.com")
        XCTAssertNotEqual(p.current, before)
    }
    #endif

    // MARK: validation

    func testValidationAcceptsHttpAndHttps() {
        XCTAssertNotNil(BaseURLProvider.validate("http://127.0.0.1:5055"))
        XCTAssertNotNil(BaseURLProvider.validate("https://x.trycloudflare.com"))
        XCTAssertNotNil(BaseURLProvider.validate("HTTPS://Example.com"))
    }

    func testValidationRejectsOtherSchemesAndGarbage() {
        for bad in ["", "   ", "ftp://a.com", "file:///etc/passwd", "javascript:alert(1)",
                    "example.com", "http://", "https://", "//a.com", "http://a.com?x=1", "http://a.com#f",
                    "not a url", "mailto:a@b.com"] {
            XCTAssertNil(BaseURLProvider.validate(bad), "should reject \(bad)")
        }
    }

    func testValidationTrimsWhitespaceAndTrailingSlashes() {
        XCTAssertEqual(BaseURLProvider.validate("  https://a.com/// \n")?.absoluteString, "https://a.com")
    }
}
