import SwiftUI

enum AppTab: Hashable {
    case home, recipes, add, fridge, social

    var title: String {
        switch self {
        case .home: "Home"
        case .recipes: "Recipes"
        case .add: "Add"
        case .fridge: "Fridge"
        case .social: "Social"
        }
    }

    var symbol: String {
        switch self {
        case .home: "house"
        case .recipes: "frying.pan"
        case .add: "plus.circle.fill"
        case .fridge: "refrigerator"
        case .social: "person.2"
        }
    }

    var accessibilityID: String {
        switch self {
        case .home: AccessibilityID.Tab.home
        case .recipes: AccessibilityID.Tab.recipes
        case .add: AccessibilityID.Tab.add
        case .fridge: AccessibilityID.Tab.fridge
        case .social: AccessibilityID.Tab.social
        }
    }
}

/// Placeholder tab shell (screens come later from docs/design/). Uses the system `TabView`
/// (Liquid Glass on iOS 26). **Add is a tab that presents a sheet and leaves the selection
/// unchanged**: selecting it shows `AddSheetView` and `selection` never becomes `.add`.
struct RootTabView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var selection: AppTab = .home
    @State private var showAdd = false
    private let tabOrder: [AppTab] = [.home, .recipes, .add, .fridge, .social]

    var body: some View {
        TabView(selection: tabSelection) {
            tab(.home) { HomeView() }
            tab(.recipes) { RecipesView() }
            tab(.add) { Color.clear }  // never shown: selecting Add presents `AddSheetView`
            tab(.fridge) { FridgeView(api: env.api) }
            tab(.social) { SocialView() }
        }
        .tint(Theme.Colors.forest)
        .background(TabBarIdentifiers(entries: tabOrder.map { .init(id: $0.accessibilityID, label: $0.title) }))
        .sheet(isPresented: $showAdd) { AddSheetView() }
    }

    /// Selecting Add presents the sheet and never writes `.add` to `selection`, so the bar keeps
    /// the previous tab highlighted (a `.add` -> previous round-trip in `onChange` can leave the
    /// UIKit bar showing Add as selected).
    private var tabSelection: Binding<AppTab> {
        Binding(
            get: { selection },
            set: { new in
                if new == .add {
                    showAdd = true
                } else {
                    selection = new
                }
            }
        )
    }

    /// The identifier sits on the tab's label content (not on the `Tab`), and the label's
    /// accessibility label is the title alone. Neither reliably reaches the UIKit bar, so
    /// `TabBarIdentifiers` also sets both on each `UITabBarItem` (IOS-4, IOS-10).
    private func tab<Content: View>(_ t: AppTab, @ViewBuilder content: @escaping () -> Content) -> some TabContent<AppTab> {
        Tab(value: t) {
            content()
        } label: {
            Label {
                Text(t.title)
            } icon: {
                Image(systemName: t.symbol).accessibilityHidden(true)
            }
            .accessibilityLabel(Text(t.title))
            .accessibilityIdentifier(t.accessibilityID)
        }
    }
}
