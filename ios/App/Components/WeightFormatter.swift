import SwiftUI

/// The Units preference (Settings). Stored on the device only; the API always speaks kilograms.
enum UnitSystem: String, CaseIterable, Sendable, Identifiable {
    /// lb / oz (the default).
    case us
    /// kg / g.
    case metric

    var id: String { rawValue }
    var displayName: String { self == .us ? "US (lb, oz)" : "Metric (kg, g)" }

    /// `@AppStorage` key. Settings and `WeightText` read the same key.
    static let storageKey = "units"
    static let `default`: UnitSystem = .us

    /// Reads the stored preference (US when unset or unreadable).
    static func stored(in defaults: UserDefaults = .standard) -> UnitSystem {
        defaults.string(forKey: storageKey).flatMap(UnitSystem.init(rawValue:)) ?? .default
    }
}

/// Converts kilograms from the API to a short display string.
/// US: under 1 lb shows whole ounces ("5 oz"), else pounds to one decimal ("1.4 lb").
/// Metric: under 1 kg shows whole grams ("250 g"), else kilograms to one decimal ("1.2 kg").
struct WeightFormatter: Sendable {
    var system: UnitSystem

    static let ouncesPerKg = 35.27396195
    static let poundsPerKg = 2.20462262

    init(system: UnitSystem = .stored()) { self.system = system }

    func string(kg: Double) -> String {
        let kg = max(kg, 0)
        switch system {
        case .us:
            let oz = kg * Self.ouncesPerKg
            if oz < 0.5 { return kg == 0 ? "0 oz" : "<1 oz" }
            if oz < 15.5 { return "\(Int(oz.rounded())) oz" }
            return "\(Self.trimmed(kg * Self.poundsPerKg)) lb"
        case .metric:
            let g = kg * 1000
            if g < 0.5 { return kg == 0 ? "0 g" : "<1 g" }
            if g < 999.5 { return "\(Int(g.rounded())) g" }
            return "\(Self.trimmed(kg)) kg"
        }
    }

    /// Spelled-out form for VoiceOver ("1.4 pounds").
    func spoken(kg: Double) -> String {
        let s = string(kg: kg)
        if s.hasPrefix("<1 ") {
            return s.hasSuffix(" oz") ? "less than 1 ounce" : "less than 1 gram"
        }
        let words = ["oz": "ounces", "lb": "pounds", "kg": "kilograms", "g": "grams"]
        let parts = s.split(separator: " ")
        guard parts.count == 2, let word = words[String(parts[1])] else { return s }
        return parts[0] == "1" ? "1 \(word.dropLast())" : "\(parts[0]) \(word)"
    }

    private static func trimmed(_ v: Double) -> String {
        let r = (v * 10).rounded() / 10
        return r == r.rounded() ? String(Int(r)) : String(format: "%.1f", r)
    }
}

/// A weight label that follows the Units preference live. `WeightText(kg: item.estWeightKg ?? 0)`.
struct WeightText: View {
    let kg: Double
    @AppStorage(UnitSystem.storageKey) private var units: UnitSystem = .us

    var body: some View {
        let f = WeightFormatter(system: units)
        Text(f.string(kg: kg))
            .accessibilityLabel(f.spoken(kg: kg))
    }
}
