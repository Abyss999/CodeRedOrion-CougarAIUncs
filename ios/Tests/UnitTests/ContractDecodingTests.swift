import XCTest
@testable import FoodWasteReducer

/// Decodes JSON built exactly to the shapes in docs/API.md into every shared-foundation model.
/// Timestamps use both documented forms (`...Z`) and what Python `isoformat()` really emits
/// (`...123456+00:00`, backend/app/routes/_util.py::iso).
final class ContractDecodingTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APICoding.decoder.decode(type, from: Data(json.utf8))
    }
    private func decode<T: Decodable>(_ json: String) throws -> T {
        try APICoding.decoder.decode(T.self, from: Data(json.utf8))
    }

    private func utc(_ s: String) -> Date { ISO8601DateFormatter().date(from: s)! }

    private func ymd(_ d: Date?) -> [Int?] {
        guard let d else { return [nil] }
        let c = Calendar.current.dateComponents([.year, .month, .day], from: d)
        return [c.year, c.month, c.day]
    }

    // MARK: Friends

    func testFriendsIncomingOutgoingAccepted() throws {
        let r: FriendsResponse = try decode("""
        {"friends":[{"user_id":"u-ana","display_name":"Ana","status":"accepted","created_at":"2026-10-01T09:00:00.123456+00:00"}],
         "incoming":[{"user_id":"u-sam","display_name":"Sam","status":"pending","created_at":"2026-10-09T18:30:00Z"}],
         "outgoing":[{"user_id":"u-dev","display_name":"Devon","status":"pending","created_at":"2026-10-10T07:05:00Z"}]}
        """)
        XCTAssertEqual(r.friends.map(\.userId), ["u-ana"])
        XCTAssertEqual(r.friends.first?.status, .accepted)
        XCTAssertEqual(r.incoming.first?.displayName, "Sam")
        XCTAssertEqual(r.incoming.first?.status, .pending)
        XCTAssertEqual(r.outgoing.first?.userId, "u-dev")
        XCTAssertEqual(r.friends.first?.id, "u-ana", "Identifiable id is the other user's id")
        let ana = try XCTUnwrap(r.friends.first?.createdAt)
        XCTAssertEqual(ana.timeIntervalSince1970, utc("2026-10-01T09:00:00Z").timeIntervalSince1970 + 0.123456, accuracy: 0.001)
    }

    func testFriendsEmptyListsAndSingleFriendEnvelope() throws {
        let r: FriendsResponse = try decode(#"{"friends":[],"incoming":[],"outgoing":[]}"#)
        XCTAssertEqual(r, .empty)
        let f: FriendResponse = try decode(#"{"friend":{"user_id":"u1","display_name":"Ana","status":"pending","created_at":"2026-10-10T07:05:00Z"}}"#)
        XCTAssertEqual(f.friend.status, .pending)
    }

    func testFriendWithNullCreatedAt() throws {
        let f: Friend = try decode(#"{"user_id":"u1","display_name":"Ana","status":"accepted","created_at":null}"#)
        XCTAssertNil(f.createdAt)
    }

    // MARK: Groups

    private let groupJSON = """
    {"id":"g-1","name":"Roomies","role":"owner","member_count":3,"invite_code":"K7PQ4XZ2","created_by":"u-me","created_at":"2026-09-20T12:00:00Z"}
    """

    func testGroupListAndNullCreatedBy() throws {
        let r: GroupsResponse = try decode("""
        {"groups":[\(groupJSON),
          {"id":"g-2","name":"Dorm 4","role":"member","member_count":12,"invite_code":"ABCDEFGH","created_by":null,"created_at":"2026-09-21T12:00:00+00:00"}]}
        """)
        XCTAssertEqual(r.groups.count, 2)
        XCTAssertEqual(r.groups[0].role, .owner)
        XCTAssertEqual(r.groups[0].inviteCode, "K7PQ4XZ2")
        XCTAssertEqual(r.groups[0].memberCount, 3)
        XCTAssertNil(r.groups[1].createdBy, "created_by is null after the creator deleted their account")
        XCTAssertEqual(r.groups[1].role, .member)
    }

    func testGroupDetailWithMembers() throws {
        let r: GroupDetailResponse = try decode("""
        {"group":{"id":"g-1","name":"Roomies","role":"owner","member_count":2,"invite_code":"K7PQ4XZ2","created_by":"u-me",
          "created_at":"2026-09-20T12:00:00Z",
          "members":[{"user_id":"u-me","display_name":"Priya","role":"owner","joined_at":"2026-09-20T12:00:00Z"},
                     {"user_id":"u-ana","display_name":"Ana","role":"member","joined_at":"2026-09-22T08:15:30.5Z"}]}}
        """)
        XCTAssertEqual(r.group.group.name, "Roomies")
        XCTAssertEqual(r.group.id, "g-1")
        XCTAssertEqual(r.group.members.map(\.displayName), ["Priya", "Ana"])
        XCTAssertEqual(r.group.members.map(\.role), [.owner, .member])
        XCTAssertNotNil(r.group.members[1].joinedAt)
    }

    func testGroupDetailWithoutMembersKeyIsEmpty() throws {
        let r: GroupDetailResponse = try decode(#"{"group":\#(groupJSON)}"#)
        XCTAssertEqual(r.group.members, [])
    }

    func testLeftResponse() throws {
        XCTAssertTrue(try decode(LeftResponse.self, #"{"left":true}"#).left)
    }

    func testGroupPantryItemsCarryAddedBy() throws {
        let r: PantryItemsResponse = try decode("""
        {"items":[{"id":"i1","owner_id":"u-ana","group_id":"g-1","name":"Eggs","category":"eggs","food_group":"protein",
          "storage":"fridge","quantity":12,"unit":"piece","est_weight_kg":0.7,"est_price":4.5,"source":"manual",
          "added_at":"2026-10-08T10:00:00Z","predicted_expiry":"2026-10-30","expiry_source":"default","removed_at":null,
          "outcome":null,"waste_reason":null,"removed_after_expiry":null,"freshness":null,"freshness_checked_at":null,
          "confidence":null,"added_by":"Ana"}]}
        """)
        let p = try XCTUnwrap(r.items.first)
        XCTAssertEqual(p.addedBy, "Ana")
        XCTAssertEqual(p.item.name, "Eggs")
        XCTAssertEqual(p.item.groupId, "g-1")
        XCTAssertNil(p.item.share, "group pantry items carry no share")
        XCTAssertEqual(ymd(p.item.predictedExpiry), [2026, 10, 30])
    }

    // MARK: Share / listings

    private let listingBase = """
    "id":"l-1","item_id":"i-1","owner_id":"u-me","group_id":null,"status":"open","recipient_id":null,"claimed_by":null,
    "created_at":"2026-10-10T12:00:00.123456+00:00","fulfilled_at":null
    """

    func testListingWithoutAudienceDecodes() throws {
        let r: ListingResponse = try decode(#"{"listing":{\#(listingBase)}}"#)
        XCTAssertNil(r.listing.audience)
        XCTAssertEqual(r.listing.status, .open)
        XCTAssertNil(r.listing.claimedBy)
        XCTAssertNil(r.listing.fulfilledAt)
    }

    func testListingWithOwnerAudience() throws {
        let r: ListingResponse = try decode("""
        {"listing":{\(listingBase),"audience":{"friends":true,"groups":[{"id":"g-1","name":"Roomies"}]}}}
        """)
        XCTAssertEqual(r.listing.audience?.friends, true)
        XCTAssertEqual(r.listing.audience?.groups, [GroupRef(id: "g-1", name: "Roomies")])
    }

    func testListingAudiencePartialAndEmptyObjects() throws {
        let a: ListingResponse = try decode(#"{"listing":{\#(listingBase),"audience":{}}}"#)
        XCTAssertEqual(a.listing.audience, ListingAudience(friends: false, groups: []))
        let b: ListingResponse = try decode(#"{"listing":{\#(listingBase),"audience":{"groups":[{"id":"g","name":"G"}]}}}"#)
        XCTAssertEqual(b.listing.audience?.friends, false)
        let n: ListingResponse = try decode(#"{"listing":{\#(listingBase),"audience":null}}"#)
        XCTAssertNil(n.listing.audience)
    }

    func testFulfilledListingWithRecipientAndClaimer() throws {
        let r: ListingResponse = try decode("""
        {"listing":{"id":"l-1","item_id":"i-1","owner_id":"u-me","group_id":"g-1","status":"fulfilled","recipient_id":"u-ana",
         "claimed_by":"u-ana","created_at":"2026-10-10T12:00:00Z","fulfilled_at":"2026-10-10T13:30:00Z"}}
        """)
        XCTAssertEqual(r.listing.status, .fulfilled)
        XCTAssertEqual(r.listing.recipientId, "u-ana")
        XCTAssertEqual(r.listing.claimedBy, "u-ana")
        XCTAssertEqual(r.listing.groupId, "g-1")
        XCTAssertEqual(r.listing.fulfilledAt, utc("2026-10-10T13:30:00Z"))
    }

    func testFoodPantryEntryFriendAndGroupSources() throws {
        let r: PantryListingsResponse = try decode("""
        {"listings":[
          {"id":"l-9","item_id":"i-9","owner_id":"u-ana","owner_name":"Ana","group_id":null,"status":"open","claimed_by_me":true,
           "created_at":"2026-10-10T08:00:00Z","source":{"type":"friend","name":"Ana"},
           "item":{"name":"Yogurt","category":"dairy","quantity":2,"unit":"cup","predicted_expiry":"2026-10-13"}},
          {"id":"l-10","item_id":"i-10","owner_id":"u-sam","owner_name":"Sam","group_id":"g-1","status":"open","claimed_by_me":false,
           "created_at":"2026-10-09T08:00:00+00:00","source":{"type":"group","name":"Roomies"},
           "item":{"name":"Basil","category":"produce_leafy","quantity":1,"unit":"bunch","predicted_expiry":null}}]}
        """)
        XCTAssertEqual(r.listings.count, 2)
        XCTAssertEqual(r.listings[0].source.type, .friend)
        XCTAssertTrue(r.listings[0].claimedByMe)
        XCTAssertEqual(r.listings[0].item.category, .dairy)
        XCTAssertEqual(ymd(r.listings[0].item.predictedExpiry), [2026, 10, 13])
        XCTAssertEqual(r.listings[1].source.type, .group)
        XCTAssertEqual(r.listings[1].source.name, "Roomies")
        XCTAssertNil(r.listings[1].item.predictedExpiry)
        XCTAssertEqual(r.listings[1].groupId, "g-1")
    }

    func testFoodPantryEmpty() throws {
        XCTAssertEqual(try decode(PantryListingsResponse.self, #"{"listings":[]}"#).listings.count, 0)
    }

    // MARK: Requests

    func testRequestWithAudiencesHiddenCountAndFulfilledBy() throws {
        let r: HelpRequestsResponse = try decode("""
        {"requests":[
         {"id":"r-1","author_id":"u-ana","author_name":"Ana","text":"Anyone have an egg?","status":"open","fulfilled_by":null,
          "fulfilled_by_name":null,"created_at":"2026-10-10T11:00:00.250000+00:00",
          "audiences":{"friends":true,"groups":[{"id":"g-1","name":"Dorm 4"},{"id":"g-2","name":"Roomies"}],"hidden_count":2},
          "source":"group","group_id":"g-1","group_name":"Dorm 4"},
         {"id":"r-2","author_id":"u-me","author_name":"Priya","text":"Need flour","status":"fulfilled","fulfilled_by":"u-sam",
          "fulfilled_by_name":"Sam","created_at":"2026-10-09T11:00:00Z",
          "audiences":{"friends":false,"groups":[],"hidden_count":0},"source":"me","group_id":null,"group_name":null},
         {"id":"r-3","author_id":"u-dev","author_name":"Devon","text":"Salt?","status":"open","fulfilled_by":null,
          "fulfilled_by_name":null,"created_at":"2026-10-08T11:00:00Z",
          "audiences":{"friends":true,"groups":[],"hidden_count":0},"source":"friend","group_id":null,"group_name":null}]}
        """)
        let a = r.requests[0]
        XCTAssertEqual(a.audiences.hiddenCount, 2)
        XCTAssertEqual(a.audiences.groups.map(\.name), ["Dorm 4", "Roomies"])
        XCTAssertTrue(a.audiences.friends)
        XCTAssertEqual(a.source.type, .group)
        XCTAssertEqual(a.groupId, "g-1")
        XCTAssertEqual(a.status, .open)
        XCTAssertNil(a.fulfilledBy)
        let b = r.requests[1]
        XCTAssertEqual(b.status, .fulfilled)
        XCTAssertEqual(b.fulfilledBy, "u-sam")
        XCTAssertEqual(b.fulfilledByName, "Sam")
        XCTAssertEqual(b.source.type, .me)
        XCTAssertFalse(b.audiences.friends)
        XCTAssertNil(b.groupId)
        XCTAssertEqual(r.requests[2].source.type, .friend)
    }

    func testRequestAudiencesToleratesMissingHiddenCountAndUnknownSource() throws {
        let r: HelpRequestResponse = try decode("""
        {"request":{"id":"r-1","author_id":"u","author_name":"A","text":"t","status":"cancelled","fulfilled_by":null,
         "fulfilled_by_name":null,"created_at":null,"audiences":{"friends":true,"groups":[]},"source":"other-future-value"}}
        """)
        XCTAssertEqual(r.request.audiences.hiddenCount, 0)
        XCTAssertEqual(r.request.source.type, .friend)
        XCTAssertEqual(r.request.status, .cancelled)
        XCTAssertNil(r.request.groupId)
        XCTAssertNil(r.request.createdAt)
    }

    func testNewRequestBodyEncoding() throws {
        let data = try APICoding.encoder.encode(NewRequestBody(text: "Eggs?", audiences: .init(friends: true, groupIds: ["g-1", "g-2"])))
        let o = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(o["text"] as? String, "Eggs?")
        let a = try XCTUnwrap(o["audiences"] as? [String: Any])
        XCTAssertEqual(a["friends"] as? Bool, true)
        XCTAssertEqual(a["group_ids"] as? [String], ["g-1", "g-2"])
        XCTAssertNil(o["group_id"], "the deprecated group_id must not be sent with audiences (400)")
    }

    // MARK: Recipes

    func testRecipeUsesItemsObjectsAndServings() throws {
        let r: RecipesResponse = try decode("""
        {"recipes":[{"title":"Spinach omelette","minutes":15,"servings":2,
          "uses_items":[{"item_id":"i-1","name":"Baby spinach","predicted_expiry":"2026-10-11"},
                        {"item_id":"i-2","name":"Eggs","predicted_expiry":null}],
          "missing_items":["salt"],"steps":["Whisk.","Cook."],
          "macros":{"kcal":320,"protein_g":18.5,"carbs_g":4,"fat_g":24},"macros_estimated":true},
         {"title":"Toast","minutes":5,"servings":null,"uses_items":[],"missing_items":[],"steps":[],"macros":null,"macros_estimated":true}]}
        """)
        let a = r.recipes[0]
        XCTAssertEqual(a.servings, 2)
        XCTAssertEqual(a.usesItems.map(\.itemId), ["i-1", "i-2"])
        XCTAssertEqual(a.usesItems[0].name, "Baby spinach")
        XCTAssertEqual(ymd(a.usesItems[0].predictedExpiry), [2026, 10, 11])
        XCTAssertNil(a.usesItems[1].predictedExpiry)
        XCTAssertEqual(a.missingItems, ["salt"])
        XCTAssertEqual(a.macros?.kcal, 320)
        XCTAssertEqual(a.macros?.proteinG, 18.5)
        XCTAssertTrue(a.macrosEstimated)
        let b = r.recipes[1]
        XCTAssertNil(b.servings)
        XCTAssertNil(b.macros)
        XCTAssertTrue(b.usesItems.isEmpty)
    }

    func testRecipeItemIdIsStableAndLegacyStringStillDecodes() throws {
        let objs: RecipeItem = try decode(#"{"item_id":"i-1","name":"Milk","predicted_expiry":"2026-10-12"}"#)
        XCTAssertEqual(objs.id, "i-1")
        let legacy: RecipeItem = try decode(#""Milk""#)
        XCTAssertEqual(legacy.name, "Milk")
        XCTAssertEqual(legacy.itemId, "")
        XCTAssertEqual(legacy.id, "Milk")
    }

    func testRecipeSuggestRequestBodyOmitsNil() throws {
        let data = try APICoding.encoder.encode(RecipeSuggestRequest(maxResults: 5, dietary: nil))
        let o = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(o["max_results"] as? Int, 5)
        XCTAssertNil(o["dietary"])
    }

    // MARK: Impact (wave 2)

    private func impactJSON(range: String = "week", previous: String) -> String {
        """
        {"range":"\(range)",
         "saved":{"count":3,"kg":1.2,"money":8.5,"co2e_kg":2.1},
         "wasted":{"count":1,"kg":0.5,"money":3.5,"co2e_kg":2.25},
         "used":{"count":1,"kg":0.4,"money":2.0,"co2e_kg":0.7},
         "donated":{"count":2,"kg":0.8,"money":6.5,"co2e_kg":1.4},
         "waste_rate":0.25,
         "waste_reasons":[{"reason":"forgot","count":1,"kg":0.5,"money":3.5,"co2e_kg":2.25,"share":1.0},
                          {"reason":"expired","count":0,"kg":0,"money":0,"co2e_kg":0,"share":0},
                          {"reason":"didnt_like","count":0,"kg":0,"money":0,"co2e_kg":0,"share":0},
                          {"reason":"other","count":0,"kg":0,"money":0,"co2e_kg":0,"share":0}],
         "previous":\(previous),
         "weekly":[{"week":"2026-10-05","saved":3,"wasted":1}],
         "last_6_weeks":[{"week":"2026-09-07","used":0,"donated":0,"saved":0,"wasted":0},
                         {"week":"2026-09-14","used":0,"donated":0,"saved":0,"wasted":0},
                         {"week":"2026-09-21","used":1,"donated":0,"saved":1,"wasted":0},
                         {"week":"2026-09-28","used":0,"donated":0,"saved":0,"wasted":0},
                         {"week":"2026-10-05","used":1,"donated":2,"saved":3,"wasted":1},
                         {"week":"2026-10-12","used":0,"donated":0,"saved":0,"wasted":0}]}
        """
    }

    private let previousJSON = """
    {"saved":{"count":2,"kg":0.9,"money":5,"co2e_kg":1.5},"wasted":{"count":2,"kg":1,"money":7,"co2e_kg":4.5},
     "used":{"count":2,"kg":0.9,"money":5,"co2e_kg":1.5},"donated":{"count":0,"kg":0,"money":0,"co2e_kg":0},"waste_rate":0.5}
    """

    func testImpactWave2WithPrevious() throws {
        let i: Impact = try decode(impactJSON(previous: previousJSON))
        XCTAssertEqual(i.range, "week")
        XCTAssertEqual(i.saved, ImpactTotals(count: 3, kg: 1.2, money: 8.5, co2eKg: 2.1))
        XCTAssertEqual(i.wasted.co2eKg, 2.25)
        XCTAssertEqual(i.used.count + i.donated.count, i.saved.count, "saved = used + donated")
        XCTAssertEqual(i.wasteRate, 0.25)
        let p = try XCTUnwrap(i.previous)
        XCTAssertEqual(p.wasteRate, 0.5)
        XCTAssertEqual(p.saved.count, 2)
        XCTAssertEqual(p.donated, .zero)
        XCTAssertEqual(i.weekly.count, 1)
        XCTAssertEqual(ymd(i.weekly[0].week), [2026, 10, 5])
    }

    func testImpactPreviousNullForRangeAll() throws {
        let i: Impact = try decode(impactJSON(range: "all", previous: "null"))
        XCTAssertNil(i.previous)
        XCTAssertEqual(i.range, "all")
    }

    func testImpactWasteReasonsAreAllFourAndShareIsFraction() throws {
        let i: Impact = try decode(impactJSON(previous: "null"))
        XCTAssertEqual(i.wasteReasons.map(\.reason), [.forgot, .expired, .didntLike, .other])
        XCTAssertEqual(i.wasteReasons[0].share, 1.0)
        XCTAssertEqual(i.wasteReasons[0].co2eKg, 2.25)
        XCTAssertEqual(i.wasteReasons.map(\.count).reduce(0, +), i.wasted.count)
        XCTAssertEqual(i.wasteReasons.map(\.id), [.forgot, .expired, .didntLike, .other])
    }

    func testImpactLast6WeeksAlwaysSixOldestFirstMondays() throws {
        let i: Impact = try decode(impactJSON(previous: "null"))
        XCTAssertEqual(i.last6Weeks.count, 6)
        XCTAssertEqual(i.last6Weeks.map(\.week), i.last6Weeks.map(\.week).sorted(), "oldest first")
        XCTAssertEqual(i.last6Weeks[4].used, 1)
        XCTAssertEqual(i.last6Weeks[4].donated, 2)
        XCTAssertEqual(i.last6Weeks[4].saved, 3)
        XCTAssertEqual(i.last6Weeks[4].wasted, 1)
        for w in i.last6Weeks {
            XCTAssertEqual(w.saved, w.used + w.donated)
            var cal = Calendar(identifier: .gregorian); cal.timeZone = .current
            XCTAssertEqual(cal.component(.weekday, from: w.week), 2, "bucket start is a Monday")
        }
    }

    func testImpactZeroDataAndSplitFieldsMissingStillDecode() throws {
        let i: Impact = try decode("""
        {"range":"all","saved":{"count":0,"kg":0,"money":0,"co2e_kg":0},"wasted":{"count":0,"kg":0,"money":0,"co2e_kg":0},
         "waste_rate":0,"previous":null,"weekly":[]}
        """)
        XCTAssertEqual(i.used, .zero)
        XCTAssertEqual(i.donated, .zero)
        XCTAssertEqual(i.wasteReasons, [])
        XCTAssertEqual(i.last6Weeks, [])
        XCTAssertEqual(i.weekly, [])
    }

    func testImpactIntegerJSONNumbersDecodeAsDouble() throws {
        // Python emits 0 / 12 (not 0.0 / 12.0) for whole numbers.
        let t: ImpactTotals = try decode(#"{"count":2,"kg":12,"money":9,"co2e_kg":0}"#)
        XCTAssertEqual(t.kg, 12)
        XCTAssertEqual(t.money, 9)
    }

    // MARK: Tips

    func testTipsShape() throws {
        let r: TipsResponse = try decode("""
        {"tips":[{"code":"past_expiry","message":"Ham is past the expiry date and still logged as in stock."},
                 {"code":"top_reason_forgot","message":"3 of the 4 items you threw out in the last 30 days had expired."},
                 {"code":"getting_started","message":"Nothing used, donated or thrown out in the last 30 days."}]}
        """)
        XCTAssertEqual(r.tips.map(\.code), ["past_expiry", "top_reason_forgot", "getting_started"])
        XCTAssertEqual(r.tips.map(\.id), r.tips.map(\.code))
        XCTAssertTrue(r.tips.allSatisfy { $0.message.count <= 100 })
        XCTAssertEqual(try decode(TipsResponse.self, #"{"tips":[]}"#).tips.count, 0)
    }

    // MARK: Add food: receipt, barcode

    func testReceiptCandidatesWithPriceTotalAndNulls() throws {
        let r: ReceiptResponse = try decode("""
        {"candidates":[
          {"name":"Whole milk","category":"dairy","food_group":"dairy","storage":"fridge","quantity":1,"unit":"gal","est_price":3.48,
           "predicted_expiry":"2026-10-20","expiry_source":"default","price":3.48,"receipt_text":"GV WHL MILK GAL"},
          {"name":"CHKN BRST","category":"meat","food_group":"protein","storage":"fridge","quantity":1,"unit":"piece","est_price":null,
           "predicted_expiry":"2026-10-13","expiry_source":"gemini","price":null,"receipt_text":"CHKN BRST"}],
         "total":21.07,"categorized_by":"gemini"}
        """)
        XCTAssertEqual(r.candidates.count, 2)
        XCTAssertEqual(r.total, 21.07)
        XCTAssertEqual(r.categorizedBy, "gemini")
        let milk = r.candidates[0]
        XCTAssertEqual(milk.candidate.name, "Whole milk")
        XCTAssertEqual(milk.price, 3.48)
        XCTAssertEqual(milk.receiptText, "GV WHL MILK GAL")
        XCTAssertEqual(milk.candidate.estPrice, 3.48)
        XCTAssertEqual(milk.candidate.foodGroup, .dairy)
        XCTAssertEqual(milk.candidate.expirySource, "default")
        XCTAssertNil(r.candidates[1].price)
        XCTAssertNil(r.candidates[1].candidate.estPrice)
        XCTAssertEqual(r.candidates[1].candidate.expirySource, "gemini")
    }

    func testReceiptTotalNullAndHeuristic() throws {
        let r: ReceiptResponse = try decode(#"{"candidates":[],"total":null,"categorized_by":"heuristic"}"#)
        XCTAssertNil(r.total)
        XCTAssertEqual(r.categorizedBy, "heuristic")
        XCTAssertTrue(r.candidates.isEmpty)
    }

    func testReceiptCandidateIdsDifferForSameNameDifferentLines() throws {
        let r: ReceiptResponse = try decode("""
        {"candidates":[
         {"name":"Milk","category":"dairy","food_group":"dairy","price":1.0,"receipt_text":"MLK 1"},
         {"name":"Milk","category":"dairy","food_group":"dairy","price":1.0,"receipt_text":"MLK 2"}],"total":2.0,"categorized_by":"heuristic"}
        """)
        XCTAssertEqual(Set(r.candidates.map(\.id)).count, 2, "duplicate lines need distinct ids for SwiftUI lists")
    }

    func testBarcodeCandidateWithBrandAndQuantityText() throws {
        let b: BarcodeResult = try decode("""
        {"candidate":{"name":"Greek yogurt","category":"dairy","food_group":"dairy","storage":"fridge","quantity":1,"unit":"piece",
          "est_price":null,"predicted_expiry":"2026-10-24","expiry_source":"default","barcode":"0123456789012","brand":"Fage",
          "quantity_text":"32 oz"}}
        """)
        XCTAssertEqual(b.candidate.name, "Greek yogurt")
        XCTAssertEqual(b.barcode, "0123456789012")
        XCTAssertEqual(b.brand, "Fage")
        XCTAssertEqual(b.quantityText, "32 oz")
        XCTAssertEqual(ymd(b.candidate.predictedExpiry), [2026, 10, 24])
    }

    func testBarcodeOptionalsNull() throws {
        let b: BarcodeResult = try decode("""
        {"candidate":{"name":"Mystery","category":"other","food_group":"other","barcode":null,"brand":null,"quantity_text":null}}
        """)
        XCTAssertNil(b.barcode); XCTAssertNil(b.brand); XCTAssertNil(b.quantityText)
        XCTAssertNil(b.candidate.storage)
    }

    func testCandidatesResponseBboxNullAndSource() throws {
        let r: CandidatesResponse = try decode("""
        {"candidates":[{"name":"Apple","category":"produce_hardy","confidence":0.91,"freshness":"semi_fresh","bbox":[0.1,0.2,0.5,0.6],
          "food_group":"fruit"},
         {"name":"Milk","category":"dairy","confidence":0.7,"freshness":"fresh","bbox":null,"food_group":"dairy"}],"source":"yolo"}
        """)
        XCTAssertEqual(r.source, "yolo")
        XCTAssertEqual(r.candidates[0].bbox, [0.1, 0.2, 0.5, 0.6])
        XCTAssertNil(r.candidates[1].bbox)
        XCTAssertEqual(r.candidates[0].freshness, .semiFresh)
    }

    // MARK: Auth

    func testGoogleSignInCreatedAndExisting() throws {
        let user = #"{"id":"u1","email":"p@gmail.com","display_name":"Priya","created_at":"2026-10-10T12:00:00.000000+00:00"}"#
        let created: GoogleAuthResult = try decode(#"{"token":"jwt.1","user":\#(user),"created":true}"#)
        XCTAssertTrue(created.created)
        XCTAssertEqual(created.session.token, "jwt.1")
        XCTAssertEqual(created.session.user.email, "p@gmail.com")
        let existing: GoogleAuthResult = try decode(#"{"token":"jwt.2","user":\#(user),"created":false}"#)
        XCTAssertFalse(existing.created)
    }

    func testMeAcceptsWrappedAndFlatShapes() throws {
        let wrapped: Me = try decode(#"{"user":{"id":"u1","email":"a@b.co","display_name":"A","created_at":"2026-10-10T12:00:00Z"},"has_password":false,"providers":["google"]}"#)
        XCTAssertEqual(wrapped.user.id, "u1")
        XCTAssertEqual(wrapped.hasPassword, false)
        XCTAssertEqual(wrapped.providers, ["google"])
        let flat: Me = try decode(#"{"id":"u1","email":"a@b.co","display_name":"A","created_at":null}"#)
        XCTAssertEqual(flat.user.displayName, "A")
        XCTAssertNil(flat.hasPassword)
        XCTAssertNil(flat.providers)
        XCTAssertNil(flat.user.createdAt)
    }

    func testAuthSessionAndUserCreatedAtFormats() throws {
        for ts in ["2026-10-10T12:00:00Z", "2026-10-10T12:00:00+00:00", "2026-10-10T12:00:00.123456+00:00", "2026-10-10T12:00:00.5Z"] {
            let s: AuthSession = try decode(#"{"token":"t","user":{"id":"u","email":"e@x.co","display_name":"D","created_at":"\#(ts)"}}"#)
            XCTAssertNotNil(s.user.createdAt, ts)
        }
    }

    func testHealth() throws {
        XCTAssertTrue(try decode(HealthResponse.self, #"{"status":"ok"}"#).isOK)
        XCTAssertFalse(try decode(HealthResponse.self, #"{"status":"degraded"}"#).isOK)
    }

    // MARK: People

    func testReachablePeopleWithIsClaimer() throws {
        let r: PeopleResponse = try decode("""
        {"people":[
          {"id":"u-ana","display_name":"Ana","kind":"friend","groups":[],"is_claimer":true},
          {"id":"u-sam","display_name":"Sam","kind":"group_member","groups":[{"id":"g-1","name":"Roomies"}],"is_claimer":false},
          {"id":"u-dev","display_name":"Devon","kind":"friend"}]}
        """)
        XCTAssertEqual(r.people[0].isClaimer, true)
        XCTAssertEqual(r.people[1].kind, .groupMember)
        XCTAssertEqual(r.people[1].groups?.first?.name, "Roomies")
        XCTAssertEqual(r.people[1].isClaimer, false)
        XCTAssertNil(r.people[2].isClaimer, "is_claimer is optional")
        XCTAssertNil(r.people[2].groups)
    }

    func testReachablePeopleNameOnlyGroupsStillDecode() throws {
        let r: PeopleResponse = try decode(#"{"people":[{"id":"u","display_name":"Sam","kind":"group_member","groups":["Roomies","Dorm 4"]}]}"#)
        XCTAssertEqual(r.people[0].groups?.map(\.name), ["Roomies", "Dorm 4"])
    }

    // MARK: Items round trip with new bits

    func testItemWithShareAndMultiSourceStillDecodes() throws {
        let i: Item = try decode("""
        {"id":"i-1","owner_id":"u","group_id":null,"name":"Salmon","category":"seafood","food_group":"protein","storage":"freezer",
         "quantity":2,"unit":"fillet","est_weight_kg":0.35,"est_price":12,"source":"receipt","added_at":"2026-10-10T12:00:00.000000+00:00",
         "predicted_expiry":"2026-11-30","expiry_source":"ml","removed_at":"2026-10-11T08:00:00Z","outcome":"donated","waste_reason":null,
         "removed_after_expiry":false,"freshness":"fresh","freshness_checked_at":"2026-10-10T12:00:00Z","confidence":0.88,
         "share":{"id":"l-1","status":"fulfilled","claimed_by":{"id":"u-ana","name":"Ana"}}}
        """)
        XCTAssertEqual(i.outcome, .donated)
        XCTAssertTrue(i.isRemoved)
        XCTAssertEqual(i.share?.status, .fulfilled)
        XCTAssertEqual(i.storage, .freezer)
        XCTAssertEqual(i.confidence, 0.88)
    }

    func testUnknownEnumValuesDoNotCrash() throws {
        let i: Item = try decode("""
        {"id":"i","name":"x","category":"brand_new_category","food_group":"brand_new_group","storage":"fridge","quantity":1,"unit":"piece"}
        """)
        XCTAssertEqual(i.category, .other)
        XCTAssertEqual(i.foodGroup, .other)
    }

    // MARK: Backend shapes confirmed by the coordinator (feat/backend-gaps)

    func testMeTopLevelHasPasswordAndProviders() throws {
        let me: Me = try decode(#"{"user":{"id":"u1","email":"a@b.co","display_name":"A","created_at":"2026-10-10T12:00:00+00:00"},"has_password":true,"providers":["google"]}"#)
        XCTAssertEqual(me.hasPassword, true, "has_password sits beside `user`")
        XCTAssertEqual(me.providers, ["google"])
        XCTAssertEqual(me.user.displayName, "A")
        let none: Me = try decode(#"{"user":{"id":"u1","email":"a@b.co","display_name":"A","created_at":null},"has_password":false,"providers":[]}"#)
        XCTAssertEqual(none.hasPassword, false)
        XCTAssertEqual(none.providers, [])
    }

    func testMineRequestsShape() throws {
        let r: HelpRequestsResponse = try decode("""
        {"requests":[{"id":"r-1","author_id":"u-me","author_name":"Priya","text":"Need lemon","status":"fulfilled","fulfilled_by":"u-ana",
          "fulfilled_by_name":"Ana","created_at":"2026-10-10T11:00:00+00:00",
          "audiences":{"friends":true,"groups":[{"id":"g-1","name":"Roomies"}],"hidden_count":0},"source":"me","group_id":"g-1","group_name":"Roomies"}]}
        """)
        XCTAssertEqual(r.requests[0].fulfilledBy, "u-ana")
        XCTAssertEqual(r.requests[0].fulfilledByName, "Ana")
        XCTAssertEqual(r.requests[0].audiences.hiddenCount, 0)
    }

    func testOwnerItemShareCarriesAudience() throws {
        let i: Item = try decode("""
        {"id":"i-1","name":"Milk","category":"dairy","food_group":"dairy","storage":"fridge","quantity":1,"unit":"gal",
         "share":{"id":"l-1","status":"open","claimed_by":null,"audience":{"friends":true,"groups":[]}}}
        """)
        let audience = Mirror(reflecting: try XCTUnwrap(i.share)).children.first { $0.label == "audience" }
        XCTAssertNotNil(audience, "ItemShare drops the documented `audience`: the owner's Fridge row cannot say who it is shared with")
    }

    func testOwnerItemShareAudienceWithGroups() throws {
        let i: Item = try decode("""
        {"id":"i-1","name":"Milk","category":"dairy","food_group":"dairy","storage":"fridge","quantity":1,"unit":"gal",
         "share":{"id":"l-1","status":"open","claimed_by":{"id":"u2","name":"Ana"},"audience":{"friends":false,"groups":[{"id":"g-1","name":"Roomies"}]}}}
        """)
        XCTAssertEqual(i.share?.claimedBy?.name, "Ana")
        let audience = Mirror(reflecting: try XCTUnwrap(i.share)).children.first { $0.label == "audience" }
        XCTAssertNotNil(audience)
    }
}
