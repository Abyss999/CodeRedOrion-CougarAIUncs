import SwiftUI
import Observation

/// What the person picked in the remove sheet.
struct RemoveChoice: Equatable, Sendable {
    var outcome: RemoveOutcome
    var wasteReason: WasteReason?
    /// Donated only. The app always sends nil: the server credits the listing's claimer (docs/API.md).
    var recipientId: String?
}

/// Inline error banner (`fridge.remove.error`): a failed remove or undo was rolled back, or a
/// refresh failed while content is on screen.
struct FridgeBanner: Identifiable {
    let id = UUID()
    var message: String
    /// nil hides "Try again" (e.g. the 10-minute restore window has passed).
    var retry: (() -> Void)?
}

/// State for the Fridge tab: items per storage, grouped by food group, plus optimistic removal
/// with Undo and rollback. Views animate through `withMotion`, so Reduce Motion is honoured.
@MainActor
@Observable
final class FridgeModel {
    enum ScreenState {
        case loading
        case error(Error)
        case empty
        case content([ItemSection])
    }

    private struct Location {
        let storage: Storage
        let group: FoodGroup
        let index: Int
    }

    var storage: Storage = .fridge
    var toast: UndoToastItem?
    /// The Undo toast for a removal made from the sheet, held until the sheet has dismissed so the
    /// full 5 s window is visible (`showPendingToast()`). The removal itself is not delayed.
    private var pendingToast: UndoToastItem?
    var banner: FridgeBanner?
    let stagger = StaggerController()
    /// DEBUG probe `debug.stagger.count`: staggers run on a storage's first load only.
    private(set) var staggerRestarts = 0

    private(set) var sections: [Storage: [ItemSection]] = [:]
    private var errors: [Storage: Error] = [:]
    private var everLoaded: Set<Storage> = []
    /// Removals in flight, keyed by item id. The value says whether the server accepted it.
    private var pendingRemovals: [String: Task<Bool, Never>] = [:]
    /// Ids removed locally and not undone, so a refresh racing a removal doesn't bring them back.
    private var locallyRemoved: Set<String> = []
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    func state(for storage: Storage) -> ScreenState {
        if let secs = sections[storage] { return secs.isEmpty ? .empty : .content(secs) }
        if let e = errors[storage] { return .error(e) }
        return .loading
    }

    // MARK: Loading

    /// Loads `storage` if it has never loaded (first appearance of that segment).
    func loadIfNeeded(_ storage: Storage) async {
        guard sections[storage] == nil, errors[storage] == nil else { return }
        await load(storage, isRefresh: false)
    }

    /// Retry from the error state: back to the skeleton, then load.
    func retry(_ storage: Storage) async {
        errors[storage] = nil
        await load(storage, isRefresh: false)
    }

    func refresh() async { await load(storage, isRefresh: true) }

    private func load(_ storage: Storage, isRefresh: Bool) async {
        do {
            let listing = try await api.listItems(storage: storage, groupBy: .foodGroup)
            let fresh = Self.grouped(listing).compactMap { section -> ItemSection? in
                var s = section
                s.items.removeAll { locallyRemoved.contains($0.id) }
                return s.items.isEmpty ? nil : s
            }
            let isFirst = !everLoaded.contains(storage)
            everLoaded.insert(storage)
            // Stagger only on a storage's first load, never on refresh. Restart before the rows exist.
            if isFirst && !fresh.isEmpty {
                stagger.restart()
                staggerRestarts += 1
            }
            sections[storage] = fresh
            errors[storage] = nil
        } catch is CancellationError {
            return
        } catch {
            if (error as? URLError)?.code == .cancelled { return }
            if sections[storage] == nil {
                errors[storage] = error
            } else if isRefresh {
                banner = FridgeBanner(message: "Couldn't refresh. \(error.localizedDescription)") { [weak self] in
                    guard let self else { return }
                    Task { await self.refresh() }
                }
            }
        }
    }

    private static func grouped(_ listing: ItemListing) -> [ItemSection] {
        switch listing {
        case .grouped(let sections): return sections.filter { !$0.items.isEmpty }
        case .flat(let items):
            return FoodGroup.allCases.compactMap { g in
                let inGroup = items.filter { $0.foodGroup == g }
                return inGroup.isEmpty ? nil : ItemSection(foodGroup: g, items: inGroup)
            }
        }
    }

    // MARK: Removal

    /// Optimistic removal: the row goes now, the toast offers Undo for 5 s, and the request runs in
    /// the background. A failure puts the row back and shows the banner.
    func remove(_ item: Item, choice: RemoveChoice, reduceMotion: Bool) {
        guard let location = location(of: item.id) else { return }
        banner = nil
        locallyRemoved.insert(item.id)
        withMotion(Theme.Motion.standard, reduceMotion: reduceMotion) { delete(item.id) }
        pendingToast = UndoToastItem(message: "\(item.name) removed") { [weak self] in
            self?.undo(item, location: location, reduceMotion: reduceMotion)
        }
        let api = self.api
        pendingRemovals[item.id] = Task { [weak self] in
            do {
                _ = try await api.removeItem(id: item.id, outcome: choice.outcome,
                                             wasteReason: choice.wasteReason, recipientId: choice.recipientId)
                return true
            } catch {
                self?.removeFailed(item, location: location, choice: choice, error: error, reduceMotion: reduceMotion)
                return false
            }
        }
    }

    /// Called once the remove sheet has finished dismissing: the toast (and its countdown) starts now.
    func showPendingToast() {
        guard let pending = pendingToast else { return }
        pendingToast = nil
        toast = pending
    }

    private func removeFailed(_ item: Item, location: Location, choice: RemoveChoice, error: Error, reduceMotion: Bool) {
        let undone = !locallyRemoved.contains(item.id)
        locallyRemoved.remove(item.id)
        withMotion(Theme.Motion.standard, reduceMotion: reduceMotion) { insert(item, at: location) }
        if pendingToast?.message == "\(item.name) removed" { pendingToast = nil }
        if toast?.message == "\(item.name) removed" { toast = nil }
        guard !undone else { return }   // already back via Undo; nothing to report
        Haptics.error()
        showBanner("Couldn't remove \(item.name). It's back in your list.") { [weak self] in
            guard let self, let current = self.item(id: item.id) else { return }
            self.remove(current, choice: choice, reduceMotion: reduceMotion)
        }
    }

    /// Undo: the row comes back now; restore runs after the removal settles. A failed restore
    /// removes the row again and shows the banner.
    private func undo(_ item: Item, location: Location, reduceMotion: Bool) {
        locallyRemoved.remove(item.id)
        banner = nil
        withMotion(Theme.Motion.standard, reduceMotion: reduceMotion) { insert(item, at: location) }
        let pending = pendingRemovals.removeValue(forKey: item.id)
        let api = self.api
        Task { [weak self] in
            // If the removal never reached the server, there is nothing to restore.
            if let pending, await pending.value == false { return }
            do {
                let restored = try await api.restoreItem(id: item.id)
                self?.replace(restored)
            } catch {
                self?.restoreFailed(item, location: location, error: error, reduceMotion: reduceMotion)
            }
        }
    }

    private func restoreFailed(_ item: Item, location: Location, error: Error, reduceMotion: Bool) {
        // 409 not_removed: the item is already active, so the restored row is right. No banner.
        if (error as? APIError) == .notRemoved { return }
        locallyRemoved.insert(item.id)
        withMotion(Theme.Motion.standard, reduceMotion: reduceMotion) { delete(item.id) }
        Haptics.error()
        let expired = (error as? APIError) == .restoreWindowExpired
        showBanner(expired ? "It's too late to undo. \(item.name) stays removed."
                           : "Couldn't undo. \(item.name) is still removed.",
                   retry: expired ? nil : { [weak self] in
                       self?.undo(item, location: location, reduceMotion: reduceMotion)
                   })
    }

    private func showBanner(_ message: String, retry: (() -> Void)?) {
        banner = FridgeBanner(message: message, retry: retry)
        AccessibilityNotification.Announcement(message).post()
    }

    // MARK: List editing

    private func item(id: String) -> Item? {
        sections.values.lazy.flatMap { $0 }.flatMap(\.items).first { $0.id == id }
    }

    private func location(of id: String) -> Location? {
        for (storage, secs) in sections {
            for s in secs {
                if let i = s.items.firstIndex(where: { $0.id == id }) {
                    return Location(storage: storage, group: s.foodGroup, index: i)
                }
            }
        }
        return nil
    }

    private func delete(_ id: String) {
        for (storage, secs) in sections {
            let updated = secs.compactMap { s -> ItemSection? in
                var s = s
                s.items.removeAll { $0.id == id }
                return s.items.isEmpty ? nil : s
            }
            if updated != secs { sections[storage] = updated }
        }
    }

    /// Idempotent: does nothing if the item is already listed.
    private func insert(_ item: Item, at location: Location) {
        guard self.item(id: item.id) == nil, var secs = sections[location.storage] else { return }
        if let si = secs.firstIndex(where: { $0.foodGroup == location.group }) {
            secs[si].items.insert(item, at: min(location.index, secs[si].items.count))
        } else {
            secs.append(ItemSection(foodGroup: location.group, items: [item]))
            let order = FoodGroup.allCases
            secs.sort { (order.firstIndex(of: $0.foodGroup) ?? 0) < (order.firstIndex(of: $1.foodGroup) ?? 0) }
        }
        sections[location.storage] = secs
    }

    private func replace(_ item: Item) {
        guard let loc = location(of: item.id), var secs = sections[loc.storage],
              let si = secs.firstIndex(where: { $0.foodGroup == loc.group }) else { return }
        secs[si].items[loc.index] = item
        sections[loc.storage] = secs
    }
}

/// Text shared by the Fridge row and the remove sheets.
enum ItemText {
    /// "1.4 lb", "5 oz", or just "8" for pieces.
    static func quantity(_ item: Item) -> String {
        let n = item.quantity.formatted(.number.precision(.fractionLength(0...1)))
        return item.unit == "piece" ? n : "\(n) \(item.unit)"
    }

    /// Row meta line. Spoiled items say so in words (the badge says "Check").
    static func meta(_ item: Item) -> String {
        if item.freshness == .spoiled { return "Photo check: looks spoiled" }
        var parts = [quantity(item)]
        if item.freshness == .semiFresh { parts.append("photo check: ripe") }
        else if let added = item.addedAt { parts.append("added \(added.formatted(.dateTime.month(.abbreviated).day()))") }
        return parts.joined(separator: " · ")
    }

    /// Lower-case expiry phrase for the sheet header, e.g. "expires tomorrow".
    static func expiryPhrase(_ item: Item) -> String? {
        guard let badge = ExpiryBadgeModel.make(for: item) else { return nil }
        switch badge.text {
        case "Check": return "looks spoiled"
        case "Use soon": return "use soon"
        case "Expired": return "expired"
        case "Today": return "expires today"
        case "1 day": return "expires tomorrow"
        default: return "expires in \(badge.text)"
        }
    }

    static func hasOpenListing(_ item: Item) -> Bool { item.share?.status == .open }

    /// "Veggies · 5 oz · expires tomorrow · on Share"
    static func sheetMeta(_ item: Item) -> String {
        var parts = [item.foodGroup.displayName, quantity(item)]
        if let e = expiryPhrase(item) { parts.append(e) }
        if hasOpenListing(item) { parts.append("on Share") }
        return parts.joined(separator: " · ")
    }
}
