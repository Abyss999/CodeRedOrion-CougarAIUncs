import SwiftUI

/// Shared design tokens. Source of truth is docs/design/DESIGN_SYSTEM.md —
/// change both together. Views never use ad-hoc colors, sizes or fonts.
enum Theme {
    enum Colors {
        /// Adaptive tokens. Each resolves per trait collection (light/dark) from the
        /// dark-mode table in docs/design/DESIGN_SYSTEM.md; views never branch on scheme.
        static let ground = Color(light: 0xF4F8E8, dark: 0x0F1A12)
        static let surface = Color(light: 0xFFFFFF, dark: 0x18261B)
        static let lime = Color(light: 0xD9EC8F, dark: 0xD9EC8F)
        static let limeTint = Color(light: 0xEEF5D6, dark: 0x24361F)
        static let track = Color(light: 0xE3EDCB, dark: 0x223024)
        static let hairline = Color(light: 0xE6EDD6, dark: 0x2A3A2D)
        static let border = Color(light: 0xD3E0BF, dark: 0x34483A)
        static let forest = Color(light: 0x1F4D2B, dark: 0xB9D871)
        static let forestMid = Color(light: 0x3B7046, dark: 0x8FB45A)
        static let forestChip = Color(light: 0x2F6B3C, dark: 0x2C4A26)
        static let ink = Color(light: 0x13261A, dark: 0xE8F0DA)
        static let inkSecondary = Color(light: 0x2B3D30, dark: 0xC9D6BC)
        static let muted = Color(light: 0x45584A, dark: 0x9DB09F)
        static let tabInactive = Color(light: 0x5C6E5F, dark: 0x8FA391)
        static let onForest = Color(light: 0xF4F8E8, dark: 0x13261A)
        static let onForestMuted = Color(light: 0xC9D8BE, dark: 0x2F4A2A)
        static let urgentBg = Color(light: 0xFBE3CF, dark: 0x4A2614)
        static let urgentInk = Color(light: 0x8A3B0E, dark: 0xFFB98A)
        static let noteYellow = Color(light: 0xFFF6C7, dark: 0x3A3720)
        static let noteLime = Color(light: 0xE4F2C4, dark: 0x2A3A1F)
        static let chartSaved = Color(light: 0x277338, dark: 0x24783D)
        static let chartWasted = Color(light: 0xE8A04C, dark: 0xC6802F)
        /// No dark row in the design doc. Light: ink at 0.6 alpha (as before). Dark: pure
        /// black at 0.6 alpha, because a light-ink (#E8F0DA) scrim would brighten the
        /// content behind a sheet instead of dimming it.
        static let scrim = Color(light: 0x13261A, dark: 0x000000, alpha: 0.6)

        /// Light/dark hex pairs for every token, keyed by token name, so tests can assert
        /// exact resolved values. Keep in sync with the declarations above.
        static let hexTable: [String: (light: UInt32, dark: UInt32, alpha: Double)] = [
            "ground": (0xF4F8E8, 0x0F1A12, 1),
            "surface": (0xFFFFFF, 0x18261B, 1),
            "lime": (0xD9EC8F, 0xD9EC8F, 1),
            "limeTint": (0xEEF5D6, 0x24361F, 1),
            "track": (0xE3EDCB, 0x223024, 1),
            "hairline": (0xE6EDD6, 0x2A3A2D, 1),
            "border": (0xD3E0BF, 0x34483A, 1),
            "forest": (0x1F4D2B, 0xB9D871, 1),
            "forestMid": (0x3B7046, 0x8FB45A, 1),
            "forestChip": (0x2F6B3C, 0x2C4A26, 1),
            "ink": (0x13261A, 0xE8F0DA, 1),
            "inkSecondary": (0x2B3D30, 0xC9D6BC, 1),
            "muted": (0x45584A, 0x9DB09F, 1),
            "tabInactive": (0x5C6E5F, 0x8FA391, 1),
            "onForest": (0xF4F8E8, 0x13261A, 1),
            "onForestMuted": (0xC9D8BE, 0x2F4A2A, 1),
            "urgentBg": (0xFBE3CF, 0x4A2614, 1),
            "urgentInk": (0x8A3B0E, 0xFFB98A, 1),
            "noteYellow": (0xFFF6C7, 0x3A3720, 1),
            "noteLime": (0xE4F2C4, 0x2A3A1F, 1),
            "chartSaved": (0x277338, 0x24783D, 1),
            "chartWasted": (0xE8A04C, 0xC6802F, 1),
            "scrim": (0x13261A, 0x000000, 0.6),
        ]
    }

    enum Fonts {
        /// Outfit must be bundled and listed under UIAppFonts before these resolve.
        static func display(_ size: CGFloat, relativeTo style: Font.TextStyle) -> Font {
            .custom("Outfit-SemiBold", size: size, relativeTo: style)
        }
        static let hero = Fonts.display(48, relativeTo: .largeTitle)
        static let screenTitle = Fonts.display(30, relativeTo: .largeTitle)
        static let sheetTitle = Fonts.display(22, relativeTo: .title2)
        static let section = Fonts.display(20, relativeTo: .title3)
        static let button = Fonts.display(17, relativeTo: .headline)
        static let rowTitle = Font.callout.weight(.semibold)
        static let body = Font.body
        static let meta = Font.footnote
        static let badge = Font.footnote.weight(.semibold)
    }

    enum Spacing {
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let sm: CGFloat = 12
        static let m: CGFloat = 16
        static let gutter: CGFloat = 20
        static let l: CGFloat = 24
        static let xl: CGFloat = 32
    }

    enum Radius {
        static let badge: CGFloat = 10
        static let input: CGFloat = 12
        static let card: CGFloat = 16
        static let hero: CGFloat = 20
        static let sheet: CGFloat = 28
    }

    enum Size {
        static let minTouch: CGFloat = 44
        static let primaryButton: CGFloat = 56
        static let removalOption: CGFloat = 68
        static let addButton: CGFloat = 60
        static let avatar: CGFloat = 40
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

extension UIColor {
    /// sRGB colour from a 0xRRGGBB value, so it resolves to the exact hex.
    convenience init(hex: UInt32, alpha: Double = 1) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: CGFloat(alpha)
        )
    }
}

extension Color {
    /// Adaptive colour: resolves to `light` or `dark` (sRGB) from the trait collection.
    init(light: UInt32, dark: UInt32, alpha: Double = 1) {
        self.init(UIColor { traits in
            traits.userInterfaceStyle == .dark
                ? UIColor(hex: dark, alpha: alpha)
                : UIColor(hex: light, alpha: alpha)
        })
    }
}
