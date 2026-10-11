import XCTest
@testable import FoodWasteReducer

/// Dates exactly as the backend emits them. Python `datetime.isoformat()` gives 6-digit microseconds
/// and `+00:00` (`2026-10-10T12:00:00.123456+00:00`), or no fraction when microsecond == 0
/// (`2026-10-10T12:00:00+00:00`); `routes/_util.py::iso` may rewrite `+00:00` to `Z`. Every variant
/// must decode through real item / user / impact JSON, not only through `APIDate.parse`.
final class APIDateTests: XCTestCase {
    /// 2026-10-10T12:00:00Z
    private let noon = Date(timeIntervalSince1970: 1_791_633_600)

    private func utc(_ s: String) -> Date { ISO8601DateFormatter().date(from: s)! }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try APICoding.decoder.decode(type, from: Data(json.utf8))
    }

    private func itemJSON(addedAt: String, removedAt: String = "null", checkedAt: String? = nil) -> String {
        let q: (String) -> String = { $0 == "null" ? "null" : "\"\($0)\"" }
        var json = """
        {"id":"7b1c2f3e-0000-4000-8000-000000000001","owner_id":"u1","group_id":null,"name":"Baby spinach",
         "category":"produce_leafy","food_group":"veggies","storage":"fridge","quantity":1,"unit":"bag",
         "est_weight_kg":0.14,"est_price":3.49,"source":"photo","added_at":\(q(addedAt)),
         "predicted_expiry":"2026-10-14","expiry_source":"gemini","removed_at":\(q(removedAt)),
         "outcome":\(removedAt == "null" ? "null" : "\"used\""),"waste_reason":null,
         "removed_after_expiry":\(removedAt == "null" ? "null" : "false")
        """
        if let checkedAt { json += ",\"freshness\":\"fresh\",\"freshness_checked_at\":\"\(checkedAt)\"" }
        return json + "}"
    }

    func testSanityReferenceDate() {
        XCTAssertEqual(noon, utc("2026-10-10T12:00:00Z"))
    }

    // MARK: Backend-shaped JSON

    func testItemWithPythonMicrosecondsAndPlusZeroOffset() throws {
        let item = try decode(Item.self, itemJSON(addedAt: "2026-10-10T12:00:00.123456+00:00",
                                                  removedAt: "2026-10-11T08:30:15.000001+00:00",
                                                  checkedAt: "2026-10-10T12:00:05.5+00:00"))
        XCTAssertEqual(try XCTUnwrap(item.addedAt).timeIntervalSince(noon), 0.123456, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(item.removedAt).timeIntervalSince(utc("2026-10-11T08:30:15Z")), 0.000001, accuracy: 1e-6)
        XCTAssertEqual(try XCTUnwrap(item.freshnessCheckedAt).timeIntervalSince(utc("2026-10-10T12:00:05Z")), 0.5, accuracy: 1e-6)
        XCTAssertTrue(item.isRemoved)
        let c = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: try XCTUnwrap(item.predictedExpiry))
        XCTAssertEqual([c.year, c.month, c.day, c.hour, c.minute], [2026, 10, 14, 0, 0], "date-only = local midnight")
    }

    func testItemWithPythonNoFractionAndPlusZeroOffset() throws {
        let item = try decode(Item.self, itemJSON(addedAt: "2026-10-10T12:00:00+00:00"))
        XCTAssertEqual(item.addedAt, noon)
        XCTAssertNil(item.removedAt)
    }

    func testItemWithZuluVariants() throws {
        for s in ["2026-10-10T12:00:00Z", "2026-10-10T12:00:00.000Z", "2026-10-10T12:00:00.000000Z"] {
            XCTAssertEqual(try decode(Item.self, itemJSON(addedAt: s)).addedAt, noon, s)
        }
        let frac = try decode(Item.self, itemJSON(addedAt: "2026-10-10T12:00:00.123456Z")).addedAt
        XCTAssertEqual(try XCTUnwrap(frac).timeIntervalSince(noon), 0.123456, accuracy: 1e-6)
    }

    func testItemsAndSectionsResponsesWithMixedFormats() throws {
        let a = itemJSON(addedAt: "2026-10-10T12:00:00.123456+00:00")
        let b = itemJSON(addedAt: "2026-10-10T12:00:00Z").replacingOccurrences(of: "000000000001", with: "000000000002")
        XCTAssertEqual(try decode(ItemsResponse.self, "{\"items\":[\(a),\(b)]}").items.count, 2)
        let s = try decode(SectionsResponse.self, "{\"sections\":[{\"food_group\":\"vegetables\",\"items\":[\(a),\(b)]}]}")
        XCTAssertEqual(s.sections.first?.items.count, 2)
        XCTAssertEqual(try decode(ItemResponse.self, "{\"item\":\(a)}").item.name, "Baby spinach")
    }

    func testUserCreatedAtFromAuthSession() throws {
        for s in ["2026-10-01T09:15:42.654321+00:00", "2026-10-01T09:15:42+00:00", "2026-10-01T09:15:42Z"] {
            let session = try decode(AuthSession.self, """
            {"token":"t","user":{"id":"u1","email":"priya@example.com","display_name":"Priya","created_at":"\(s)"}}
            """)
            let created = try XCTUnwrap(session.user.createdAt, s)
            XCTAssertEqual(created.timeIntervalSince(utc("2026-10-01T09:15:42Z")), s.contains(".") ? 0.654321 : 0, accuracy: 1e-6, s)
        }
    }

    /// Impact weekly buckets come from Timescale `time_bucket('1 week', time)`: the backend may send
    /// the bucket as a date or as a midnight timestamp with `+00:00`.
    func testImpactWeeklyBucketDateAndTimestamp() throws {
        let i = try decode(Impact.self, """
        {"saved":{"count":3,"kg":1.2,"money":9.5,"co2e_kg":3.0},"wasted":{"count":1,"kg":0.3,"money":2.0,"co2e_kg":0.8},
         "waste_rate":0.25,"weekly":[{"week":"2026-10-05","saved":3,"wasted":1},
                                     {"week":"2026-09-28T00:00:00+00:00","saved":0,"wasted":0},
                                     {"week":"2026-09-21T00:00:00.000000+00:00","saved":1,"wasted":0}]}
        """)
        XCTAssertEqual(i.weekly.count, 3)
        XCTAssertEqual(i.weekly[1].week, utc("2026-09-28T00:00:00Z"))
        XCTAssertEqual(i.weekly[2].week, utc("2026-09-21T00:00:00Z"))
    }

    func testMalformedDateInItemThrowsDecodingError() {
        XCTAssertThrowsError(try decode(Item.self, itemJSON(addedAt: "2026-10-10T12:00:00.+00:00"))) { e in
            guard case DecodingError.dataCorrupted = e else { return XCTFail("\(e)") }
        }
    }

    // MARK: APIDate.parse: accepted forms

    func testSeparatorsTLowercaseTAndSpace() {
        for s in ["2026-10-10T12:00:00Z", "2026-10-10t12:00:00Z", "2026-10-10 12:00:00Z",
                  "2026-10-10 12:00:00+00:00", "2026-10-10t12:00:00.0+00:00"] {
            XCTAssertEqual(APIDate.parse(s), noon, s)
        }
    }

    func testFractionOneToNineDigits() throws {
        let cases: [(String, Double)] = [
            ("5", 0.5), ("12", 0.12), ("123", 0.123), ("1234", 0.1234), ("12345", 0.12345),
            ("123456", 0.123456), ("1234567", 0.1234567), ("12345678", 0.12345678), ("123456789", 0.123456789),
        ]
        for (frac, value) in cases {
            for zone in ["Z", "+00:00", ""] {
                let s = "2026-10-10T12:00:00.\(frac)\(zone)"
                let d = try XCTUnwrap(APIDate.parse(s), s)
                XCTAssertEqual(d.timeIntervalSince(noon), value, accuracy: 1e-6, s)
            }
        }
    }

    func testZoneForms() {
        XCTAssertEqual(APIDate.parse("2026-10-10T12:00:00z"), noon)
        XCTAssertEqual(APIDate.parse("2026-10-10T12:00:00"), noon, "no zone is read as UTC")
        XCTAssertEqual(APIDate.parse("2026-10-10T12:00:00-00:00"), noon)
        XCTAssertEqual(APIDate.parse("2026-10-10T07:00:00-05:00"), noon)
        XCTAssertEqual(APIDate.parse("2026-10-10T07:00:00-0500"), noon)
        XCTAssertEqual(APIDate.parse("2026-10-10T17:30:00+05:30"), noon)
        XCTAssertEqual(APIDate.parse("2026-10-10T17:30:00+0530"), noon)
        XCTAssertEqual(APIDate.parse("2026-10-11T01:45:00+13:45"), noon, "Chatham daylight time")
        XCTAssertEqual(APIDate.parse("2026-10-10T01:00:00-11:00"), noon)
        let d = APIDate.parse("2026-10-10T07:00:00.250000-05:00")
        XCTAssertEqual(d.map { $0.timeIntervalSince(noon) } ?? -1, 0.25, accuracy: 1e-6)
    }

    func testDayBoundaryAndYearRollOverWithOffsets() {
        XCTAssertEqual(APIDate.parse("2026-12-31T23:30:00-01:00"), utc("2027-01-01T00:30:00Z"))
        XCTAssertEqual(APIDate.parse("2027-01-01T00:30:00+01:00"), utc("2026-12-31T23:30:00Z"))
        XCTAssertEqual(APIDate.parse("2028-02-29T12:00:00+00:00"), utc("2028-02-29T12:00:00Z"), "leap day")
    }

    func testDateOnlyIsLocalMidnightInTheGivenCalendar() throws {
        for tz in ["Pacific/Honolulu", "Asia/Tokyo", "UTC", "America/Chicago"] {
            var cal = Calendar(identifier: .gregorian)
            cal.timeZone = TimeZone(identifier: tz)!
            let d = try XCTUnwrap(APIDate.parse("2026-10-14", calendar: cal), tz)
            let c = cal.dateComponents([.year, .month, .day, .hour, .minute, .second], from: d)
            XCTAssertEqual([c.year, c.month, c.day, c.hour, c.minute, c.second], [2026, 10, 14, 0, 0, 0], tz)
        }
    }

    // MARK: APIDate.parse: rejected forms

    func testRejectsMalformed() {
        let bad = [
            "", "yesterday", "2026-10-10T", "2026-10-10T12:00", "2026-10-10T12:00:00.",   // bare dot
            "2026-10-10T12:00:00.Z", "2026-10-10T12:00:00.+00:00",
            "2026-10-10T12:00:00.1234567890Z", "2026-10-10T12:00:00.1234567890",           // > 9 digits
            "2026-10-10T12:00:00+00", "2026-10-10T12:00:00-05",                            // bare hour offset
            "2026-10-10T12:00:00+0", "2026-10-10T12:00:00+00:0", "2026-10-10T12:00:00+00:000",
            "2026-10-10T12:00:00+24:00", "2026-10-10T12:00:00+05:60", "2026-10-10T12:00:00+aa:bb",
            "2026-10-10T12:00:00ZZ", "2026-10-10T12:00:00Z ", "2026-10-10T12:00:00 Z",
            "2026-10-10T12:00:00UTC", "2026-10-10T12:00:00GMT", "2026-10-10T12:00:00Q",
            "2026-10-10X12:00:00Z", "2026/10/10T12:00:00Z", "2026-10-10T12-00-00Z",
            "2026-13-10T12:00:00Z", "2026-00-10T12:00:00Z", "2026-10-32T12:00:00Z", "2026-10-00T12:00:00Z",
            "2026-10-10T24:00:00Z", "2026-10-10T12:60:00Z", "2026-10-10T12:00:61Z",
            "2026-1-10", "2026-10-1", "26-10-10", "2026-10-10Z", "20261010", "2026-10-1a",
            " 2026-10-10", "2026-10-10 ", "２０２６-10-10",
        ]
        for s in bad { XCTAssertNil(APIDate.parse(s), "should reject \(s.debugDescription)") }
    }

    // MARK: Encoding

    func testEncodingEmitsWholeSecondZuluAndDayString() throws {
        XCTAssertEqual(APIDate.timestampString(noon.addingTimeInterval(0.123456)), "2026-10-10T12:00:00Z")
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "Asia/Tokyo")!
        XCTAssertEqual(APIDate.dayString(noon, calendar: cal), "2026-10-10")
        cal.timeZone = TimeZone(identifier: "Pacific/Kiritimati")!   // UTC+14: already the 11th
        XCTAssertEqual(APIDate.dayString(noon, calendar: cal), "2026-10-11")
        // Round trip: what we send, we can read back.
        XCTAssertEqual(APIDate.parse(APIDate.timestampString(noon)), noon)
    }
}
