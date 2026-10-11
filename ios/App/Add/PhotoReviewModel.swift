import SwiftUI
import Observation

enum SpoiledDecision: Equatable { case toss, keep }

/// One detected item under review.
struct ReviewRow: Identifiable, Equatable {
    let id = UUID()
    var candidate: Candidate
    var isOn = true
    var amount: Double
    var unit: String
    var isEditing = false
    var decision: SpoiledDecision?

    init(candidate: Candidate) {
        self.candidate = candidate
        amount = candidate.quantity ?? 1
        unit = candidate.unit ?? "piece"
    }

    var isSpoiled: Bool { candidate.freshness == .spoiled }

    var content: DetectedRowContent {
        DetectedRowContent(name: candidate.name, rawLine: nil, meta: candidate.foodGroup.displayName,
                           badge: DetectedBadge.make(expiry: candidate.predictedExpiry, freshness: candidate.freshness,
                                                     confidence: candidate.confidence))
    }
}

/// A "Toss" whose remove call failed: the item stays in the fridge as "Looks off".
struct TossFailure: Identifiable, Equatable {
    let id: String   // item id
    let name: String
}

/// State and the confirm step for PhotoReview. Candidates are not saved until `confirm`.
@MainActor
@Observable
final class PhotoReviewModel {
    enum Phase: Equatable {
        case reviewing
        case saving
        /// Created. `tossFailures` is non-empty when some tosses failed (banners with retry).
        case done(added: Int)
    }

    private(set) var rows: [ReviewRow]
    private(set) var phase: Phase = .reviewing
    /// Shown above the confirm button when creating failed.
    private(set) var addError: String?
    private(set) var tossFailures: [TossFailure] = []
    let mode: PhotoMode
    private let api: APIClient

    init(candidates: [Candidate], mode: PhotoMode, api: APIClient) {
        rows = candidates.map(ReviewRow.init)
        self.mode = mode
        self.api = api
    }

    // MARK: Derived

    var foundIndices: [Int] { rows.indices.filter { !rows[$0].isSpoiled } }
    var spoiledIndices: [Int] { rows.indices.filter { rows[$0].isSpoiled } }
    var undecidedCount: Int { spoiledIndices.filter { rows[$0].decision == nil }.count }
    var tossCount: Int { rows.filter { $0.isSpoiled && $0.decision == .toss }.count }
    /// Items that stay: ticked found items plus spoiled ones kept.
    var addCount: Int {
        rows.filter { $0.isSpoiled ? $0.decision == .keep : $0.isOn }.count
    }
    var canConfirm: Bool { phase == .reviewing && undecidedCount == 0 && (addCount + tossCount) > 0 }
    var title: String { rows.count == 1 ? "We found 1 item" : "We found \(rows.count) items" }

    // MARK: Edits

    func setOn(_ on: Bool, at i: Int) { rows[i].isOn = on }
    func setAmount(_ v: Double, at i: Int) { rows[i].amount = v }
    func setUnit(_ u: String, at i: Int) { rows[i].unit = u }
    func setEditing(_ e: Bool, at i: Int) { rows[i].isEditing = e }
    func decide(_ d: SpoiledDecision, at i: Int) { rows[i].decision = d; Haptics.selection() }

    // MARK: Confirm

    private func newItem(for row: ReviewRow) -> NewItem {
        var n = NewItem(candidate: row.candidate, source: mode == .fridge ? "photo" : "single_photo")
        n.quantity = row.amount
        n.unit = row.unit
        return n
    }

    /// Creates the items; tossed ones are then removed as `thrown_out` (counts as waste). If a remove fails the
    /// item stays in the fridge (freshness spoiled, "Looks off") and a banner explains.
    func confirm() async {
        guard canConfirm else { return }
        let included = rows.filter { $0.isSpoiled ? $0.decision != nil : $0.isOn }
        phase = .saving
        addError = nil
        let created: [Item]
        do {
            created = try await api.createItems(included.map(newItem(for:)))
        } catch {
            phase = .reviewing
            addError = (error as? LocalizedError)?.errorDescription ?? "Couldn't add those items."
            Haptics.error()
            return
        }
        NotificationCenter.default.post(name: .itemsDidChange, object: nil)
        var failures: [TossFailure] = []
        for (row, item) in zip(included, created) where row.isSpoiled && row.decision == .toss {
            do {
                _ = try await api.removeItem(id: item.id, outcome: .thrownOut, wasteReason: .expired)
            } catch {
                failures.append(TossFailure(id: item.id, name: row.candidate.name))
            }
        }
        tossFailures = failures
        failures.isEmpty ? Haptics.success() : Haptics.error()
        NotificationCenter.default.post(name: .itemsDidChange, object: nil)
        phase = .done(added: addCount)
    }

    /// "Try again" on a toss banner.
    func retryToss(_ failure: TossFailure) async {
        do {
            _ = try await api.removeItem(id: failure.id, outcome: .thrownOut, wasteReason: .expired)
            tossFailures.removeAll { $0.id == failure.id }
            Haptics.success()
            NotificationCenter.default.post(name: .itemsDidChange, object: nil)
        } catch {
            Haptics.error()
        }
    }

    func dismissToss(_ failure: TossFailure) { tossFailures.removeAll { $0.id == failure.id } }
}
