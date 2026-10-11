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
        /// Text on `forestChip`.
        static let onForestChip = Color(light: 0xF4F8E8, dark: 0xE8F0DA)
        static let ink = Color(light: 0x13261A, dark: 0xE8F0DA)
        static let inkSecondary = Color(light: 0x2B3D30, dark: 0xC9D6BC)
        static let muted = Color(light: 0x45584A, dark: 0x9DB09F)
        static let tabInactive = Color(light: 0x5C6E5F, dark: 0x8FA391)
        static let onForest = Color(light: 0xF4F8E8, dark: 0x13261A)
        static let onForestMuted = Color(light: 0xC9D8BE, dark: 0x2F4A2A)
        /// Text on the fixed `lime` fill (Home impact pill). Identical in both modes, like `lime`
        /// (artboard: #1F4D2B in light and dark). Not in `hexTable`: it is deliberately not adaptive.
        static let onLime = Color(light: 0x1F4D2B, dark: 0x1F4D2B)
        /// Undo toast countdown: the track behind the bar (Fridge/BatchUndo artboard: white at 10% on forest;
        /// dark, where forest is the light lime, ink at 10%) and the bar itself (`onForest` at 80%).
        static let toastTrack = Color(light: 0xFFFFFF, dark: 0x13261A, alpha: 0.1)
        static let toastBar = Color(light: 0xF4F8E8, dark: 0x13261A, alpha: 0.8)
        static let urgentBg = Color(light: 0xFBE3CF, dark: 0x4A2614)
        static let urgentInk = Color(light: 0x8A3B0E, dark: 0xFFB98A)
        static let noteYellow = Color(light: 0xFFF6C7, dark: 0x3A3720)
        static let noteLime = Color(light: 0xE4F2C4, dark: 0x2A3A1F)
        static let chartSaved = Color(light: 0x277338, dark: 0x24783D)
        static let chartWasted = Color(light: 0xE8A04C, dark: 0xC6802F)
        static let useSoonBg = Color(light: 0xFFF1B8, dark: 0x3A3112)
        static let useSoonInk = Color(light: 0x6B5000, dark: 0xFFD970)
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
            "onForestChip": (0xF4F8E8, 0xE8F0DA, 1),
            "ink": (0x13261A, 0xE8F0DA, 1),
            "inkSecondary": (0x2B3D30, 0xC9D6BC, 1),
            "muted": (0x45584A, 0x9DB09F, 1),
            "tabInactive": (0x5C6E5F, 0x8FA391, 1),
            "onForest": (0xF4F8E8, 0x13261A, 1),
            "onForestMuted": (0xC9D8BE, 0x2F4A2A, 1),
            "toastTrack": (0xFFFFFF, 0x13261A, 0.1),
            "toastBar": (0xF4F8E8, 0x13261A, 0.8),
            "urgentBg": (0xFBE3CF, 0x4A2614, 1),
            "urgentInk": (0x8A3B0E, 0xFFB98A, 1),
            "noteYellow": (0xFFF6C7, 0x3A3720, 1),
            "noteLime": (0xE4F2C4, 0x2A3A1F, 1),
            "chartSaved": (0x277338, 0x24783D, 1),
            "chartWasted": (0xE8A04C, 0xC6802F, 1),
            "useSoonBg": (0xFFF1B8, 0x3A3112, 1),
            "useSoonInk": (0x6B5000, 0xFFD970, 1),
            "scrim": (0x13261A, 0x000000, 0.6),
        ]
    }

    /// Food-group identity colours (DESIGN_SYSTEM "Food-group colours"). Adaptive. Only for
    /// food-group identity; never for status or charts.
    enum FoodGroup {
        struct Palette {
            let stroke: Color
            let tile: Color
        }
        static let protein = Palette(stroke: Color(light: 0xB0412E, dark: 0xFF9E8A), tile: Color(light: 0xFBE4DE, dark: 0x3D1F1A))
        static let veggies = Palette(stroke: Color(light: 0x2F7A3A, dark: 0x8FD69A), tile: Color(light: 0xE2F1D8, dark: 0x1C3320))
        static let fruit = Palette(stroke: Color(light: 0xA8366E, dark: 0xF59AC6), tile: Color(light: 0xF8E1EC, dark: 0x3A1C2B))
        static let dairy = Palette(stroke: Color(light: 0x3A5BA0, dark: 0x9DB7F0), tile: Color(light: 0xE2E9F7, dark: 0x1C2540))
        static let grains = Palette(stroke: Color(light: 0x8A6414, dark: 0xE8C46A), tile: Color(light: 0xF5EBCD, dark: 0x33290F))
        static let pantry = Palette(stroke: Color(light: 0x6A4FA3, dark: 0xC1AAF0), tile: Color(light: 0xECE5F7, dark: 0x2A2140))
        static let leftovers = Palette(stroke: Color(light: 0x1F7A78, dark: 0x7FD8D3), tile: Color(light: 0xDAF0EE, dark: 0x14302F))
        static let frozen = Palette(stroke: Color(light: 0x1E7BA8, dark: 0x86CBEE), tile: Color(light: 0xDCEFF8, dark: 0x122C3A))
        static let other = Palette(stroke: Color(light: 0x5C6E5F, dark: 0xB4C2B6), tile: Color(light: 0xEAEFE6, dark: 0x243026))

        /// Light/dark hex pairs per group, so tests can assert exact resolved values.
        static let hexTable: [String: (stroke: (light: UInt32, dark: UInt32), tile: (light: UInt32, dark: UInt32))] = [
            "protein": (stroke: (0xB0412E, 0xFF9E8A), tile: (0xFBE4DE, 0x3D1F1A)),
            "veggies": (stroke: (0x2F7A3A, 0x8FD69A), tile: (0xE2F1D8, 0x1C3320)),
            "fruit": (stroke: (0xA8366E, 0xF59AC6), tile: (0xF8E1EC, 0x3A1C2B)),
            "dairy": (stroke: (0x3A5BA0, 0x9DB7F0), tile: (0xE2E9F7, 0x1C2540)),
            "grains": (stroke: (0x8A6414, 0xE8C46A), tile: (0xF5EBCD, 0x33290F)),
            "pantry": (stroke: (0x6A4FA3, 0xC1AAF0), tile: (0xECE5F7, 0x2A2140)),
            "leftovers": (stroke: (0x1F7A78, 0x7FD8D3), tile: (0xDAF0EE, 0x14302F)),
            "frozen": (stroke: (0x1E7BA8, 0x86CBEE), tile: (0xDCEFF8, 0x122C3A)),
            "other": (stroke: (0x5C6E5F, 0xB4C2B6), tile: (0xEAEFE6, 0x243026)),
        ]
    }

    enum Fonts {
        /// Outfit static instances bundled in Resources/Fonts and listed under UIAppFonts.
        /// PostScript names: `Outfit-Medium` (500) and `Outfit-SemiBold` (600).
        static let displayMedium = "Outfit-Medium"
        static let displaySemiBold = "Outfit-SemiBold"

        static func display(_ size: CGFloat, relativeTo style: Font.TextStyle, medium: Bool = false) -> Font {
            .custom(medium ? displayMedium : displaySemiBold, size: size, relativeTo: style)
        }
        static let hero = Fonts.display(48, relativeTo: .largeTitle)
        static let signInHeadline = Fonts.display(44, relativeTo: .largeTitle)
        static let screenTitle = Fonts.display(30, relativeTo: .largeTitle)
        static let sheetTitle = Fonts.display(22, relativeTo: .title2)
        static let section = Fonts.display(20, relativeTo: .title3)
        static let cardHeading = Fonts.display(17, relativeTo: .headline)
        static let button = Fonts.display(17, relativeTo: .headline)
        /// Group header (Fridge): 13 / 600, uppercase, tracked +0.04em. Apply `Theme.Tracking.groupHeader`
        /// and `.textCase(.uppercase)` (or use `GroupHeaderText`).
        static let groupHeader = Font.footnote.weight(.semibold)
        static let rowTitle = Font.callout.weight(.semibold)
        static let body = Font.body
        static let meta = Font.footnote
        static let badge = Font.footnote.weight(.semibold)
        /// Remove sheet outcome tile title: Outfit 18 / 600 (RemoveSheet artboard).
        static let tileTitle = Fonts.display(18, relativeTo: .headline)
        /// Sheet subtitle under the sheet title (artboards: 14 pt, nearest text style).
        static let sheetMeta = Font.subheadline
        /// Storage segmented control (Fridge artboard: 15 pt, 600 selected / 500 unselected).
        static let segment = Font.subheadline.weight(.medium)
        static let segmentSelected = Font.subheadline.weight(.semibold)
        /// Info callout body (RemoveReason artboard: 14 pt).
        static let callout = Font.subheadline
    }

    enum Tracking {
        /// Hero number: -2% of 48 pt.
        static let hero: CGFloat = -0.96
        /// Group header: +0.04em of 13 pt.
        static let groupHeader: CGFloat = 0.52
    }

    enum Spacing {
        /// 2: title-to-subtitle gap in tiles and sheet headers (artboards).
        static let xxs: CGFloat = 2
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let sm: CGFloat = 12
        static let m: CGFloat = 16
        static let gutter: CGFloat = 20
        static let l: CGFloat = 24
        static let xl: CGFloat = 32
        /// 6: title/meta text stack inside a row, and the group header icon-to-label gap (artboards).
        static let stack: CGFloat = 6
        /// 10: horizontal padding inside a badge pill (vertical is `xs`).
        static let badgeHorizontal: CGFloat = 10
        /// 10: gap between removal tiles and between reason tiles (Remove artboards).
        static let tileGap: CGFloat = 10
        /// 14: icon-to-text gap inside an outcome tile, and reason tile padding (Remove artboards).
        static let tileInner: CGFloat = 14
        /// 18: vertical gap between blocks of a removal sheet (Remove artboards).
        static let sheetSection: CGFloat = 18
    }

    enum Radius {
        static let badge: CGFloat = 10
        /// 14: segmented-control track, info callouts, RemoveSheet header tile (artboards).
        static let control: CGFloat = 14
        /// 18: AddSheet option tiles and pill buttons (artboards).
        static let optionTile: CGFloat = 18
        static let input: CGFloat = 12
        /// Skeleton text bars.
        static let bar: CGFloat = 4
        /// Food-group icon tile and skeleton avatar.
        static let avatar: CGFloat = 12
        static let card: CGFloat = 16
        static let hero: CGFloat = 20
        static let sheet: CGFloat = 28
    }

    enum Size {
        static let minTouch: CGFloat = 44
        static let primaryButton: CGFloat = 56
        static let removalOption: CGFloat = 68
        static let avatar: CGFloat = 40
        /// Food-group glyph on the 40 pt avatar tile (Fridge artboard: 22 pt).
        static let avatarGlyph: CGFloat = 22
        /// Food-group glyph in the Fridge group header (Fridge artboard: 16 pt).
        static let groupHeaderIcon: CGFloat = 16
        /// Undo toast countdown bar height.
        static let toastProgress: CGFloat = 3
        /// FridgeSelect checkbox leading column (artboard: 52 pt wide) and the box inside it (24 pt).
        static let selectColumn: CGFloat = 52
        static let checkbox: CGFloat = 24
        /// FridgeSelect bottom bar buttons (artboard: 52 pt tall).
        static let selectBarButton: CGFloat = 52
        /// Listing badge on the Remove sheet header tile (artboard: 18 pt).
        static let listingBadge: CGFloat = 18
        /// FridgeSelect bottom bar corner radius (artboard: 28 pt).
        static let selectBarCorner: CGFloat = 28
        /// Skeleton placeholders, shaped like an `ItemRow`'s title, meta line and `ExpiryBadge`.
        static let skeletonTitle = CGSize(width: 140, height: 14)
        static let skeletonMeta = CGSize(width: 96, height: 11)
        static let skeletonBadge = CGSize(width: 56, height: 24)
        /// Storage segmented control: 36 pt segments in a 4 pt-padded track (44 pt total target).
        static let segment: CGFloat = 36
        /// Remove sheet header tile (48 pt) for the item's food group.
        static let sheetHeaderTile: CGFloat = 48
        /// Waste-reason tile minimum height (RemoveReason artboard).
        static let reasonTile: CGFloat = 96
        /// Text button at the bottom of a sheet (Cancel).
        static let sheetTextButton: CGFloat = 48
        /// Checkmark that scales in on the tapped removal tile.
        static let tileCheckmark: CGFloat = 24
        /// First-guess height of the Remove sheet before its content is measured.
        static let removeSheetEstimate: CGFloat = 560
        /// Social: minimum height of a request note (Social artboard: 168).
        static let noteMin: CGFloat = 168
        /// Social: filled circle inside the 44 pt "+" button beside "Requests" (34).
        static let addGlyphCircle: CGFloat = 34
        /// Social: food tile in the Pantry widget (36) and its loading placeholder height.
        static let pantryTile: CGFloat = 36
        static let pantryTilePlaceholder: CGFloat = 72
        /// ClaimedItem: map preview height.
        static let mapPreview: CGFloat = 160
        /// DEBUG-only invisible probe elements read by UI tests.
        static let debugProbe: CGFloat = 1
    }

    /// Stroke widths.
    enum Stroke {
        /// Outlined tiles and inputs (`border`).
        static let hairline: CGFloat = 1
        /// Selected tile / focus ring (`forest`).
        static let selected: CGFloat = 2
    }

    enum Opacity {
        /// Fill behind a button sitting on a forest surface (Undo on the toast), tinted `onForest`.
        static let onForestFill: Double = 0.18
        /// DEBUG-only probe elements: visually invisible but still in the accessibility tree.
        static let debugProbe: Double = 0.01
    }

    /// Drop shadows. Colour is always `Theme.Colors.scrim` at `opacity`.
    enum Shadow {
        struct Style {
            let opacity: Double
            let radius: CGFloat
            let y: CGFloat
        }
        /// Floating toast above content.
        static let toast = Style(opacity: 0.25, radius: 12, y: 4)
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
