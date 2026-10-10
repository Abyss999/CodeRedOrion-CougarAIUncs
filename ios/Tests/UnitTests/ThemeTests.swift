import XCTest
@testable import FoodWasteReducer

final class ThemeTests: XCTestCase {
    func testSpacingScaleIsAscending() {
        let scale = [Theme.Spacing.xs, Theme.Spacing.s, Theme.Spacing.m, Theme.Spacing.l, Theme.Spacing.xl]
        XCTAssertEqual(scale, scale.sorted())
    }
}
