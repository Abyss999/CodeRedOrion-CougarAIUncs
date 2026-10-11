import SwiftUI

@main
struct FoodWasteReducerApp: App {
    @State private var env = AppEnvironment.make()

    var body: some Scene {
        WindowGroup {
            RootTabView()
                .environment(env)
        }
    }
}
