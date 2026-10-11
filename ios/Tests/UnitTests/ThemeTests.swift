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
        for size in [Theme.Size.primaryButton, Theme.Size.removalOption] {
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
            ("useSoonBg", C.useSoonBg, "#FFF1B8", "#3A3112"),
            ("useSoonInk", C.useSoonInk, "#6B5000", "#FFD970"),
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

    // MARK: - Food-group palettes (DESIGN_SYSTEM "Food-group colours"), literals copied from the doc

    private typealias GroupRow = (name: String, p: Theme.FoodGroup.Palette,
                                  sl: String, st: String, dl: String, dt: String)

    private var groups: [GroupRow] {
        let G = Theme.FoodGroup.self
        return [
            ("protein", G.protein, "#B0412E", "#FBE4DE", "#FF9E8A", "#3D1F1A"),
            ("veggies", G.veggies, "#2F7A3A", "#E2F1D8", "#8FD69A", "#1C3320"),
            ("fruit", G.fruit, "#A8366E", "#F8E1EC", "#F59AC6", "#3A1C2B"),
            ("dairy", G.dairy, "#3A5BA0", "#E2E9F7", "#9DB7F0", "#1C2540"),
            ("grains", G.grains, "#8A6414", "#F5EBCD", "#E8C46A", "#33290F"),
            ("pantry", G.pantry, "#6A4FA3", "#ECE5F7", "#C1AAF0", "#2A2140"),
            ("leftovers", G.leftovers, "#1F7A78", "#DAF0EE", "#7FD8D3", "#14302F"),
            ("frozen", G.frozen, "#1E7BA8", "#DCEFF8", "#86CBEE", "#122C3A"),
            ("other", G.other, "#5C6E5F", "#EAEFE6", "#B4C2B6", "#243026"),
        ]
    }

    func testFoodGroupPaletteMatchesDesignSystem() {
        for g in groups {
            XCTAssertEqual(hex(g.p.stroke, .light), g.sl, "\(g.name) stroke light")
            XCTAssertEqual(hex(g.p.tile, .light), g.st, "\(g.name) tile light")
            XCTAssertEqual(hex(g.p.stroke, .dark), g.dl, "\(g.name) stroke dark")
            XCTAssertEqual(hex(g.p.tile, .dark), g.dt, "\(g.name) tile dark")
        }
    }

    func testEveryFoodGroupEnumCaseHasAPalette() {
        XCTAssertEqual(Set(FoodGroup.allCases.map(\.rawValue)), Set(groups.map(\.name)))
        for g in FoodGroup.allCases { _ = g.palette }
    }

    func testFoodGroupStrokeContrastOnTile() {
        // DESIGN_SYSTEM: stroke clears 3:1 on its tile (light worst 3.98, dark worst 7.39).
        for g in groups {
            XCTAssertGreaterThanOrEqual(contrast(g.sl, g.st), 3.0, "\(g.name) light")
            XCTAssertGreaterThanOrEqual(contrast(g.dl, g.dt), 3.0, "\(g.name) dark")
        }
    }

    func testUseSoonContrast() {
        // DESIGN_SYSTEM: 6.7:1 light, 9.5:1 dark.
        XCTAssertGreaterThanOrEqual(contrast("#6B5000", "#FFF1B8"), 6.5)
        XCTAssertGreaterThanOrEqual(contrast("#FFD970", "#3A3112"), 9.0)
    }

    private func contrast(_ a: String, _ b: String) -> Double {
        func lum(_ h: String) -> Double {
            let v = UInt32(h.dropFirst(), radix: 16)!
            func f(_ x: UInt32) -> Double { let c = Double(x) / 255; return c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4) }
            return 0.2126 * f((v >> 16) & 255) + 0.7152 * f((v >> 8) & 255) + 0.0722 * f(v & 255)
        }
        let x = lum(a), y = lum(b)
        return (max(x, y) + 0.05) / (min(x, y) + 0.05)
    }

    // MARK: - Radii (artboards: 14 and 18)

    func testRadii() {
        XCTAssertEqual(Theme.Radius.control, 14)
        XCTAssertEqual(Theme.Radius.optionTile, 18)
        XCTAssertEqual(Theme.Radius.sheet, 28)
        XCTAssertEqual(Theme.Radius.hero, 20)
        XCTAssertEqual(Theme.Radius.card, 16)
        XCTAssertEqual(Theme.Radius.input, 12)
        XCTAssertEqual(Theme.Radius.badge, 10)
    }

    // MARK: - Fonts (Outfit bundled and registered through UIAppFonts)

    func testOutfitPostScriptNamesResolve() {
        for name in ["Outfit-Medium", "Outfit-SemiBold"] {
            XCTAssertNotNil(UIFont(name: name, size: 17), "\(name) is not registered; check UIAppFonts and Resources/Fonts")
        }
        XCTAssertEqual(Theme.Fonts.displayMedium, "Outfit-Medium")
        XCTAssertEqual(Theme.Fonts.displaySemiBold, "Outfit-SemiBold")
    }

    func testUIAppFontsListsBundledFiles() {
        let listed = Bundle.main.object(forInfoDictionaryKey: "UIAppFonts") as? [String] ?? []
        XCTAssertTrue(listed.contains("Outfit-Medium.ttf"))
        XCTAssertTrue(listed.contains("Outfit-SemiBold.ttf"))
    }
}
