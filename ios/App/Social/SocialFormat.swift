import Foundation

extension FoodCategory {
    /// Food-group identity for the tile colour.
    var foodGroup: FoodGroup {
        switch self {
        case .produceLeafy, .produceHardy: .veggies
        case .dairy: .dairy
        case .meat, .seafood, .eggs: .protein
        case .bakery: .grains
        case .leftovers: .leftovers
        case .pantryDry: .pantry
        case .frozen: .frozen
        case .other: .other
        }
    }
}

enum SocialText {
    /// "now", "20m", "3h", "2d".
    static func ago(_ date: Date?, now: Date = Date()) -> String {
        guard let date else { return "" }
        let s = max(0, Int(now.timeIntervalSince(date)))
        switch s {
        case ..<60: return "now"
        case ..<3600: return "\(s / 60)m"
        case ..<86_400: return "\(s / 3600)h"
        default: return "\(s / 86_400)d"
        }
    }

    static func agoLong(_ date: Date?, now: Date = Date()) -> String {
        let short = ago(date, now: now)
        if short.isEmpty { return "" }
        if short == "now" { return "Just now" }
        let unit = short.last!
        let n = String(short.dropLast())
        switch unit {
        case "m": return "\(n) min ago"
        case "h": return "\(n) h ago"
        default: return "\(n) d ago"
        }
    }

    static func firstName(_ name: String) -> String {
        name.split(separator: " ").first.map(String.init) ?? name
    }
}

extension HelpRequest {
    /// Small label above the text: group name, the author, or "You".
    var sourceLabel: String {
        switch source {
        case .me: "You"
        case .group: groupName ?? audiences.groups.first?.name ?? "Group"
        case .friend: authorName
        }
    }

    /// "Marcus, 20m".
    var whoLine: String {
        let who = source == .me ? "You" : SocialText.firstName(authorName)
        let t = SocialText.ago(createdAt)
        return t.isEmpty ? who : "\(who), \(t)"
    }

    /// "Friends, Moody Hall 4F".
    var audienceSummary: String {
        var parts: [String] = []
        if audiences.friends { parts.append("Friends") }
        parts += audiences.groups.map(\.name)
        return parts.isEmpty ? "Private" : parts.joined(separator: ", ")
    }
}
