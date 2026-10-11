import SwiftUI

/// What the badge says and how it is styled, derived from an item's expiry and freshness.
/// Uses the local calendar, so "Today" flips at the user's midnight.
struct ExpiryBadgeModel: Equatable {
    enum Style: Equatable { case urgent, useSoon, later }

    /// The single status a row shows (DESIGN_SYSTEM Principle 1). Everything else (text, style,
    /// spoken phrase) is derived from this, never from the display string.
    enum Kind: Equatable {
        /// Photo check found it spoiled.
        case looksOff
        case expired
        case today
        case tomorrow
        case useSoon
        /// A user-entered date `n` days out (n >= 2): exact.
        case exactDays(Int)
        /// An estimated date `days` out (days >= 2): a range ending at the predicted date.
        case estimated(days: Int)
    }

    let kind: Kind

    var text: String {
        switch kind {
        case .looksOff: "Looks off"
        case .expired: "Expired"
        case .today: "Today"
        case .tomorrow: "Tomorrow"
        case .useSoon: "Use soon"
        case .exactDays(let n): "\(n) days"
        case .estimated(let days): Self.rangeText(days: days)
        }
    }

    var style: Style {
        switch kind {
        case .looksOff, .expired, .today, .tomorrow: .urgent
        case .useSoon: .useSoon
        case .exactDays, .estimated: .later
        }
    }

    /// "2–3 days" (2 or 3 days out), "3–4 days" … "6–7 days" (4...7), "1–2 weeks" (8–14), "2–3 weeks" (15–21), "3+ weeks" (22+).
    /// The range ends at the predicted date; the vocabulary starts at "2–3 days".
    static func rangeText(days: Int) -> String {
        switch days {
        case ..<2: "Tomorrow"
        case 2...3: "2–3 days"
        case 4...7: "\(days - 1)–\(days) days"
        case 8...14: "1–2 weeks"
        case 15...21: "2–3 weeks"
        default: "3+ weeks"
        }
    }

    /// Priority: spoiled "Looks off" > past expiry "Expired" > "Today" / "Tomorrow" (urgent) >
    /// semi_fresh "Use soon" > estimated range (or exact "N days" when the date was typed in).
    /// Returns nil with no expiry date and nothing to flag. `estimated` is false only when the person
    /// entered the date (`expiry_source == "user"`).
    static func make(expiry: Date?, freshness: Freshness?, estimated: Bool = true, now: Date = Date(),
                     calendar: Calendar = .current) -> ExpiryBadgeModel? {
        if freshness == .spoiled { return .init(kind: .looksOff) }
        guard let expiry else {
            return freshness == .semiFresh ? .init(kind: .useSoon) : nil
        }
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now),
                                           to: calendar.startOfDay(for: expiry)).day ?? 0
        switch days {
        case ..<0: return .init(kind: .expired)
        case 0: return .init(kind: .today)
        case 1: return .init(kind: .tomorrow)
        default:
            if freshness == .semiFresh { return .init(kind: .useSoon) }
            return .init(kind: estimated ? .estimated(days: days) : .exactDays(days))
        }
    }

    static func make(for item: Item, now: Date = Date(), calendar: Calendar = .current) -> ExpiryBadgeModel? {
        make(expiry: item.predictedExpiry, freshness: item.freshness, estimated: item.expirySource != "user",
             now: now, calendar: calendar)
    }

    /// Spoken form: "Looks off, may be spoiled", "Expires tomorrow", "Expires in 2 to 3 days".
    var accessibilityText: String {
        switch kind {
        case .looksOff: "Looks off, may be spoiled"
        case .useSoon: "Use soon"
        case .expired: "Expired"
        case .today: "Expires today"
        case .tomorrow: "Expires tomorrow"
        case .exactDays(let n): "Expires in \(n) days"
        case .estimated: "Expires in about " + text.replacingOccurrences(of: "–", with: " to ")
        }
    }

    /// Lower-case phrase for running text, e.g. "expires tomorrow".
    var phrase: String {
        switch kind {
        case .looksOff: "looks off"
        case .useSoon: "use soon"
        case .expired: "expired"
        case .today: "expires today"
        case .tomorrow: "expires tomorrow"
        case .exactDays(let n): "expires in \(n) days"
        case .estimated: "expires in " + text
        }
    }
}

struct ExpiryBadge: View {
    let model: ExpiryBadgeModel

    var body: some View {
        Text(model.text)
            .font(Theme.Fonts.badge)
            .foregroundStyle(ink)
            .lineLimit(1)
            .padding(.horizontal, Theme.Spacing.badgeHorizontal).padding(.vertical, Theme.Spacing.xs)
            .background(bg, in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
            .fixedSize()   // never wraps
            .accessibilityLabel(model.accessibilityText)
    }

    private var bg: Color {
        switch model.style {
        case .urgent: Theme.Colors.urgentBg
        case .useSoon: Theme.Colors.useSoonBg
        case .later: Theme.Colors.limeTint
        }
    }
    private var ink: Color {
        switch model.style {
        case .urgent: Theme.Colors.urgentInk
        case .useSoon: Theme.Colors.useSoonInk
        case .later: Theme.Colors.forest
        }
    }
}
