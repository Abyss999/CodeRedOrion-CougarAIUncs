import SwiftUI

/// Shared design tokens. Source of truth is docs/design/DESIGN_SYSTEM.md —
/// change both together. Values below are placeholders until the designs are approved.
enum Theme {
    enum Colors {
        static let primaryLight = Color(red: 0.86, green: 0.93, blue: 0.62) // light green-yellow
        static let primaryDeep = Color(red: 0.16, green: 0.40, blue: 0.22)  // deep green
        static let onPrimaryDeep = Color.white
    }

    enum Spacing {
        static let xs: CGFloat = 4
        static let s: CGFloat = 8
        static let m: CGFloat = 16
        static let l: CGFloat = 24
        static let xl: CGFloat = 32
    }

    enum Radius {
        static let card: CGFloat = 16
        static let button: CGFloat = 12
    }
}
