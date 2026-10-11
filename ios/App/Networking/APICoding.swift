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
    /// Parses `2026-10-10T12:00:00Z`, with or without fractional seconds, or a `yyyy-MM-dd` calendar
    /// date (returned as local midnight so calendar-day maths matches what the user sees).
    static func parse(_ raw: String, calendar: Calendar = .current) -> Date? {
        if let d = withFraction.date(from: raw) ?? plain.date(from: raw) { return d }
        let parts = raw.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3, raw.count == 10 else { return nil }
        return calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    static func timestampString(_ date: Date) -> String { plain.string(from: date) }

    /// `yyyy-MM-dd` in the given calendar, for `predicted_expiry` request fields.
    static func dayString(_ date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }

    // ISO8601DateFormatter is thread-safe for date(from:)/string(from:).
    nonisolated(unsafe) private static let withFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f
    }()
    nonisolated(unsafe) private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime]; return f
    }()
}
