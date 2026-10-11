import SwiftUI

/// Fridge group header text: 13 / semibold, uppercase, +0.04em tracking, in `muted`.
struct GroupHeaderText: View {
    let text: String
    var body: some View {
        Text(text)
            .font(Theme.Fonts.groupHeader)
            .tracking(Theme.Tracking.groupHeader)
            .textCase(.uppercase)
            .foregroundStyle(Theme.Colors.muted)
    }
}
