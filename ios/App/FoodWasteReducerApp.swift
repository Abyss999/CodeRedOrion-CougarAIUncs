import SwiftUI

@main
struct FoodWasteReducerApp: App {
    @State private var env = AppEnvironment.make()

    init() { GoogleSignInConfig.configure() }

    var body: some Scene {
        WindowGroup {
            AuthGate()
                // Inside .environment(env): the friend-link modifier reads AppEnvironment.
                .handlesFriendLinks()
                .environment(env)
                .environment(\.reduceMotionOverride, env.launch.reduceMotion ? true : nil)
                .environment(\.undoWindowOverride, env.launch.undoWindow)
                .onOpenURL { GoogleSignInConfig.handleOpenURL($0) }
        }
    }
}
