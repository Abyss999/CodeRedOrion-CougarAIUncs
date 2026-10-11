import Foundation

/// JSON coding shared by the live client, the mock and tests.
enum APICoding {
    static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        d.dateDecodingStrategy = .custom { decoder in
            let raw = try decoder.singleValueContainer().decode(String.self)
            if let date = APIDate.parse(raw) { return date }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                    debugDescription: "Unrecognised date \(raw)"))
        }
        return d
    }()

    static let encoder: JSONEncoder = {
        let e = JSONEncoder()
        e.keyEncodingStrategy = .convertToSnakeCase
        e.dateEncodingStrategy = .custom { date, encoder in
            var c = encoder.singleValueContainer()
            try c.encode(APIDate.timestampString(date))
        }
        return e
    }()
}

enum APIDate {
    /// Parses what the backend emits (Python `isoformat()`, see `backend/app/routes/_util.py::iso`):
    /// - timestamps `YYYY-MM-DDTHH:MM:SS`, optionally with 1-9 fractional digits (Python emits 6),
    ///   followed by `Z`, `±HH:MM` or `±HHMM` (a missing zone is read as UTC, the API's zone);
    /// - calendar dates `YYYY-MM-DD` (e.g. `predicted_expiry`, `week`), returned as local midnight
    ///   so calendar-day maths matches what the user sees.
    static func parse(_ raw: String, calendar: Calendar = .current) -> Date? {
        let b = Array(raw.utf8)
        if b.count == 10 {
            guard let (y, mo, d) = ymd(b) else { return nil }
            return calendar.date(from: DateComponents(year: y, month: mo, day: d))
        }
        return timestamp(b)
    }

    /// Request timestamps: `2026-10-10T12:00:00Z` (whole seconds, UTC). Python 3.11+
    /// `datetime.fromisoformat` accepts the `Z` suffix.
    static func timestampString(_ date: Date) -> String { plain.string(from: date) }

    /// `yyyy-MM-dd` in the given calendar, for `predicted_expiry` request fields.
    static func dayString(_ date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }

    // MARK: - Parsing

    private static func digits(_ b: [UInt8], _ i: Int, _ n: Int) -> Int? {
        guard i + n <= b.count else { return nil }
        var v = 0
        for k in i..<(i + n) {
            let c = b[k]
            guard c >= 0x30, c <= 0x39 else { return nil }
            v = v * 10 + Int(c - 0x30)
        }
        return v
    }

    private static func ymd(_ b: [UInt8]) -> (Int, Int, Int)? {
        guard b.count >= 10, b[4] == UInt8(ascii: "-"), b[7] == UInt8(ascii: "-"),
              let y = digits(b, 0, 4), let mo = digits(b, 5, 2), let d = digits(b, 8, 2),
              (1...12).contains(mo), (1...31).contains(d) else { return nil }
        return (y, mo, d)
    }

    private static func timestamp(_ b: [UInt8]) -> Date? {
        // YYYY-MM-DDTHH:MM:SS = 19 bytes minimum.
        guard b.count >= 19, let (y, mo, d) = ymd(b),
              b[10] == UInt8(ascii: "T") || b[10] == UInt8(ascii: "t") || b[10] == UInt8(ascii: " "),
              b[13] == UInt8(ascii: ":"), b[16] == UInt8(ascii: ":"),
              let h = digits(b, 11, 2), let mi = digits(b, 14, 2), let s = digits(b, 17, 2),
              h <= 23, mi <= 59, s <= 60 else { return nil }
        var i = 19
        var fraction = 0.0
        if i < b.count, b[i] == UInt8(ascii: ".") {
            i += 1
            var value = 0, divisor = 1
            let fracStart = i
            while i < b.count, b[i] >= 0x30, b[i] <= 0x39, i - fracStart < 9 {
                value = value * 10 + Int(b[i] - 0x30)
                divisor *= 10
                i += 1
            }
            guard i > fracStart else { return nil }
            fraction = Double(value) / Double(divisor)
        }
        var offset = 0
        if i == b.count {
            offset = 0
        } else if b[i] == UInt8(ascii: "Z") || b[i] == UInt8(ascii: "z") {
            guard i + 1 == b.count else { return nil }
        } else if b[i] == UInt8(ascii: "+") || b[i] == UInt8(ascii: "-") {
            let sign = b[i] == UInt8(ascii: "-") ? -1 : 1
            let rest = b.count - i - 1
            guard let oh = digits(b, i + 1, 2), oh <= 23 else { return nil }
            let om: Int?
            if rest == 5, b[i + 3] == UInt8(ascii: ":") { om = digits(b, i + 4, 2) }
            else if rest == 4 { om = digits(b, i + 3, 2) }
            else { om = nil }
            guard let om, om <= 59 else { return nil }
            offset = sign * (oh * 3600 + om * 60)
        } else {
            return nil
        }
        let comps = DateComponents(year: y, month: mo, day: d, hour: h, minute: mi, second: s)
        guard let base = utc.date(from: comps) else { return nil }
        return base.addingTimeInterval(fraction - Double(offset))
    }

    private static let utc: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(secondsFromGMT: 0)!
        return c
    }()

    // ISO8601DateFormatter is thread-safe for string(from:).
    nonisolated(unsafe) private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f
    }()
}
