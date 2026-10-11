import Foundation

/// Mock data for the social surfaces (friends, groups, Food Pantry, request board, people), the
/// receipt and barcode add paths and the wave-2 Impact. Same cast as the Fridge seed: Priya,
/// Marcus Ojeda, Moody Hall 4F and CougarCS Kitchen.
struct MockSocialState: Sendable {
    var friends: FriendsResponse
    var groups: [SharingGroup]
    var members: [String: [GroupMember]]
    /// Groups that can be joined by invite code (key = normalised code).
    var joinable: [String: SharingGroup]
    var pantry: [PantryListing]
    /// Listings the signed-in user owns (the spinach and carrots listings on the Fridge items).
    var listings: [Listing]
    var requests: [HelpRequest]
    var people: [Person]
    var groupPantry: [String: [PantryItem]]
    /// Accounts `requestFriend` can find, by lowercased email.
    var directory: [String: User]
}

extension MockData {
    static let ana = User(id: "user-ana", email: "ana@example.com", displayName: "Ana Reyes", createdAt: nil)
    static let devon = User(id: "user-devon", email: "devon@example.com", displayName: "Devon Park", createdAt: nil)
    static let jordan = User(id: "user-jordan", email: "jordan@example.com", displayName: "Jordan Kim", createdAt: nil)
    static let sam = User(id: "user-sam", email: "sam@example.com", displayName: "Sam Okafor", createdAt: nil)
    static let taylor = User(id: "user-taylor", email: "taylor@example.com", displayName: "Taylor Brooks", createdAt: nil)
    static let marcusFull = User(id: friend.id, email: friend.email, displayName: "Marcus Ojeda", createdAt: nil)

    static func social(for fixture: MockFixture = .fridge, now: Date = Date(), calendar: Calendar = .current) -> MockSocialState {
        let start = calendar.startOfDay(for: now)
        func day(_ n: Int) -> Date { calendar.date(byAdding: .day, value: n, to: start)! }
        func ago(_ hours: Int) -> Date { now.addingTimeInterval(-Double(hours) * 3600) }

        let moody = SharingGroup(id: "group-moody", name: "Moody Hall 4F", role: .member, memberCount: 4,
                                 inviteCode: "MDY4FH23", createdBy: ana.id, createdAt: day(-40))
        let ccs = SharingGroup(id: "group-ccs", name: "CougarCS Kitchen", role: .owner, memberCount: 3,
                               inviteCode: "CGRKTCH7", createdBy: priya.id, createdAt: day(-25))
        let garden = SharingGroup(id: "group-garden", name: "Cougar Gardeners", role: .member, memberCount: 9,
                                  inviteCode: "GRDN2345", createdBy: taylor.id, createdAt: day(-60))
        if fixture == .empty {
            return MockSocialState(friends: .empty, groups: [], members: [:], joinable: ["GRDN2345": garden], pantry: [],
                                   listings: [], requests: [], people: [], groupPantry: [:], directory: directoryUsers)
        }

        func member(_ u: User, _ role: GroupRole, _ joined: Int) -> GroupMember {
            GroupMember(userId: u.id, displayName: u.displayName, role: role, joinedAt: day(-joined))
        }
        let members: [String: [GroupMember]] = [
            moody.id: [member(ana, .owner, 40), member(priya, .member, 30), member(marcusFull, .member, 22), member(devon, .member, 9)],
            ccs.id: [member(priya, .owner, 25), member(devon, .member, 20), member(jordan, .member, 11)],
        ]

        let friends = FriendsResponse(
            friends: [Friend(userId: marcusFull.id, displayName: marcusFull.displayName, status: .accepted, createdAt: day(-30)),
                      Friend(userId: ana.id, displayName: ana.displayName, status: .accepted, createdAt: day(-18))],
            incoming: [Friend(userId: jordan.id, displayName: jordan.displayName, status: .pending, createdAt: ago(5))],
            outgoing: [Friend(userId: sam.id, displayName: sam.displayName, status: .pending, createdAt: ago(30))])

        func food(_ name: String, _ cat: FoodCategory, _ qty: Double, _ unit: String, _ expiry: Int) -> PantryListing.Food {
            .init(name: name, category: cat, quantity: qty, unit: unit, predictedExpiry: day(expiry))
        }
        let pantry = [
            PantryListing(id: "share-sourdough", itemId: "item-marcus-sourdough", ownerId: marcusFull.id, ownerName: "Marcus Ojeda",
                          groupId: nil, status: .open, claimedByMe: false, createdAt: ago(3),
                          source: .init(type: .friend, name: "Marcus Ojeda"), item: food("Sourdough loaf", .bakery, 1, "loaf", 2)),
            PantryListing(id: "share-rice", itemId: "item-ana-rice", ownerId: ana.id, ownerName: "Ana Reyes",
                          groupId: moody.id, status: .open, claimedByMe: false, createdAt: ago(8),
                          source: .init(type: .group, name: "Moody Hall 4F"), item: food("Cooked rice", .leftovers, 3, "cup", 1)),
            PantryListing(id: "share-apples", itemId: "item-marcus-apples", ownerId: marcusFull.id, ownerName: "Marcus Ojeda",
                          groupId: ccs.id, status: .open, claimedByMe: true, createdAt: ago(26),
                          source: .init(type: .group, name: "CougarCS Kitchen"), item: food("Gala apples", .produceHardy, 6, "piece", 9)),
        ]

        let listings = [
            Listing(id: "share-spinach", itemId: "item-spinach", ownerId: priya.id, groupId: nil, status: .open, recipientId: nil,
                    claimedBy: marcusFull.id, createdAt: ago(20), fulfilledAt: nil, audience: ListingAudience(friends: true)),
            Listing(id: "share-carrots", itemId: "item-carrots", ownerId: priya.id, groupId: moody.id, status: .open, recipientId: nil,
                    claimedBy: nil, createdAt: ago(6), fulfilledAt: nil,
                    audience: ListingAudience(groups: [GroupRef(id: moody.id, name: moody.name)])),
        ]

        let requests = [
            HelpRequest(id: "req-onion", authorId: marcusFull.id, authorName: "Marcus Ojeda",
                        text: "Anyone have an onion I can borrow? Making chili tonight.", status: .open, fulfilledBy: nil,
                        fulfilledByName: nil, createdAt: ago(2), audiences: RequestAudiences(friends: true), source: .friend,
                        groupId: nil, groupName: nil),
            HelpRequest(id: "req-tortillas", authorId: ana.id, authorName: "Ana Reyes",
                        text: "Does anyone on 4F have tortillas? Taco night.", status: .open, fulfilledBy: nil, fulfilledByName: nil,
                        createdAt: ago(7), audiences: RequestAudiences(groups: [GroupRef(id: moody.id, name: moody.name)], hiddenCount: 1),
                        source: .group, groupId: moody.id, groupName: moody.name),
            HelpRequest(id: "req-lemon", authorId: priya.id, authorName: "Priya",
                        text: "Need one lemon for a salmon recipe.", status: .open, fulfilledBy: nil, fulfilledByName: nil,
                        createdAt: ago(1),
                        audiences: RequestAudiences(friends: true, groups: [GroupRef(id: ccs.id, name: ccs.name)]),
                        source: .me, groupId: ccs.id, groupName: ccs.name),
        ]

        let people = [
            Person(id: marcusFull.id, displayName: "Marcus Ojeda", kind: .friend,
                   groups: [GroupRef(id: moody.id, name: moody.name)], isClaimer: true),
            Person(id: ana.id, displayName: "Ana Reyes", kind: .friend, groups: [GroupRef(id: moody.id, name: moody.name)], isClaimer: false),
            Person(id: devon.id, displayName: "Devon Park", kind: .groupMember,
                   groups: [GroupRef(id: moody.id, name: moody.name), GroupRef(id: ccs.id, name: ccs.name)], isClaimer: false),
            Person(id: jordan.id, displayName: "Jordan Kim", kind: .groupMember, groups: [GroupRef(id: ccs.id, name: ccs.name)], isClaimer: false),
        ]

        func pantryItem(_ id: String, _ name: String, _ cat: FoodCategory, _ group: FoodGroup, _ qty: Double, _ unit: String,
                        _ expiry: Int, by: User, storage: Storage = .fridge, groupId: String) -> PantryItem {
            PantryItem(item: Item(id: id, ownerId: by.id, groupId: groupId, name: name, category: cat, foodGroup: group,
                                  storage: storage, quantity: qty, unit: unit, estWeightKg: 0.4, estPrice: 3.5, source: "manual",
                                  addedAt: day(-2), predictedExpiry: day(expiry), expirySource: "default", removedAt: nil, outcome: nil,
                                  wasteReason: nil, removedAfterExpiry: nil, freshness: nil, freshnessCheckedAt: nil,
                                  confidence: nil, share: nil),
                       addedBy: by.displayName)
        }
        let groupPantry: [String: [PantryItem]] = [
            moody.id: [pantryItem("gp-hotsauce", "Hot sauce", .pantryDry, .pantry, 1, "bottle", 120, by: ana, storage: .pantry, groupId: moody.id),
                       pantryItem("gp-dumplings", "Frozen dumplings", .frozen, .frozen, 2, "bag", 60, by: devon, storage: .freezer, groupId: moody.id)],
            ccs.id: [pantryItem("gp-cheddar", "Cheddar block", .dairy, .dairy, 1, "lb", 14, by: jordan, groupId: ccs.id),
                     pantryItem("gp-tortillas", "Flour tortillas", .bakery, .grains, 10, "piece", 5, by: priya, groupId: ccs.id)],
        ]

        return MockSocialState(friends: friends, groups: [moody, ccs], members: members,
                               joinable: ["GRDN2345": garden], pantry: pantry, listings: listings, requests: requests,
                               people: people, groupPantry: groupPantry, directory: directoryUsers)
    }

    static var directoryUsers: [String: User] {
        Dictionary(uniqueKeysWithValues: [marcusFull, ana, devon, jordan, sam, taylor].map { ($0.email, $0) })
    }

    // MARK: Receipt and barcode

    static func receipt(now: Date = Date(), calendar: Calendar = .current) -> ReceiptResponse {
        func day(_ n: Int) -> Date { calendar.date(byAdding: .day, value: n, to: calendar.startOfDay(for: now))! }
        func line(_ name: String, _ cat: FoodCategory, _ group: FoodGroup, _ storage: Storage, _ qty: Double, _ unit: String,
                  _ price: Double, _ expiry: Int, text: String) -> ReceiptCandidate {
            ReceiptCandidate(candidate: Candidate(name: name, category: cat, foodGroup: group, confidence: nil, freshness: nil, bbox: nil,
                                                  storage: storage, quantity: qty, unit: unit, estPrice: price,
                                                  predictedExpiry: day(expiry), expirySource: "default"),
                             price: price, receiptText: text)
        }
        return ReceiptResponse(candidates: [
            line("Whole milk", .dairy, .dairy, .fridge, 1, "gal", 3.48, 9, text: "GV WHL MILK GAL"),
            line("Chicken breast", .meat, .protein, .fridge, 2.1, "lb", 9.87, 2, text: "CHKN BRST BNLS"),
            line("Bananas", .produceHardy, .fruit, .pantry, 6, "piece", 1.74, 4, text: "BANANAS"),
            line("Greek yogurt", .dairy, .dairy, .fridge, 32, "oz", 5.49, 12, text: "YGRT GRK PLN 32"),
            line("Sourdough bread", .bakery, .grains, .pantry, 1, "loaf", 4.25, 5, text: "BRD SOURDGH"),
        ], total: 27.43, categorizedBy: "gemini")
    }

    static func barcode(_ code: String, now: Date = Date(), calendar: Calendar = .current) -> BarcodeResult? {
        func day(_ n: Int) -> Date { calendar.date(byAdding: .day, value: n, to: calendar.startOfDay(for: now))! }
        switch code {
        case "016000275287":
            return BarcodeResult(candidate: Candidate(name: "Cheerios", category: .pantryDry, foodGroup: .grains, confidence: nil, freshness: nil, bbox: nil,
                                                      storage: .pantry, quantity: 1, unit: "box", estPrice: 4.99, predictedExpiry: day(150), expirySource: "default"),
                                 barcode: code, brand: "General Mills", quantityText: "18 oz")
        case "070470003795":
            return BarcodeResult(candidate: Candidate(name: "Chobani Greek yogurt", category: .dairy, foodGroup: .dairy, confidence: nil, freshness: nil, bbox: nil,
                                                      storage: .fridge, quantity: 32, unit: "oz", estPrice: 5.99, predictedExpiry: day(14), expirySource: "default"),
                                 barcode: code, brand: "Chobani", quantityText: "32 oz")
        default:
            return nil
        }
    }

    // MARK: Impact (wave-2 shape)

    private static func round2(_ v: Double) -> Double { (v * 100).rounded() / 100 }
    private static func saved(_ n: Int) -> ImpactTotals {
        ImpactTotals(count: n, kg: round2(Double(n) * 0.62), money: round2(Double(n) * 2.67), co2eKg: round2(Double(n) * 1.68))
    }
    private static func wasted(_ n: Int) -> ImpactTotals {
        ImpactTotals(count: n, kg: round2(Double(n) * 0.52), money: round2(Double(n) * 2.37), co2eKg: round2(Double(n) * 1.4))
    }
    private static func sum(_ a: ImpactTotals, _ b: ImpactTotals) -> ImpactTotals {
        ImpactTotals(count: a.count + b.count, kg: round2(a.kg + b.kg), money: round2(a.money + b.money), co2eKg: round2(a.co2eKg + b.co2eKg))
    }
    private static func rate(_ saved: Int, _ wasted: Int) -> Double { saved + wasted == 0 ? 0 : round2(Double(wasted) / Double(saved + wasted)) }

    static func impact(range: ImpactRange, now: Date = Date(), calendar: Calendar = .current) -> Impact {
        // (used, donated, wasted by reason: expired, didnt_like, forgot, other), then the previous window.
        let cur: (Int, Int, [Int]), prev: (Int, Int, Int)?
        switch range {
        case .week: cur = (4, 2, [0, 0, 1, 0]); prev = (3, 1, 2)
        case .month: cur = (11, 6, [1, 1, 2, 0]); prev = (9, 4, 5)
        case .all: cur = (15, 8, [2, 1, 3, 0]); prev = nil
        }
        let used = saved(cur.0), donated = saved(cur.1)
        let wastedCount = cur.2.reduce(0, +)
        let totalWasted = wasted(wastedCount)
        let reasonCases: [WasteReason] = [.expired, .didntLike, .forgot, .other]
        let reasons = zip(reasonCases, cur.2).enumerated().map { (i, pair) in
            (i, WasteReasonStat(reason: pair.0, count: pair.1, kg: wasted(pair.1).kg, money: wasted(pair.1).money,
                                co2eKg: wasted(pair.1).co2eKg, share: wastedCount == 0 ? 0 : round2(Double(pair.1) / Double(wastedCount))))
        }
        .sorted { $0.1.count != $1.1.count ? $0.1.count > $1.1.count : $0.0 < $1.0 }.map(\.1)

        var cal = calendar
        cal.firstWeekday = 2
        let monday = cal.dateInterval(of: .weekOfYear, for: now)?.start ?? cal.startOfDay(for: now)
        let usedPerWeek = [2, 3, 4, 3, 5, 4], donatedPerWeek = [0, 1, 1, 2, 2, 2], wastedPerWeek = [2, 1, 2, 1, 1, 1]
        let last6 = (0..<6).map { i in
            WeekCounts(week: cal.date(byAdding: .day, value: -7 * (5 - i), to: monday)!, used: usedPerWeek[i], donated: donatedPerWeek[i],
                       saved: usedPerWeek[i] + donatedPerWeek[i], wasted: wastedPerWeek[i])
        }
        let weekly = last6.map { WeeklyBucket(week: $0.week, saved: $0.saved, wasted: $0.wasted) }

        let previous = prev.map { p in
            ImpactPrevious(saved: saved(p.0 + p.1), wasted: wasted(p.2), used: saved(p.0), donated: saved(p.1), wasteRate: rate(p.0 + p.1, p.2))
        }
        return Impact(range: range.rawValue, saved: sum(used, donated), wasted: totalWasted, used: used, donated: donated,
                      wasteRate: rate(cur.0 + cur.1, wastedCount), wasteReasons: reasons, previous: previous,
                      weekly: range == .week ? Array(weekly.suffix(1)) : weekly, last6Weeks: last6)
    }
}
