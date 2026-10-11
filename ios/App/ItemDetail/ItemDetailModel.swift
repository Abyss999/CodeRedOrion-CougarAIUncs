import SwiftUI
import Observation
import UIKit

/// State for Item detail / ItemShared: editable fields (saved with `PATCH /items/:id`), the freshness
/// re-check, the share switch and the pickup spot.
@MainActor
@Observable
final class ItemDetailModel {
    struct Notice: Equatable {
        var style: BannerStyle
        var message: String
    }

    var api: APIClient?
    private(set) var item: Item

    // Editable drafts
    var name: String
    var quantityText: String
    var unit: String
    var storage: Storage
    var foodGroup: FoodGroup
    var expiry: Date?

    var notice: Notice?
    private(set) var isSaving = false
    private(set) var isChecking = false
    private(set) var isSharing = false
    /// A pickup spot chosen before the item is shared; sent with `POST /share`.
    private(set) var pendingPickup: Pickup?
    /// True once something was saved, so the Fridge refreshes when the screen goes away.
    private(set) var didChange = false

    // Audience sheet
    private(set) var groups: [SharingGroup] = []
    private(set) var groupsError: Error?
    private(set) var groupsLoading = false

    init(item: Item) {
        self.item = item
        name = item.name
        quantityText = Self.format(item.quantity)
        unit = item.unit
        storage = item.storage
        foodGroup = item.foodGroup
        expiry = item.predictedExpiry
    }

    // MARK: Derived

    /// The open listing, if any (cancelled / fulfilled listings don't count).
    var share: ItemShare? { item.share?.status == .open ? item.share : nil }
    var isShared: Bool { share != nil }
    var claimer: ItemShare.Claimant? { share?.claimedBy }
    var pickup: Pickup? { isShared ? share?.pickup : pendingPickup }
    var audienceSummary: String { share?.audience?.summary ?? "Friends" }

    private var parsedQuantity: Double? {
        Double(quantityText.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: "."))
    }

    var isDirty: Bool { !patch().isEmpty }

    static func format(_ q: Double) -> String { q.formatted(.number.precision(.fractionLength(0...2)).grouping(.never)) }

    private func patch() -> ItemPatch {
        var p = ItemPatch()
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty, trimmed != item.name { p.name = trimmed }
        if let q = parsedQuantity, q > 0, q != item.quantity { p.quantity = q }
        let u = unit.trimmingCharacters(in: .whitespacesAndNewlines)
        if !u.isEmpty, u != item.unit { p.unit = u }
        if storage != item.storage { p.storage = storage }
        if foodGroup != item.foodGroup { p.foodGroup = foodGroup }
        if let expiry, !Self.sameDay(expiry, item.predictedExpiry) { p.predictedExpiry = APIDate.dayString(expiry) }
        return p
    }

    private static func sameDay(_ a: Date, _ b: Date?) -> Bool {
        guard let b else { return false }
        return Calendar.current.isDate(a, inSameDayAs: b)
    }

    // MARK: Save

    /// Returns true when saved (or there was nothing to save).
    func save() async -> Bool {
        guard let api, !isSaving else { return false }
        if name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            notice = Notice(style: .error, message: "Give this item a name.")
            return false
        }
        guard let q = parsedQuantity, q > 0 else {
            notice = Notice(style: .error, message: "Enter an amount above zero.")
            return false
        }
        _ = q
        let p = patch()
        if p.isEmpty { return true }
        isSaving = true
        notice = nil
        defer { isSaving = false }
        do {
            let updated = try await api.patchItem(id: item.id, p)
            apply(updated)
            Haptics.success()
            return true
        } catch {
            Haptics.error()
            notice = Notice(style: .error, message: "Couldn't save. \(error.localizedDescription)")
            return false
        }
    }

    /// Takes the server's copy, keeping the listing the PATCH response may not carry.
    private func apply(_ updated: Item) {
        var next = updated
        if next.share == nil { next.share = item.share }
        item = next
        didChange = true
        name = next.name
        quantityText = Self.format(next.quantity)
        unit = next.unit
        storage = next.storage
        foodGroup = next.foodGroup
        expiry = next.predictedExpiry
    }

    // MARK: Check again

    /// Photo → the existing from-photo detect path (single item), then PATCH only `freshness`
    /// (the server sets `freshness_checked_at`; `confidence` isn't editable). Nothing is stored.
    func checkAgain(imageData: Data) async {
        guard let api, !isChecking else { return }
        isChecking = true
        notice = nil
        defer { isChecking = false }
        do {
            let jpeg = await Task.detached(priority: .userInitiated) { Self.downscaled(imageData) }.value
            let response = try await api.fromPhoto(imageData: jpeg, mode: .single)
            guard let freshness = response.candidates.first?.freshness else {
                notice = Notice(style: .warning, message: "Couldn't tell from that photo. Try a closer, brighter shot.")
                return
            }
            let updated = try await api.patchItem(id: item.id, ItemPatch(freshness: freshness))
            var next = item
            next.freshness = updated.freshness
            next.freshnessCheckedAt = updated.freshnessCheckedAt
            item = next
            didChange = true
            Haptics.success()
            notice = Notice(style: .success, message: "Checked just now: \(Self.freshnessLabel(freshness)).")
        } catch {
            Haptics.error()
            notice = Notice(style: .error, message: "Couldn't check this item. \(error.localizedDescription)")
        }
    }

    nonisolated static func downscaled(_ data: Data, maxSide: CGFloat = 1600) -> Data {
        guard let image = UIImage(data: data) else { return data }
        let longest = max(image.size.width, image.size.height)
        let scale = min(1, maxSide / max(longest, 1))
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let rendered = UIGraphicsImageRenderer(size: size, format: format).jpegData(withCompressionQuality: 0.8) { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        return rendered
    }

    static func freshnessLabel(_ f: Freshness) -> String {
        switch f {
        case .fresh: "Fresh"
        case .semiFresh: "Use soon"
        case .spoiled: "Looks off"
        }
    }

    // MARK: Share

    func loadGroups() async {
        guard let api else { return }
        groupsLoading = true
        groupsError = nil
        defer { groupsLoading = false }
        do { groups = try await api.listGroups() }
        catch { groupsError = error }
    }

    func startSharing(audience: ShareAudience) async -> Bool {
        guard let api, !isSharing else { return false }
        isSharing = true
        notice = nil
        defer { isSharing = false }
        do {
            let listing = try await api.share(itemId: item.id, audience: audience, pickup: pendingPickup)
            var next = item
            next.share = ItemShare(id: listing.id, status: .open, claimedBy: nil,
                                   audience: listing.audience ?? audience.listingAudience,
                                   pickup: listing.pickup ?? pendingPickup)
            item = next
            pendingPickup = nil
            didChange = true
            Haptics.success()
            return true
        } catch {
            Haptics.error()
            notice = Notice(style: .error, message: shareMessage(error, verb: "share"))
            return false
        }
    }

    func stopSharing() async {
        guard let api, let share, !isSharing else { return }
        isSharing = true
        notice = nil
        defer { isSharing = false }
        do {
            _ = try await api.cancelShare(id: share.id)
            var next = item
            // Keep the spot for the next time it is shared.
            pendingPickup = share.pickup
            next.share = nil
            item = next
            didChange = true
        } catch {
            Haptics.error()
            notice = Notice(style: .error, message: shareMessage(error, verb: "stop sharing"))
        }
    }

    private func shareMessage(_ error: Error, verb: String) -> String {
        if case APIError.server(_, let code, _) = error {
            if code == "already_shared" { return "This item is already shared." }
            if code == "listing_closed" { return "That listing was already closed. Pull to refresh." }
        }
        return "Couldn't \(verb). \(error.localizedDescription)"
    }

    // MARK: Pickup

    /// Open listing: `PATCH /share/:id`. Not shared yet: held and sent with `POST /share`.
    /// Throws so the editor can show the error and stay open.
    func savePickup(_ pickup: Pickup?) async throws {
        if let share {
            guard let api else { return }
            let listing = try await api.updatePickup(listingId: share.id, pickup: pickup)
            var next = item
            next.share?.pickup = listing.pickup ?? pickup
            item = next
            didChange = true
        } else {
            pendingPickup = pickup
        }
    }
}

extension ItemPatch {
    var isEmpty: Bool {
        name == nil && quantity == nil && unit == nil && storage == nil && category == nil && foodGroup == nil
            && predictedExpiry == nil && estPrice == nil && estWeightKg == nil && freshness == nil && !clearFreshness
    }
}
