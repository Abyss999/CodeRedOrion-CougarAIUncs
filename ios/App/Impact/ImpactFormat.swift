import Foundation

/// Client-side presentation maths for Impact: deltas against `previous`, the driving equivalent for
/// carbon emissions, and the short strings the screen shows. Pure, so unit tests can pin them.
enum ImpactFormat {
    /// EPA average passenger car: about 404 g of CO2e per mile.
    static let kgCO2ePerMile = 0.404
    static let kmPerMile = 1.609344
    static let poundsPerKg = WeightFormatter.poundsPerKg

    // MARK: Ranges

    static func title(_ range: ImpactRange) -> String {
        switch range {
        case .week: "Week"
        case .month: "Month"
        case .all: "All"
        }
    }

    /// "previous 30 days" (month), "previous 7 days" (week); nil for All (the API sends no `previous`).
    static func previousPhrase(_ range: ImpactRange) -> String? {
        switch range {
        case .week: "previous 7 days"
        case .month: "previous 30 days"
        case .all: nil
        }
    }

    /// ("This month", "Last month"), or nil for All.
    static func comparePeriods(_ range: ImpactRange) -> (current: String, previous: String)? {
        switch range {
        case .week: ("This week", "Last week")
        case .month: ("This month", "Last month")
        case .all: nil
        }
    }

    // MARK: Deltas

    enum Direction: Equatable, Sendable { case up, down, same }

    struct Delta: Equatable, Sendable {
        var direction: Direction
        /// "Up 6.2 lb", "Down 4 items", "Same".
        var text: String
        var spoken: String
    }

    static func weightDelta(current: Double, previous: Double, formatter: WeightFormatter) -> Delta {
        let diff = current - previous
        guard abs(diff) >= 0.005, formatter.string(kg: abs(diff)) != (formatter.system == .us ? "0 oz" : "0 g") else {
            return Delta(direction: .same, text: "Same", spoken: "Same")
        }
        let up = diff > 0
        return Delta(direction: up ? .up : .down,
                     text: "\(up ? "Up" : "Down") \(formatter.string(kg: abs(diff)))",
                     spoken: "\(up ? "Up" : "Down") \(formatter.spoken(kg: abs(diff)))")
    }

    static func countDelta(current: Int, previous: Int) -> Delta {
        let diff = current - previous
        guard diff != 0 else { return Delta(direction: .same, text: "Same", spoken: "Same") }
        let n = abs(diff), noun = n == 1 ? "item" : "items"
        let word = diff > 0 ? "Up" : "Down"
        return Delta(direction: diff > 0 ? .up : .down, text: "\(word) \(n) \(noun)", spoken: "\(word) \(n) \(noun)")
    }

    static func moneyDelta(current: Double, previous: Double) -> Delta {
        let diff = ((current - previous) * 100).rounded() / 100
        guard diff != 0 else { return Delta(direction: .same, text: "Same", spoken: "Same") }
        let text = "\(diff > 0 ? "Up" : "Down") \(money(abs(diff)))"
        return Delta(direction: diff > 0 ? .up : .down, text: text, spoken: text)
    }

    // MARK: Numbers

    static func money(_ value: Double) -> String {
        value.formatted(.currency(code: Locale.current.currency?.identifier ?? "USD"))
    }

    /// 0.148 -> "14.8%", 0.25 -> "25%", 0 -> "0%".
    static func percent(_ rate: Double) -> String {
        (rate).formatted(.percent.precision(.fractionLength(0...1)))
    }

    /// Splits "21.2 lb" into ("21.2", "lb") for the hero. "<1 oz" has no plain number.
    static func heroParts(_ formatted: String) -> (number: String, unit: String) {
        let parts = formatted.split(separator: " ", maxSplits: 1).map(String.init)
        return parts.count == 2 ? (parts[0], parts[1]) : (formatted, "")
    }

    // MARK: Carbon emissions in plain words

    /// "41 lb of carbon emissions avoided, about a 46-mile drive" (US) /
    /// "19 kg of carbon emissions avoided, about a 74-km drive" (metric). Never "CO2e".
    static func emissionsLine(co2eKg: Double, system: UnitSystem) -> String {
        let kg = max(co2eKg, 0)
        guard kg >= 0.05 else { return "No carbon emissions avoided yet" }
        let amount: String
        let drive: String
        let miles = max(1, Int((kg / kgCO2ePerMile).rounded()))
        switch system {
        case .us:
            amount = "\(trimmed(kg * poundsPerKg)) lb"
            drive = "about a \(miles)-mile drive"
        case .metric:
            amount = "\(trimmed(kg)) kg"
            drive = "about a \(max(1, Int((Double(miles) * kmPerMile).rounded())))-km drive"
        }
        return "\(amount) of carbon emissions avoided, \(drive)"
    }

    /// Whole numbers from 10 up, else one decimal without a trailing ".0".
    private static func trimmed(_ v: Double) -> String {
        if v >= 10 { return String(Int(v.rounded())) }
        let r = (v * 10).rounded() / 10
        return r == r.rounded() ? String(Int(r)) : String(format: "%.1f", r)
    }

    // MARK: Waste reasons

    static func reasonTitle(_ reason: WasteReason) -> String {
        switch reason {
        case .forgot: "Forgot about it"
        case .expired: "Expired"
        case .didntLike: "Didn't like it"
        case .other: "Other"
        }
    }

    // MARK: Compare widget

    /// Bar fractions for this vs last period (the larger is 1). Both zero -> (0, 0).
    static func compareFractions(current: Double, previous: Double) -> (current: Double, previous: Double) {
        let top = max(current, previous)
        guard top > 0 else { return (0, 0) }
        return (current / top, previous / top)
    }

    /// "Wasted 0.8 lb less than last month" / "more" / "the same as".
    static func compareSentence(current: Double, previous: Double, previousName: String, formatter: WeightFormatter) -> (text: String, direction: Direction) {
        let d = weightDelta(current: current, previous: previous, formatter: formatter)
        let amount = formatter.string(kg: abs(current - previous))
        switch d.direction {
        case .same: return (current == 0 ? "Nothing wasted in either period" : "Wasted the same as \(previousName.lowercased())", .same)
        case .down: return ("Wasted \(amount) less than \(previousName.lowercased())", .down)
        case .up: return ("Wasted \(amount) more than \(previousName.lowercased())", .up)
        }
    }

    // MARK: Weekly chart

    static func weekLabel(_ date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.month, .day], from: date)
        return "\(c.month ?? 0)/\(c.day ?? 0)"
    }
}
