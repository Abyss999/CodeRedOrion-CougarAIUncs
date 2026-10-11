import SwiftUI
import UIKit

/// SwiftUI's `.accessibilityIdentifier` on tab items reaches the UITabBar buttons only
/// intermittently on iOS 26 (IOS-4). This installs the same identifiers directly on the
/// underlying `UITabBarItem`s, and re-applies them on a short schedule and whenever SwiftUI
/// re-lays the bar out. Order must match the `TabView` order.
///
/// It also sets each item's `accessibilityLabel` to the tab title (IOS-10): SwiftUI's
/// `.accessibilityHidden` on the tab image doesn't reach UIKit, so VoiceOver otherwise reads the
/// SF Symbol's name ("house", "add") alongside the title.
struct TabBarIdentifiers: UIViewRepresentable {
    struct Entry: Equatable {
        let id: String
        let label: String
    }
    let entries: [Entry]

    func makeUIView(context: Context) -> InstallerView { InstallerView(entries: entries) }
    func updateUIView(_ uiView: InstallerView, context: Context) { uiView.entries = entries; uiView.apply() }

    final class InstallerView: UIView {
        var entries: [Entry]
        private var tries = 0

        init(entries: [Entry]) {
            self.entries = entries
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
            for (item, entry) in zip(bar.tabBar.items ?? [], entries) {
                if item.accessibilityIdentifier != entry.id { item.accessibilityIdentifier = entry.id }
                if item.accessibilityLabel != entry.label { item.accessibilityLabel = entry.label }
                // Drop the symbol's own description so it can't be read as part of the button.
                if let image = item.image, image.accessibilityLabel != nil { image.accessibilityLabel = nil }
                if let image = item.selectedImage, image.accessibilityLabel != nil { image.accessibilityLabel = nil }
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
