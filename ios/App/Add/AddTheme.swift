import SwiftUI

extension Theme {
    /// Sizes taken from the Add / PhotoReview artboards that no shared token covers. Mirror in DESIGN_SYSTEM.md.
    enum AddFlow {
        /// "Snap your fridge" hero tile: 88 pt minimum, 56 pt icon tile, 28 pt glyph.
        static let heroMinHeight: CGFloat = 88
        static let heroIconTile: CGFloat = 56
        static let heroGlyph: CGFloat = 28
        /// 2x2 option tile minimum height and its 40 pt icon tile.
        static let tileMinHeight: CGFloat = 112
        static let tileIconTile: CGFloat = 40
        static let tileGlyph: CGFloat = 22
        /// DetectedItemRow checkbox ring.
        static let checkbox: CGFloat = 24
        static let checkboxTick: CGFloat = 12
        /// QuantityStepper buttons: 44 pt wide (round 3).
        static let stepperButtonWidth: CGFloat = 44
        static let amountMinWidth: CGFloat = 48
        /// Inline amount editor.
        static let amountFieldWidth: CGFloat = 88
        static let unitMenuMinWidth: CGFloat = 72
        /// Photo blocks per screen.
        static let analyzingPhotoHeight: CGFloat = 340
        static let reviewPhotoHeight: CGFloat = 200
        static let errorPhotoHeight: CGFloat = 120
        /// Analyzing spinner.
        static let spinner: CGFloat = 36
        static let spinnerLine: CGFloat = 3.5
        /// Error / done icon disc.
        static let statusDisc: CGFloat = 52
        /// Detection box stroke.
        static let boxLine: CGFloat = 2
        /// Box draw-on (stroke trim 0 -> 1), MOTION.md "Photo review".
        static let boxDraw: Animation = .easeOut(duration: 0.4)
        /// Analyzing: after this long the screen adds "This can take a little longer".
        static let slowNoticeAfter: Duration = .seconds(12)
    }
}
