import Foundation

extension MockData {
    /// `GET /impact` for a user with no events (`-UITestSeed empty`): zeros, no previous for All.
    static func emptyImpact(range: ImpactRange, now: Date = Date(), calendar: Calendar = .current) -> Impact {
        var cal = calendar
        cal.firstWeekday = 2
        let monday = cal.dateInterval(of: .weekOfYear, for: now)?.start ?? cal.startOfDay(for: now)
        let last6 = (0..<6).map { i in
            WeekCounts(week: cal.date(byAdding: .day, value: -7 * (5 - i), to: monday)!, used: 0, donated: 0, saved: 0, wasted: 0)
        }
        let reasons = [WasteReason.expired, .didntLike, .forgot, .other].map {
            WasteReasonStat(reason: $0, count: 0, kg: 0, money: 0, co2eKg: 0, share: 0)
        }
        let previous = ImpactPrevious(saved: .zero, wasted: .zero, used: .zero, donated: .zero, wasteRate: 0)
        return Impact(range: range.rawValue, saved: .zero, wasted: .zero, wasteRate: 0, wasteReasons: reasons,
                      previous: range == .all ? nil : previous, weekly: [], last6Weeks: last6)
    }
}
