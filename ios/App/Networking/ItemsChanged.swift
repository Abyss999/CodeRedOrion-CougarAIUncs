import Foundation

extension Notification.Name {
    /// Posted after items were created or changed outside a list's own screen (the Add flow), so the Fridge reloads.
    static let itemsDidChange = Notification.Name("bitedown.itemsDidChange")
}
