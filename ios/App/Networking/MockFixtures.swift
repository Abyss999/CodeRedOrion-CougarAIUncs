import Foundation

/// Named data sets for `MockAPIClient` (`-UITestSeed <name>`). The default, `fridge`, matches the
/// Fridge artboard: Priya's fridge with chicken today, spinach in 1 day, strawberries flagged
/// spoiled and bananas ripe ("Use soon"). Dates are relative to `now` so badges are stable.
/// Spinach has an open Share listing claimed by Marcus; carrots have an open, unclaimed listing.
enum MockFixture: String, CaseIterable, Sendable {
    case fridge
    case empty
    /// Past-expiry and spoiled items, to exercise "Expired" and "Check".
    case expired
    /// 30+ items across all groups, for scrolling.
    case long
    /// Same items as `fridge` (which carries the listings); named for UI tests of "Gave it to".
    case listing

    init(name: String?) { self = name.flatMap(MockFixture.init(rawValue:)) ?? .fridge }
}

enum MockData {
    static let priya = User(id: "user-priya", email: "priya@example.com", displayName: "Priya", createdAt: nil)
    static let friend = User(id: "user-marcus", email: "marcus@example.com", displayName: "Marcus", createdAt: nil)

    static func items(for fixture: MockFixture, now: Date = Date(), calendar: Calendar = .current) -> [Item] {
        func day(_ offset: Int) -> Date {
            calendar.date(byAdding: .day, value: offset, to: calendar.startOfDay(for: now))!
        }
        func make(_ id: String, _ name: String, _ cat: FoodCategory, _ group: FoodGroup, _ qty: Double, _ unit: String,
                  expiry: Int?, storage: Storage = .fridge, addedDaysAgo: Int = 3, price: Double? = 4.5,
                  freshness: Freshness? = nil, share: ItemShare? = nil) -> Item {
            Item(id: id, ownerId: priya.id, groupId: nil, name: name, category: cat, foodGroup: group,
                 storage: storage, quantity: qty, unit: unit, estWeightKg: 0.5, estPrice: price, source: "photo",
                 addedAt: day(-addedDaysAgo), predictedExpiry: expiry.map(day), expirySource: "default",
                 removedAt: nil, outcome: nil, wasteReason: nil, removedAfterExpiry: nil,
                 freshness: freshness, freshnessCheckedAt: freshness == nil ? nil : day(-1),
                 confidence: freshness == nil ? nil : 0.9, share: share)
        }
        switch fixture {
        case .empty:
            return []
        case .fridge, .listing:
            return [
                make("item-chicken", "Chicken thighs", .meat, .protein, 1.4, "lb", expiry: 0, addedDaysAgo: 3, price: 8.9),
                make("item-eggs", "Eggs", .eggs, .protein, 8, "piece", expiry: 12, price: 4.2),
                make("item-spinach", "Baby spinach", .produceLeafy, .veggies, 5, "oz", expiry: 1, addedDaysAgo: 6, price: 3.5,
                     share: ItemShare(id: "share-spinach", status: .open,
                                      claimedBy: .init(id: friend.id, name: "Marcus Ojeda"))),
                make("item-carrots", "Carrots", .produceHardy, .veggies, 2, "lb", expiry: 18, price: 2.8,
                     share: ItemShare(id: "share-carrots", status: .open, claimedBy: nil)),
                make("item-strawberries", "Strawberries", .produceLeafy, .fruit, 1, "pack", expiry: 2, price: 5.0, freshness: .spoiled),
                make("item-bananas", "Bananas", .produceHardy, .fruit, 5, "piece", expiry: 3, price: 1.9, freshness: .semiFresh),
                make("item-yogurt", "Greek yogurt", .dairy, .dairy, 32, "oz", expiry: 3, price: 5.5),
                make("item-oatmilk", "Oat milk", .dairy, .dairy, 64, "oz", expiry: 6, price: 4.0),
            ]
        case .expired:
            return [
                make("item-milk", "Whole milk", .dairy, .dairy, 1, "gal", expiry: -2, price: 4.1),
                make("item-lettuce", "Romaine lettuce", .produceLeafy, .veggies, 1, "head", expiry: -1, price: 2.4),
                make("item-berries", "Blueberries", .produceLeafy, .fruit, 1, "pint", expiry: 1, price: 4.8, freshness: .spoiled),
                make("item-leftover", "Pad thai", .leftovers, .leftovers, 1, "box", expiry: 0, price: 12),
            ]
        case .long:
            let groups: [(FoodGroup, FoodCategory, String)] = [
                (.protein, .meat, "Beef"), (.veggies, .produceHardy, "Broccoli"), (.fruit, .produceHardy, "Apples"),
                (.dairy, .dairy, "Cheese"), (.grains, .bakery, "Bread"), (.pantry, .pantryDry, "Rice"),
                (.leftovers, .leftovers, "Soup"), (.frozen, .frozen, "Peas"), (.other, .other, "Hummus"),
            ]
            return (0..<36).map { i in
                let g = groups[i % groups.count]
                return make("item-long-\(i)", "\(g.2) \(i / groups.count + 1)", g.1, g.0, 1, "piece", expiry: (i * 3) % 21 - 1)
            }
        }
    }

    static func candidates(now: Date = Date(), calendar: Calendar = .current) -> [Candidate] {
        func day(_ n: Int) -> Date { calendar.date(byAdding: .day, value: n, to: calendar.startOfDay(for: now))! }
        return [
            Candidate(name: "Baby spinach", category: .produceLeafy, foodGroup: .veggies, confidence: 0.94, freshness: .fresh,
                      bbox: [0.1, 0.1, 0.4, 0.4], storage: .fridge, quantity: 5, unit: "oz", estPrice: 3.5, predictedExpiry: day(5), expirySource: "default"),
            Candidate(name: "Bananas", category: .produceHardy, foodGroup: .fruit, confidence: 0.88, freshness: .semiFresh,
                      bbox: [0.5, 0.1, 0.9, 0.4], storage: .pantry, quantity: 5, unit: "piece", estPrice: 1.9, predictedExpiry: day(2), expirySource: "default"),
            Candidate(name: "Strawberries", category: .produceLeafy, foodGroup: .fruit, confidence: 0.81, freshness: .spoiled,
                      bbox: [0.1, 0.5, 0.4, 0.9], storage: .fridge, quantity: 1, unit: "pack", estPrice: 5, predictedExpiry: day(0), expirySource: "default"),
            Candidate(name: "Greek yogurt", category: .dairy, foodGroup: .dairy, confidence: 0.45, freshness: .fresh,
                      bbox: nil, storage: .fridge, quantity: 32, unit: "oz", estPrice: 5.5, predictedExpiry: day(9), expirySource: "default"),
        ]
    }

    static let tips: [Tip] = [
        Tip(code: "forgot_leafy", message: "Spinach was forgotten twice before, so next time we'll remind you on day 3."),
    ]

    static var recipes: [Recipe] { recipes() }

    static func recipes(now: Date = Date(), calendar: Calendar = .current) -> [Recipe] {
        func day(_ n: Int) -> Date { calendar.date(byAdding: .day, value: n, to: calendar.startOfDay(for: now))! }
        return [
            Recipe(title: "Chicken and spinach skillet", minutes: 25, servings: 2,
                   usesItems: [RecipeItem(itemId: "item-chicken", name: "Chicken thighs", predictedExpiry: day(0)),
                               RecipeItem(itemId: "item-spinach", name: "Baby spinach", predictedExpiry: day(1))],
                   missingItems: ["Garlic"], steps: ["Sear the chicken.", "Wilt the spinach.", "Serve."],
                   macros: Macros(kcal: 520, proteinG: 42, carbsG: 14, fatG: 30), macrosEstimated: true),
            Recipe(title: "Banana oat pancakes", minutes: 20, servings: 3,
                   usesItems: [RecipeItem(itemId: "item-bananas", name: "Bananas", predictedExpiry: day(3)),
                               RecipeItem(itemId: "item-oatmilk", name: "Oat milk", predictedExpiry: day(6))],
                   missingItems: [], steps: ["Mash bananas.", "Mix with oats and milk.", "Pan fry."],
                   macros: Macros(kcal: 380, proteinG: 11, carbsG: 62, fatG: 9), macrosEstimated: true),
            Recipe(title: "Yogurt berry bowl", minutes: 5, servings: nil,
                   usesItems: [RecipeItem(itemId: "item-yogurt", name: "Greek yogurt", predictedExpiry: day(3)),
                               RecipeItem(itemId: "item-strawberries", name: "Strawberries", predictedExpiry: day(2))],
                   missingItems: ["Granola"], steps: ["Spoon yogurt into a bowl.", "Top with fruit."],
                   macros: nil, macrosEstimated: true),
        ]
    }
}
