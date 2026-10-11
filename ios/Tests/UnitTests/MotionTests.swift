import XCTest
import SwiftUI
@testable import FoodWasteReducer

/// Values asserted here are literals copied from docs/design/MOTION.md (quick easeOut 0.15,
/// standard spring 0.35/0.85, emphasized spring 0.5/0.75, stagger 40 ms per item (20 ms for chart
/// columns) capped at 6 items with a 0.3 s item so the sequence ends by 0.5 s, shimmer 1.2 s,
/// listening pulse 8 pt / 30% / 1.6 s, static ring 4 pt / 25%, list insert 8 pt / 0.3 s, toast 5 s).
/// If MOTION.md changes, change both.
@MainActor
final class MotionTests: XCTestCase {
    func testTokenValues() {
        XCTAssertEqual(Theme.Motion.quick, .easeOut(duration: 0.15))
        XCTAssertEqual(Theme.Motion.standard, .spring(response: 0.35, dampingFraction: 0.85))
        XCTAssertEqual(Theme.Motion.emphasized, .spring(response: 0.5, dampingFraction: 0.75))
        XCTAssertEqual(Theme.Motion.staggerStep, 0.040, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerCap, 6)
        XCTAssertEqual(Theme.Motion.chartStaggerStep, 0.020, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerItem, .easeOut(duration: 0.3))
        XCTAssertEqual(Theme.Motion.staggerItemDuration, 0.3, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.listInsert, .easeOut(duration: 0.3))
        XCTAssertEqual(Theme.Motion.listInsertOffset, 8)
        XCTAssertEqual(Theme.Motion.pulseGrowth, 8)
        XCTAssertEqual(Theme.Motion.pulsePeakOpacity, 0.30, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.pulsePeriod, 1.6, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.pulseStaticWidth, 4)
        XCTAssertEqual(Theme.Motion.pulseStaticOpacity, 0.25, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.pulseLineWidth, 2)
        XCTAssertEqual(Theme.Motion.shimmerHighlightOpacity, 0.65, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.shimmerBandWidth, 0.6, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.shimmerDuration, 1.2, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.oneShotLimit, 0.5, accuracy: 1e-9)
    }

    /// MOTION.md: "5 x 40 ms of delay + a 0.3 s item = 0.5 s"; the whole sequence ends within 0.5 s.
    func testFullStaggerSequenceFitsTheOneShotLimit() {
        let last = Theme.Motion.staggerDelay(index: 1_000) + Theme.Motion.staggerItemDuration
        XCTAssertEqual(last, 0.5, accuracy: 1e-9)
        XCTAssertLessThanOrEqual(last, Theme.Motion.oneShotLimit + 1e-9)
        let chartLast = Theme.Motion.staggerDelay(index: 1_000, step: Theme.Motion.chartStaggerStep)
            + Theme.Motion.staggerItemDuration
        XCTAssertLessThanOrEqual(chartLast, Theme.Motion.oneShotLimit + 1e-9)
    }

    func testTokensAreDistinct() {
        XCTAssertNotEqual(Theme.Motion.quick, Theme.Motion.standard)
        XCTAssertNotEqual(Theme.Motion.standard, Theme.Motion.emphasized)
    }

    func testReduceMotionReturnsQuickFallbackForEveryToken() {
        for a in [Theme.Motion.standard, Theme.Motion.emphasized, Theme.Motion.quick,
                  Animation.linear(duration: 1.2), Animation.spring()] {
            XCTAssertEqual(Theme.Motion.animation(a, reduceMotion: true), Theme.Motion.quick)
        }
    }

    func testReduceMotionOffKeepsTheAnimation() {
        XCTAssertEqual(Theme.Motion.animation(Theme.Motion.emphasized, reduceMotion: false), Theme.Motion.emphasized)
        XCTAssertEqual(Theme.Motion.animation(Theme.Motion.standard, reduceMotion: false), Theme.Motion.standard)
    }

    /// Capped at 6 items: index 5 (the 6th item) is 5 x 40 ms = 0.2 s; items past the 6th share it.
    func testStaggerDelayIs40msPerIndexCappedAtSixItems() {
        XCTAssertEqual(Theme.Motion.staggerDelay(index: 0), 0, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerDelay(index: 1), 0.040, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerDelay(index: 4), 0.160, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerDelay(index: 5), 0.200, accuracy: 1e-9)
        for i in 6...50 { XCTAssertEqual(Theme.Motion.staggerDelay(index: i), 0.200, accuracy: 1e-9, "index \(i)") }
        XCTAssertEqual(Theme.Motion.staggerDelay(index: 3, step: Theme.Motion.chartStaggerStep), 0.060, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerDelay(index: 9, step: Theme.Motion.chartStaggerStep), 0.100, accuracy: 1e-9)
        XCTAssertEqual(Theme.Motion.staggerDelay(index: -3), 0, accuracy: 1e-9, "negative index clamps to 0")
        let delays = (0..<20).map { Theme.Motion.staggerDelay(index: $0) }
        XCTAssertEqual(delays, delays.sorted(), "never decreases")
    }

    func testStaggerRunsOnFirstLoadOnlyNotOnRefresh() {
        let c = StaggerController()
        XCTAssertFalse(c.isActive, "no stagger until the owner asks for one (a refresh never calls restart)")
        XCTAssertEqual(c.generation, 0)
        c.restart()
        XCTAssertTrue(c.isActive)
        XCTAssertEqual(c.generation, 1)
        c.restart()
        XCTAssertEqual(c.generation, 2)
        XCTAssertGreaterThan(StaggerController.window,
                             Theme.Motion.staggerDelay(index: Theme.Motion.staggerCap) + Theme.Motion.staggerItemDuration)
    }

    func testHapticsProviderIsSwappableAndRecords() {
        let saved = Haptics.provider
        defer { Haptics.provider = saved }
        let rec = RecordingHaptics()
        Haptics.provider = rec
        Haptics.success(); Haptics.warning(); Haptics.error(); Haptics.selection(); Haptics.lightImpact()
        XCTAssertEqual(rec.events, [.success, .warning, .error, .selection, .lightImpact])
    }

    // MARK: Undo toast

    func testToastTimingConstants() {
        XCTAssertEqual(UndoToastTiming.duration, .seconds(5))
        XCTAssertGreaterThanOrEqual(UndoToastTiming.assistiveDuration, UndoToastTiming.duration)
        XCTAssertEqual(Theme.Size.minTouch, 44)
    }

    func testToastTimesOutAfterAboutFiveSecondsAndDoesNotCallUndo() async throws {
        var undone = false
        let timedOut = expectation(description: "timeout")
        let dismissed = expectation(description: "dismiss")
        let start = Date()
        var elapsed = 0.0
        let item = UndoToastItem(message: "Removed Spinach", onUndo: { undone = true },
                                 onTimeout: { elapsed = Date().timeIntervalSince(start); timedOut.fulfill() })
        let host = UIHostingController(rootView: UndoToastView(item: item, dismiss: { dismissed.fulfill() }))
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: 402, height: 874))
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer { window.isHidden = true }
        await fulfillment(of: [timedOut, dismissed], timeout: 8)
        XCTAssertFalse(undone)
        XCTAssertGreaterThan(elapsed, 4.5)
        XCTAssertLessThan(elapsed, 6.0, "auto-dismiss at about 5 s, got \(elapsed)")
    }
}
