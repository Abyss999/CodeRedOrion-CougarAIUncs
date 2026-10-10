import SwiftUI

/// Shared design tokens. Source of truth is docs/design/DESIGN_SYSTEM.md —
/// change both together. Views never use ad-hoc colors, sizes or fonts.
enum Theme {
    enum Colors {
        static let ground = Color(hex: 0xF4F8E8)
        static let surface = Color(hex: 0xFFFFFF)
        static let lime = Color(hex: 0xD9EC8F)
        static let limeTint = Color(hex: 0xEEF5D6)
        static let track = Color(hex: 0xE3EDCB)
        static let hairline = Color(hex: 0xE6EDD6)
        static let border = Color(hex: 0xD3E0BF)
        static let forest = Color(hex: 0x1F4D2B)
        static let forestMid = Color(hex: 0x3B7046)
        static let forestChip = Color(hex: 0x2F6B3C)
        static let ink = Color(hex: 0x13261A)
        static let inkSecondary = Color(hex: 0x2B3D30)
        static let muted = Color(hex: 0x45584A)
        static let tabInactive = Color(hex: 0x5C6E5F)
        static let onForest = Color(hex: 0xF4F8E8)
        static let onForestMuted = Color(hex: 0xC9D8BE)
        static let urgentBg = Color(hex: 0xFBE3CF)
        static let urgentInk = Color(hex: 0x8A3B0E)
        static let noteYellow = Color(hex: 0xFFF6C7)
        static let noteLime = Color(hex: 0xE4F2C4)
        static let chartSaved = Color(hex: 0x277338)
        static let chartWasted = Color(hex: 0xE8A04C)
        static let scrim = Color(hex: 0x13261A).opacity(0.6)
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
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}
