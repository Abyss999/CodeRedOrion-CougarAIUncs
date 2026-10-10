import SwiftUI

/// Placeholder tab shell. The real screens are built in Wave 2 from the
/// approved designs in docs/design/ — do not design here.
struct RootTabView: View {
    var body: some View {
        TabView {
            Text("Home").tabItem { Label("Home", systemImage: "house") }
            Text("Recipes").tabItem { Label("Recipes", systemImage: "fork.knife") }
            Text("Add").tabItem { Label("Add", systemImage: "plus.circle.fill") }
            Text("Fridge / Pantry").tabItem { Label("Fridge", systemImage: "refrigerator") }
            Text("Social").tabItem { Label("Social", systemImage: "person.2") }
        }
        .tint(Theme.Colors.primaryDeep)
    }
}
