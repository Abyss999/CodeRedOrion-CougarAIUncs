import Foundation
import Observation

/// A named pickup spot kept on this device ("Home", "Lab"). Never sent to the server on its own;
/// choosing one just fills the editor.
struct SavedPickupSpot: Codable, Hashable, Sendable, Identifiable {
    var id: String
    var name: String
    var pickup: Pickup

    /// Second line of the saved row: the place name, else the note.
    var detail: String { pickup.placeName?.isEmpty == false ? pickup.placeName! : (pickup.trimmedNote ?? "Dropped pin") }

    var systemImage: String {
        switch name.lowercased() {
        case "home": "house"
        case "lab", "work": "flask"
        default: "mappin.and.ellipse"
        }
    }
}

/// Saved spots in `UserDefaults` (owner ruling: on the device, not on the server).
@MainActor
@Observable
final class SavedPickupSpotsStore {
    static let key = "pickup.savedSpots"
    static let shared = SavedPickupSpotsStore()

    private(set) var spots: [SavedPickupSpot]
    @ObservationIgnored private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
        if let data = defaults.data(forKey: Self.key),
           let decoded = try? JSONDecoder().decode([SavedPickupSpot].self, from: data) {
            spots = decoded
        } else {
            spots = []
        }
    }

    /// Adds a spot, or replaces the one with the same name (case-insensitive).
    func add(name: String, pickup: Pickup) {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, pickup.isValid else { return }
        if let i = spots.firstIndex(where: { $0.name.caseInsensitiveCompare(trimmed) == .orderedSame }) {
            spots[i].pickup = pickup
            spots[i].name = trimmed
        } else {
            spots.append(SavedPickupSpot(id: UUID().uuidString, name: trimmed, pickup: pickup))
        }
        persist()
    }

    func remove(id: String) {
        spots.removeAll { $0.id == id }
        persist()
    }

    private func persist() {
        if let data = try? JSONEncoder().encode(spots) { defaults.set(data, forKey: Self.key) }
    }
}
