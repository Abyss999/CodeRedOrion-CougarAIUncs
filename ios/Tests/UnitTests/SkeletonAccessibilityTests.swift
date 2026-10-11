import XCTest
import SwiftUI
@testable import FoodWasteReducer

/// Skeletons expose ONE accessibility element per list, `<screen>.loading`, labelled "Loading"
/// (IOS-9: previously every row was its own "Loading" VoiceOver stop). No per-row ids.
@MainActor
final class SkeletonAccessibilityTests: XCTestCase {
    func testLoadingIdentifierFormat() {
        XCTAssertEqual(AccessibilityID.State.loading("fridge"), "fridge.loading")
        XCTAssertEqual(AccessibilityID.State.loading("home"), "home.loading")
        XCTAssertEqual(AccessibilityID.State.empty("fridge"), "fridge.empty")
        XCTAssertEqual(AccessibilityID.State.error("fridge"), "fridge.error")
        XCTAssertEqual(AccessibilityID.State.retry("fridge"), "fridge.error.retry")
    }

    func testSkeletonListIsASingleLoadingElement() throws {
        for count in [1, 5] {
            let elements = try accessibleLeaves(of: SkeletonList(screen: "fridge", count: count))
            XCTAssertEqual(elements.count, 1, "count \(count): one VoiceOver stop, got \(elements.map(describe))")
            let e = try XCTUnwrap(elements.first)
            XCTAssertEqual(e.accessibilityLabel, "Loading")
            XCTAssertEqual(identifier(e), "fridge.loading")
        }
    }

    func testSkeletonListHasNoPerRowIdentifiers() throws {
        let ids = try accessibleLeaves(of: SkeletonList(screen: "home", count: 5))
            .compactMap(identifier)
        XCTAssertEqual(ids, ["home.loading"])
        XCTAssertFalse(ids.contains { $0.contains(".skeleton.") }, "no <screen>.skeleton.<n> ids: \(ids)")
    }

    // MARK: Helpers

    private var window: UIWindow?

    override func tearDown() {
        window?.isHidden = true
        window = nil
        super.tearDown()
    }

    /// SwiftUI only builds its accessibility tree when an assistive client is attached. A unit-test
    /// host has none, so turn on the automation flag the way XCUITest does (test target only).
    private static let axEnabled: Bool = {
        guard let h = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let sym = dlsym(h, "_AXSSetAutomationEnabled") else { return false }
        typealias Fn = @convention(c) (Bool) -> Void
        unsafeBitCast(sym, to: Fn.self)(true)
        return true
    }()

    /// Hosts `view` in a key window and returns the leaf accessibility elements SwiftUI exposes.
    private func accessibleLeaves<V: View>(of view: V) throws -> [NSObject] {
        _ = Self.axEnabled
        let host = UIHostingController(rootView: view.padding().environment(\.reduceMotionOverride, true))
        let w = UIWindow(frame: CGRect(x: 0, y: 0, width: 402, height: 874))
        w.rootViewController = host
        w.makeKeyAndVisible()
        window = w
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.3))
        var out: [NSObject] = []
        collect(host.view, into: &out)
        if out.isEmpty { throw XCTSkip("SwiftUI exposed no accessibility elements in this host") }
        return out
    }

    private func collect(_ node: NSObject, into out: inout [NSObject]) {
        if node.isAccessibilityElement { out.append(node); return }
        var children: [NSObject] = []
        if let els = node.accessibilityElements as? [NSObject], !els.isEmpty {
            children = els
        } else {
            let n = node.accessibilityElementCount()
            if n != NSNotFound, n > 0 {
                children = (0..<n).compactMap { node.accessibilityElement(at: $0) as? NSObject }
            }
            if children.isEmpty, let v = node as? UIView { children = v.subviews }
        }
        for c in children { collect(c, into: &out) }
    }

    /// SwiftUI's accessibility nodes answer `accessibilityIdentifier` without declaring
    /// `UIAccessibilityIdentification`, so read it by selector.
    private func identifier(_ o: NSObject) -> String? {
        if let id = (o as? UIAccessibilityIdentification)?.accessibilityIdentifier { return id }
        let sel = NSSelectorFromString("accessibilityIdentifier")
        guard o.responds(to: sel) else { return nil }
        return o.perform(sel)?.takeUnretainedValue() as? String
    }

    private func describe(_ o: NSObject) -> String {
        "\(o.accessibilityLabel ?? "nil")#\(identifier(o) ?? "nil")"
    }
}
