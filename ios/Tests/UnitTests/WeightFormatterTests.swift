import XCTest
@testable import FoodWasteReducer

/// The API speaks kilograms; the Units preference decides lb/oz or kg/g on screen.
final class WeightFormatterTests: XCTestCase {
    private let us = WeightFormatter(system: .us)
    private let metric = WeightFormatter(system: .metric)

    // MARK: US

    func testUSUnderAPoundShowsWholeOunces() {
        XCTAssertEqual(us.string(kg: 0.1417), "5 oz")           // 5.0 oz
        XCTAssertEqual(us.string(kg: 0.0283495), "1 oz")
        XCTAssertEqual(us.string(kg: 0.2), "7 oz")              // 7.05
        XCTAssertEqual(us.string(kg: 0.4), "14 oz")             // 14.11
    }

    func testUSOverAPoundShowsPoundsToOneDecimal() {
        XCTAssertEqual(us.string(kg: 1.0), "2.2 lb")
        XCTAssertEqual(us.string(kg: 0.64), "1.4 lb")           // the chicken-thighs fixture
        XCTAssertEqual(us.string(kg: 2.5), "5.5 lb")
        XCTAssertEqual(us.string(kg: 4.5359237), "10 lb", "whole pounds drop the .0")
    }

    func testUSBoundaryNearAPoundNeverShows16Oz() {
        // 15.5 oz and up becomes pounds so the label never reads "16 oz".
        for kg in stride(from: 0.43, through: 0.46, by: 0.0005) {
            XCTAssertNotEqual(us.string(kg: kg), "16 oz", "\(kg) kg")
        }
        XCTAssertEqual(us.string(kg: 0.4536), "1 lb")
    }

    func testUSZeroAndTiny() {
        XCTAssertEqual(us.string(kg: 0), "0 oz")
        XCTAssertEqual(us.string(kg: 0.0001), "<1 oz")          // 0.0035 oz
        XCTAssertEqual(us.string(kg: 0.0132), "<1 oz")          // 0.47 oz rounds below half
        XCTAssertEqual(us.string(kg: 0.0142), "1 oz")           // 0.50 oz
    }

    func testUSNegativeClampsToZero() {
        XCTAssertEqual(us.string(kg: -3), "0 oz")
        XCTAssertEqual(us.string(kg: -0.0), "0 oz")
    }

    func testUSLarge() {
        XCTAssertEqual(us.string(kg: 100), "220.5 lb")
        XCTAssertEqual(us.string(kg: 100_000), "220462.3 lb", "est_weight_kg is bounded to 100,000")
    }

    // MARK: Metric

    func testMetricUnderAKiloShowsWholeGrams() {
        XCTAssertEqual(metric.string(kg: 0.25), "250 g")
        XCTAssertEqual(metric.string(kg: 0.64), "640 g")
        XCTAssertEqual(metric.string(kg: 0.0004), "<1 g")
        XCTAssertEqual(metric.string(kg: 0.0005), "1 g", "0.5 g rounds up")
        XCTAssertEqual(metric.string(kg: 0.9994), "999 g")
    }

    func testMetricAtAKiloAndAboveShowsKilograms() {
        XCTAssertEqual(metric.string(kg: 1), "1 kg")
        XCTAssertEqual(metric.string(kg: 1.24), "1.2 kg")
        XCTAssertEqual(metric.string(kg: 1.26), "1.3 kg")
        XCTAssertEqual(metric.string(kg: 12), "12 kg")
        XCTAssertEqual(metric.string(kg: 0.9996), "1 kg", "999.6 g must not read 1000 g")
    }

    func testMetricZeroNegativeLarge() {
        XCTAssertEqual(metric.string(kg: 0), "0 g")
        XCTAssertEqual(metric.string(kg: -1), "0 g")
        XCTAssertEqual(metric.string(kg: 100_000), "100000 kg")
    }

    // MARK: Spoken

    func testSpokenSpellsOutUnitsAndHandlesSingular() {
        XCTAssertEqual(us.spoken(kg: 0.64), "1.4 pounds")
        XCTAssertEqual(us.spoken(kg: 0.4536), "1 pound")
        XCTAssertEqual(us.spoken(kg: 0.1417), "5 ounces")
        XCTAssertEqual(us.spoken(kg: 0.0283495), "1 ounce")
        XCTAssertEqual(metric.spoken(kg: 0.25), "250 grams")
        XCTAssertEqual(metric.spoken(kg: 1), "1 kilogram")
        XCTAssertEqual(metric.spoken(kg: 1.2), "1.2 kilograms")
        XCTAssertEqual(metric.spoken(kg: 0.001), "1 gram")
    }

    func testSpokenNeverContainsAbbreviationOrSymbol() {
        for kg in [0, 0.0001, 0.1, 0.64, 1, 12.3] {
            for f in [us, metric] {
                let s = f.spoken(kg: kg)
                XCTAssertFalse(s.contains("<"), "VoiceOver would read a bare '<': \(s)")
                for abbr in [" oz", " lb", " kg", " g"] where s.hasSuffix(abbr) { XCTFail("unspoken unit: \(s)") }
            }
        }
    }

    // MARK: Preference switching

    func testSamePayloadRendersDifferentlyPerUnit() {
        let kg = 0.64
        XCTAssertEqual(WeightFormatter(system: .us).string(kg: kg), "1.4 lb")
        XCTAssertEqual(WeightFormatter(system: .metric).string(kg: kg), "640 g")
    }

    func testStoredPreferenceDefaultsToUSAndRoundTrips() {
        let suite = "WeightFormatterTests-\(UUID().uuidString)"
        let d = UserDefaults(suiteName: suite)!
        defer { d.removePersistentDomain(forName: suite) }
        XCTAssertEqual(UnitSystem.stored(in: d), .us, "unset means US")
        d.set("metric", forKey: UnitSystem.storageKey)
        XCTAssertEqual(UnitSystem.stored(in: d), .metric)
        d.set("us", forKey: UnitSystem.storageKey)
        XCTAssertEqual(UnitSystem.stored(in: d), .us)
        d.set("stone", forKey: UnitSystem.storageKey)
        XCTAssertEqual(UnitSystem.stored(in: d), .us, "an unreadable value falls back to US")
        d.set(42, forKey: UnitSystem.storageKey)
        XCTAssertEqual(UnitSystem.stored(in: d), .us)
    }

    func testUnitSystemRawValuesAndStorageKeyAreStable() {
        XCTAssertEqual(UnitSystem.storageKey, "units")
        XCTAssertEqual(UnitSystem.us.rawValue, "us")
        XCTAssertEqual(UnitSystem.metric.rawValue, "metric")
        XCTAssertEqual(UnitSystem.allCases.count, 2)
        XCTAssertEqual(UnitSystem.default, .us)
    }

    func testConversionConstants() {
        XCTAssertEqual(WeightFormatter.ouncesPerKg, 35.27396195, accuracy: 1e-8)
        XCTAssertEqual(WeightFormatter.poundsPerKg * 16, WeightFormatter.ouncesPerKg, accuracy: 1e-4)
    }

    func testMonotonicNoNegativeOrEmptyStrings() {
        var last = -1.0
        for i in 0...2000 {
            let kg = Double(i) / 500
            XCTAssertFalse(us.string(kg: kg).isEmpty)
            XCTAssertFalse(metric.string(kg: kg).isEmpty)
            XCTAssertGreaterThan(kg, last); last = kg
        }
    }
}
