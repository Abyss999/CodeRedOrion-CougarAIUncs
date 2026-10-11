import SwiftUI

/// What the badge says and how it is styled, derived from an item's expiry and freshness.
/// Uses the local calendar, so "Today" flips at the user's midnight.
struct ExpiryBadgeModel: Equatable {
    enum Style: Equatable { case urgent, useSoon, later }
    let text: String
    let style: Style

    /// Priority: spoiled "Check" > past expiry "Expired" > "Today" / "1 day" (urgent) >
    /// semi_fresh "Use soon" > "N days". Returns nil with no expiry date and nothing to flag.
    static func make(expiry: Date?, freshness: Freshness?, now: Date = Date(),
                     calendar: Calendar = .current) -> ExpiryBadgeModel? {
        if freshness == .spoiled { return .init(text: "Check", style: .urgent) }
        guard let expiry else {
            return freshness == .semiFresh ? .init(text: "Use soon", style: .useSoon) : nil
        }
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now),
                                           to: calendar.startOfDay(for: expiry)).day ?? 0
        switch days {
        case ..<0: return .init(text: "Expired", style: .urgent)
        case 0: return .init(text: "Today", style: .urgent)
        case 1: return .init(text: "1 day", style: .urgent)
        default:
            if freshness == .semiFresh { return .init(text: "Use soon", style: .useSoon) }
            return .init(text: "\(days) days", style: .later)
        }
    }

    static func make(for item: Item, now: Date = Date(), calendar: Calendar = .current) -> ExpiryBadgeModel? {
        make(expiry: item.predictedExpiry, freshness: item.freshness, now: now, calendar: calendar)
    }

    var accessibilityText: String {
        switch text {
        case "Check": "Check, looks spoiled"
        case "Use soon": "Use soon"
        case "Expired": "Expired"
        case "Today": "Expires today"
        default: "Expires in \(text)"
        }
    }
}

struct ExpiryBadge: View {
    let model: ExpiryBadgeModel

    var body: some View {
        Text(model.text)
            .font(Theme.Fonts.badge)
            .foregroundStyle(ink)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(bg, in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
            .fixedSize()
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
