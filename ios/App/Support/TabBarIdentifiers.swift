import SwiftUI
import UIKit

/// SwiftUI's `.accessibilityIdentifier` on tab items reaches the UITabBar buttons only
/// intermittently on iOS 26 (IOS-4). This installs the same identifiers directly on the
/// underlying `UITabBarItem`s, and re-applies them on a short schedule and whenever SwiftUI
/// re-lays the bar out. Order must match the `TabView` order.
struct TabBarIdentifiers: UIViewRepresentable {
    let ids: [String]

    func makeUIView(context: Context) -> InstallerView { InstallerView(ids: ids) }
    func updateUIView(_ uiView: InstallerView, context: Context) { uiView.ids = ids; uiView.apply() }

    final class InstallerView: UIView {
        var ids: [String]
        private var tries = 0

        init(ids: [String]) {
            self.ids = ids
            super.init(frame: .zero)
            isUserInteractionEnabled = false
            isAccessibilityElement = false
        }
        required init?(coder: NSCoder) { fatalError() }

        override func didMoveToWindow() {
            super.didMoveToWindow()
            tries = 0
            schedule()
        }

        private func schedule() {
            apply()
            tries += 1
            guard tries < 20 else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { [weak self] in self?.schedule() }
        }

        func apply() {
            guard let root = window?.rootViewController, let bar = Self.findTabBar(root) else { return }
            for (item, id) in zip(bar.tabBar.items ?? [], ids) where item.accessibilityIdentifier != id {
                item.accessibilityIdentifier = id
            }
        }

        private static func findTabBar(_ vc: UIViewController) -> UITabBarController? {
            if let t = vc as? UITabBarController { return t }
            for child in vc.children { if let t = findTabBar(child) { return t } }
            if let p = vc.presentedViewController { return findTabBar(p) }
            return nil
        }
    }
}
