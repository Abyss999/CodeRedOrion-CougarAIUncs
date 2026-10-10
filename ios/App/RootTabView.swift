import SwiftUI

/// Placeholder tab shell. The real screens are built in Wave 2 from the
/// approved designs in docs/design/ — do not design here.
struct RootTabView: View {
    var body: some View {
        TabView {
            Text("Home").frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.Colors.ground.ignoresSafeArea()).tabItem { Label("Home", systemImage: "house") }
            Text("Recipes").frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.Colors.ground.ignoresSafeArea()).tabItem { Label("Recipes", systemImage: "fork.knife") }
            Text("Add").frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.Colors.ground.ignoresSafeArea()).tabItem { Label("Add", systemImage: "plus.circle.fill") }
            Text("Fridge / Pantry").frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.Colors.ground.ignoresSafeArea()).tabItem { Label("Fridge", systemImage: "refrigerator") }
            Text("Social").frame(maxWidth: .infinity, maxHeight: .infinity).background(Theme.Colors.ground.ignoresSafeArea()).tabItem { Label("Social", systemImage: "person.2") }
        }
        .tint(Theme.Colors.forest)
    }
}
