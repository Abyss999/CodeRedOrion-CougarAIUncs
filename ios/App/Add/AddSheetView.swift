import SwiftUI

/// The sheet the Add tab presents. Placeholder until the Add flow lands; that PR edits only this folder.
struct AddSheetView: View {
    var body: some View {
        Text("Add")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.Colors.ground.ignoresSafeArea())
            .presentationDetents([.medium, .large])
            .presentationCornerRadius(Theme.Radius.sheet)
            .accessibilityIdentifier(AccessibilityID.Add.sheet)
    }
}
