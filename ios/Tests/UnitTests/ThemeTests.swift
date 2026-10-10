import XCTest
import SwiftUI
import UIKit
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

    // MARK: - Adaptive (light/dark) tokens, per the Dark mode table in DESIGN_SYSTEM.md

    private func hex(_ color: Color, _ style: UIUserInterfaceStyle) -> String {
        let resolved = UIColor(color).resolvedColor(with: UITraitCollection(userInterfaceStyle: style))
        var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        let space = CGColorSpace(name: CGColorSpace.sRGB)!
        let cg = resolved.cgColor.converted(to: space, intent: .defaultIntent, options: nil) ?? resolved.cgColor
        UIColor(cgColor: cg).getRed(&r, green: &g, blue: &b, alpha: &a)
        func c(_ v: CGFloat) -> Int { Int((v * 255).rounded()) }
        return String(format: "#%02X%02X%02X", c(r), c(g), c(b))
    }

    private typealias Row = (name: String, color: Color, light: String, dark: String)

    private var darkTable: [Row] {
        let C = Theme.Colors.self
        return [
            ("ground", C.ground, "#F4F8E8", "#0F1A12"),
            ("surface", C.surface, "#FFFFFF", "#18261B"),
            ("lime", C.lime, "#D9EC8F", "#D9EC8F"),
            ("limeTint", C.limeTint, "#EEF5D6", "#24361F"),
            ("track", C.track, "#E3EDCB", "#223024"),
            ("hairline", C.hairline, "#E6EDD6", "#2A3A2D"),
            ("border", C.border, "#D3E0BF", "#34483A"),
            ("forest", C.forest, "#1F4D2B", "#B9D871"),
            ("forestMid", C.forestMid, "#3B7046", "#8FB45A"),
            ("forestChip", C.forestChip, "#2F6B3C", "#2C4A26"),
            ("ink", C.ink, "#13261A", "#E8F0DA"),
            ("inkSecondary", C.inkSecondary, "#2B3D30", "#C9D6BC"),
            ("muted", C.muted, "#45584A", "#9DB09F"),
            ("tabInactive", C.tabInactive, "#5C6E5F", "#8FA391"),
            ("onForest", C.onForest, "#F4F8E8", "#13261A"),
            ("onForestMuted", C.onForestMuted, "#C9D8BE", "#2F4A2A"),
            ("urgentBg", C.urgentBg, "#FBE3CF", "#4A2614"),
            ("urgentInk", C.urgentInk, "#8A3B0E", "#FFB98A"),
            ("noteYellow", C.noteYellow, "#FFF6C7", "#3A3720"),
            ("noteLime", C.noteLime, "#E4F2C4", "#2A3A1F"),
            ("chartSaved", C.chartSaved, "#277338", "#24783D"),
            ("chartWasted", C.chartWasted, "#E8A04C", "#C6802F"),
        ]
    }

    func testEveryTokenMatchesLightValue() {
        for row in darkTable {
            XCTAssertEqual(hex(row.color, .light), row.light, "\(row.name) light")
        }
    }

    func testEveryTokenMatchesDarkValue() {
        for row in darkTable {
            XCTAssertEqual(hex(row.color, .dark), row.dark, "\(row.name) dark")
        }
    }

    func testTokensDifferBetweenLightAndDarkExceptLime() {
        for row in darkTable {
            let l = hex(row.color, .light), d = hex(row.color, .dark)
            if row.name == "lime" {
                XCTAssertEqual(l, d, "lime must be identical in both modes")
            } else {
                XCTAssertNotEqual(l, d, "\(row.name) should be adaptive")
            }
        }
    }

    func testSelectedTabTintIsVisibleOnDarkGround() {
        // Regression for IOS-1: forest on the dark ground must have real contrast.
        func lum(_ h: String) -> Double {
            let v = UInt32(h.dropFirst(), radix: 16)!
            func f(_ x: UInt32) -> Double { let c = Double(x) / 255; return c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4) }
            return 0.2126 * f((v >> 16) & 255) + 0.7152 * f((v >> 8) & 255) + 0.0722 * f(v & 255)
        }
        let a = lum(hex(Theme.Colors.forest, .dark)), b = lum(hex(Theme.Colors.ground, .dark))
        XCTAssertGreaterThanOrEqual((max(a, b) + 0.05) / (min(a, b) + 0.05), 7.0)
    }
}
