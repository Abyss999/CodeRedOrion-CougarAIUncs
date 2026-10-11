import SwiftUI

enum AppTab: Hashable {
    case home, recipes, add, fridge, social
}

/// Placeholder tab shell (screens come later from docs/design/). Uses the system `TabView`
/// (Liquid Glass on iOS 26). **Add is a tab that presents a sheet and leaves the selection
/// unchanged**: selecting it reverts to the previous tab and shows `AddSheetPlaceholder`.
struct RootTabView: View {
    @State private var selection: AppTab = .home
    @State private var showAdd = false

    var body: some View {
        TabView(selection: $selection) {
            Tab("Home", systemImage: "house", value: AppTab.home) {
                placeholder("Home") { VersionLabel() }
            }
            .accessibilityIdentifier(AccessibilityID.Tab.home)
            Tab("Recipes", systemImage: "frying.pan", value: AppTab.recipes) { placeholder("Recipes") }
                .accessibilityIdentifier(AccessibilityID.Tab.recipes)
            Tab("Add", systemImage: "plus.circle.fill", value: AppTab.add) { placeholder("Add") }
                .accessibilityIdentifier(AccessibilityID.Tab.add)
            Tab("Fridge", systemImage: "refrigerator", value: AppTab.fridge) { placeholder("Fridge / Pantry") }
                .accessibilityIdentifier(AccessibilityID.Tab.fridge)
            Tab("Social", systemImage: "person.2", value: AppTab.social) { placeholder("Social") }
                .accessibilityIdentifier(AccessibilityID.Tab.social)
        }
        .tint(Theme.Colors.forest)
        .onChange(of: selection) { old, new in
            if new == .add {
                selection = old
                showAdd = true
            }
        }
        .sheet(isPresented: $showAdd) { AddSheetPlaceholder() }
    }

    private func placeholder<Extra: View>(_ title: String, @ViewBuilder extra: () -> Extra = { EmptyView() }) -> some View {
        VStack(spacing: Theme.Spacing.m) {
            Text(title)
            extra()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.Colors.ground.ignoresSafeArea())
    }
}

/// Empty placeholder until the Add sheet is built.
struct AddSheetPlaceholder: View {
    var body: some View {
        Text("Add")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.Colors.ground.ignoresSafeArea())
            .presentationDetents([.medium, .large])
            .presentationCornerRadius(Theme.Radius.sheet)
            .accessibilityIdentifier(AccessibilityID.Add.sheet)
    }
}
