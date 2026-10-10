import XCTest
@testable import FoodWasteReducer

final class ThemeTests: XCTestCase {
    func testSpacingScaleIsAscending() {
        let scale = [Theme.Spacing.xs, Theme.Spacing.s, Theme.Spacing.sm, Theme.Spacing.m,
                     Theme.Spacing.gutter, Theme.Spacing.l, Theme.Spacing.xl]
        XCTAssertEqual(scale, scale.sorted())
    }

    func testTouchTargetsMeetMinimum() {
        for size in [Theme.Size.primaryButton, Theme.Size.removalOption, Theme.Size.addButton] {
            XCTAssertGreaterThanOrEqual(size, Theme.Size.minTouch)
        }
    }
}
