import XCTest
@testable import FoodWasteReducer

/// JSON below mirrors the examples in docs/API.md (snake_case, ISO dates, `{"error": {...}}`).
final class ModelsTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APICoding.decoder.decode(type, from: Data(json.utf8))
    }

    private let itemJSON = """
    {"id":"7b1c2f3e-0000-4000-8000-000000000001","owner_id":"u1","group_id":null,"name":"Chicken thighs",
     "category":"meat","food_group":"protein","storage":"fridge","quantity":1.4,"unit":"lb",
     "est_weight_kg":0.64,"est_price":8.9,"source":"photo","added_at":"2026-10-07T18:22:11Z",
     "predicted_expiry":"2026-10-10","expiry_source":"gemini","removed_at":null,"outcome":null,
     "waste_reason":null,"removed_after_expiry":null}
    """

    func testItemDecodesSnakeCaseAndDates() throws {
        let item = try decode(Item.self, itemJSON)
        XCTAssertEqual(item.name, "Chicken thighs")
        XCTAssertEqual(item.foodGroup, .protein)
        XCTAssertEqual(item.category, .meat)
        XCTAssertEqual(item.storage, .fridge)
        XCTAssertEqual(item.quantity, 1.4)
        XCTAssertEqual(item.estWeightKg, 0.64)
        XCTAssertEqual(item.expirySource, "gemini")
        XCTAssertNil(item.groupId)
        XCTAssertNil(item.removedAt)
        XCTAssertFalse(item.isRemoved)
        XCTAssertEqual(item.addedAt, ISO8601DateFormatter().date(from: "2026-10-07T18:22:11Z"))
        let c = Calendar.current.dateComponents([.year, .month, .day, .hour], from: try XCTUnwrap(item.predictedExpiry))
        XCTAssertEqual([c.year, c.month, c.day, c.hour], [2026, 10, 10, 0], "date-only expiry is local midnight")
    }

    func testOptionalFreshnessAndShareAbsent() throws {
        let item = try decode(Item.self, itemJSON)
        XCTAssertNil(item.freshness)
        XCTAssertNil(item.share)
        XCTAssertNil(item.freshnessCheckedAt)
    }

    func testOptionalFreshnessAndSharePresent() throws {
        let json = itemJSON.replacingOccurrences(of: "\"removed_after_expiry\":null}", with:
            "\"removed_after_expiry\":null,\"freshness\":\"semi_fresh\",\"freshness_checked_at\":\"2026-10-09T10:00:00.123Z\"," +
            "\"share\":{\"id\":\"s1\",\"status\":\"open\",\"claimed_by\":{\"id\":\"u2\",\"name\":\"Marcus\"}}}")
        let item = try decode(Item.self, json)
        XCTAssertEqual(item.freshness, .semiFresh)
        XCTAssertNotNil(item.freshnessCheckedAt, "fractional-second timestamps must parse")
        XCTAssertEqual(item.share?.status, .open)
        XCTAssertEqual(item.share?.claimedBy?.name, "Marcus")
    }

    func testShareWithoutClaimant() throws {
        let json = itemJSON.replacingOccurrences(of: "\"removed_after_expiry\":null}", with:
            "\"removed_after_expiry\":null,\"share\":{\"id\":\"s1\",\"status\":\"open\",\"claimed_by\":null}}")
        XCTAssertNil(try decode(Item.self, json).share?.claimedBy)
    }

    func testRemovedItemFields() throws {
        let json = itemJSON
            .replacingOccurrences(of: "\"removed_at\":null", with: "\"removed_at\":\"2026-10-11T09:00:00Z\"")
            .replacingOccurrences(of: "\"outcome\":null", with: "\"outcome\":\"thrown_out\"")
            .replacingOccurrences(of: "\"waste_reason\":null", with: "\"waste_reason\":\"didnt_like\"")
            .replacingOccurrences(of: "\"removed_after_expiry\":null", with: "\"removed_after_expiry\":true")
        let item = try decode(Item.self, json)
        XCTAssertTrue(item.isRemoved)
        XCTAssertEqual(item.outcome, .thrownOut)
        XCTAssertEqual(item.wasteReason, .didntLike)
        XCTAssertEqual(item.removedAfterExpiry, true)
    }

    func testUnknownEnumValuesFallBackToOther() throws {
        let json = itemJSON.replacingOccurrences(of: "\"protein\"", with: "\"mystery\"")
            .replacingOccurrences(of: "\"meat\"", with: "\"weird\"")
        let item = try decode(Item.self, json)
        XCTAssertEqual(item.foodGroup, .other)
        XCTAssertEqual(item.category, .other)
    }

    func testExtraUnknownKeysAreIgnored() throws {
        let json = itemJSON.replacingOccurrences(of: "\"name\"", with: "\"future_field\":1,\"name\"")
        XCTAssertEqual(try decode(Item.self, json).name, "Chicken thighs")
    }

    func testItemsAndSectionsResponses() throws {
        let flat = try decode(ItemsResponse.self, "{\"items\":[\(itemJSON)]}")
        XCTAssertEqual(flat.items.count, 1)
        let grouped = try decode(SectionsResponse.self, "{\"sections\":[{\"food_group\":\"protein\",\"items\":[\(itemJSON)]}]}")
        XCTAssertEqual(grouped.sections.first?.foodGroup, .protein)
        XCTAssertEqual(grouped.sections.first?.items.count, 1)
    }

    func testAuthSessionAndUser() throws {
        let s = try decode(AuthSession.self, """
        {"token":"jwt.abc.def","user":{"id":"u1","email":"p@x.com","display_name":"Priya","created_at":"2026-10-01T00:00:00Z"}}
        """)
        XCTAssertEqual(s.token, "jwt.abc.def")
        XCTAssertEqual(s.user.displayName, "Priya")
        XCTAssertNotNil(s.user.createdAt)
    }

    func testCandidatesResponse() throws {
        let r = try decode(CandidatesResponse.self, """
        {"candidates":[{"name":"Banana","category":"produce_hardy","food_group":"fruit","confidence":0.88,
          "freshness":"semi_fresh","bbox":[0.1,0.2,0.3,0.4],"storage":"pantry","quantity":5,"unit":"piece",
          "est_price":1.9,"predicted_expiry":"2026-10-13","expiry_source":"default"},
          {"name":"Milk","category":"dairy","food_group":"dairy","confidence":null,"bbox":null}],
         "source":"yolo"}
        """)
        XCTAssertEqual(r.source, "yolo")
        XCTAssertEqual(r.candidates[0].freshness, .semiFresh)
        XCTAssertEqual(r.candidates[0].bbox, [0.1, 0.2, 0.3, 0.4])
        XCTAssertNil(r.candidates[1].bbox)
        XCTAssertNil(r.candidates[1].freshness)
        XCTAssertNotEqual(r.candidates[0].id, r.candidates[1].id)
    }

    func testImpact() throws {
        let i = try decode(Impact.self, """
        {"saved":{"count":23,"kg":14.2,"money":61.4,"co2e_kg":38.6},
         "wasted":{"count":6,"kg":3.1,"money":14.2,"co2e_kg":8.4},
         "waste_rate":0.21,"weekly":[{"week":"2026-10-05","saved":8,"wasted":1}]}
        """)
        XCTAssertEqual(i.saved.co2eKg, 38.6)
        XCTAssertEqual(i.wasteRate, 0.21)
        XCTAssertEqual(i.weekly.count, 1)
        XCTAssertEqual(i.weekly[0].saved, 8)
        let empty = try decode(Impact.self, """
        {"saved":{"count":0,"kg":0,"money":0,"co2e_kg":0},"wasted":{"count":0,"kg":0,"money":0,"co2e_kg":0},"waste_rate":0,"weekly":[]}
        """)
        XCTAssertTrue(empty.weekly.isEmpty)
    }

    func testRecipesWithAndWithoutMacros() throws {
        let r = try decode(RecipesResponse.self, """
        {"recipes":[{"title":"Skillet","minutes":25,"uses_items":["Chicken"],"missing_items":["Garlic"],"steps":["Cook"],
          "macros":{"kcal":520,"protein_g":42,"carbs_g":14,"fat_g":30.5},"macros_estimated":true},
          {"title":"Bowl","minutes":5,"uses_items":[],"missing_items":[],"steps":[],"macros":null,"macros_estimated":true}]}
        """)
        XCTAssertEqual(r.recipes[0].macros?.proteinG, 42)
        XCTAssertEqual(r.recipes[0].macros?.fatG, 30.5)
        XCTAssertNil(r.recipes[1].macros)
    }

    func testTips() throws {
        let t = try decode(TipsResponse.self, "{\"tips\":[{\"code\":\"getting_started\",\"message\":\"Add food\"}]}")
        XCTAssertEqual(t.tips.first?.id, "getting_started")
    }

    func testErrorShape() throws {
        let e = try decode(APIErrorBody.self, "{\"error\":{\"code\":\"already_removed\",\"message\":\"Item already removed\"}}")
        XCTAssertEqual(e.error.code, "already_removed")
        XCTAssertEqual(e.error.message, "Item already removed")
        let err = APIError.server(status: 409, code: e.error.code, message: e.error.message)
        XCTAssertEqual(err.code, "already_removed")
        XCTAssertEqual(err.errorDescription, "Item already removed")
        XCTAssertEqual(APIError.unauthorized.code, "unauthorized")
        XCTAssertTrue(APIError.network("x").isNetwork)
        XCTAssertFalse(APIError.unauthorized.isNetwork)
    }

    func testMalformedJSONThrows() {
        XCTAssertThrowsError(try decode(Item.self, "{\"id\":\"x\"}"))
        XCTAssertThrowsError(try decode(Item.self, itemJSON.replacingOccurrences(of: "2026-10-07T18:22:11Z", with: "yesterday")))
    }

    // MARK: Encoding

    func testItemRoundTrip() throws {
        let item = try decode(Item.self, itemJSON)
        let data = try APICoding.encoder.encode(item)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNotNil(obj["food_group"], "encoder must emit snake_case")
        XCTAssertNotNil(obj["est_weight_kg"])
        XCTAssertNil(obj["foodGroup"])
        let back = try APICoding.decoder.decode(Item.self, from: data)
        XCTAssertEqual(back.id, item.id)
        XCTAssertEqual(back.name, item.name)
        XCTAssertEqual(back.foodGroup, item.foodGroup)
        XCTAssertEqual(back.quantity, item.quantity)
        XCTAssertEqual(back.addedAt, item.addedAt)
        XCTAssertEqual(back.predictedExpiry, item.predictedExpiry)
    }

    func testAuthSessionRoundTrip() throws {
        let s = AuthSession(token: "t", user: MockData.priya)
        let back = try APICoding.decoder.decode(AuthSession.self, from: APICoding.encoder.encode(s))
        XCTAssertEqual(back, s)
    }

    func testCreateRequestEncoding() throws {
        let req = CreateItemsRequest(items: [NewItem(name: "Milk", category: .dairy, foodGroup: .dairy, storage: .fridge,
                                                     quantity: 1, unit: "gal", predictedExpiry: "2026-10-20", source: "manual")])
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: APICoding.encoder.encode(req)) as? [String: Any])
        let first = try XCTUnwrap((obj["items"] as? [[String: Any]])?.first)
        XCTAssertEqual(first["predicted_expiry"] as? String, "2026-10-20")
        XCTAssertEqual(first["food_group"] as? String, "dairy")
        XCTAssertNil(first["est_price"], "nil optionals are omitted")
    }

    func testRemoveRequestEncodingUsesAPIRawValues() throws {
        let body = RemoveRequest(outcome: .thrownOut, wasteReason: .didntLike, recipientId: nil)
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(with: APICoding.encoder.encode(body)) as? [String: Any])
        XCTAssertEqual(obj["outcome"] as? String, "thrown_out")
        XCTAssertEqual(obj["waste_reason"] as? String, "didnt_like")
        XCTAssertNil(obj["recipient_id"])
    }

    func testPatchOmitsNilFields() throws {
        let obj = try XCTUnwrap(JSONSerialization.jsonObject(
            with: APICoding.encoder.encode(ItemPatch(name: "Oat milk", storage: .pantry))) as? [String: Any])
        XCTAssertEqual(Set(obj.keys), ["name", "storage"])
    }

    func testDayStringAndTimestamp() {
        var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: "America/Chicago")!
        let d = c.date(from: DateComponents(year: 2026, month: 3, day: 5, hour: 23, minute: 50))!
        XCTAssertEqual(APIDate.dayString(d, calendar: c), "2026-03-05")
        XCTAssertEqual(APIDate.timestampString(Date(timeIntervalSince1970: 0)), "1970-01-01T00:00:00Z")
    }

    func testEveryFoodGroupDecodesFromAPIValue() throws {
        for g in ["protein", "veggies", "fruit", "dairy", "grains", "pantry", "leftovers", "frozen", "other"] {
            let e = try decode(ItemSection.self, "{\"food_group\":\"\(g)\",\"items\":[]}")
            XCTAssertEqual(e.foodGroup.rawValue, g)
        }
        XCTAssertEqual(FoodGroup.allCases.count, 9)
    }
}
