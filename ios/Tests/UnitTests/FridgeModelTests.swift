import XCTest
@testable import FoodWasteReducer

/// Records remove/restore calls and forwards everything to a `MockAPIClient`.
actor SpyAPIClient: APIClient {
    struct RemoveCall: Equatable { let id: String; let outcome: RemoveOutcome; let reason: WasteReason?; let recipient: String? }
    let inner: MockAPIClient
    private(set) var removes: [RemoveCall] = []
    private(set) var restores: [String] = []
    private(set) var lists = 0
    init(_ inner: MockAPIClient) { self.inner = inner }

    func signup(email: String, password: String, displayName: String) async throws -> AuthSession { try await inner.signup(email: email, password: password, displayName: displayName) }
    func login(email: String, password: String) async throws -> AuthSession { try await inner.login(email: email, password: password) }
    func deleteAccount() async throws { try await inner.deleteAccount() }
    func listItems(storage: Storage?, groupBy: ItemGrouping?) async throws -> ItemListing { lists += 1; return try await inner.listItems(storage: storage, groupBy: groupBy) }
    func createItems(_ items: [NewItem]) async throws -> [Item] { try await inner.createItems(items) }
    func patchItem(id: String, _ patch: ItemPatch) async throws -> Item { try await inner.patchItem(id: id, patch) }
    func removeItem(id: String, outcome: RemoveOutcome, wasteReason: WasteReason?, recipientId: String?) async throws -> Item {
        removes.append(.init(id: id, outcome: outcome, reason: wasteReason, recipient: recipientId))
        return try await inner.removeItem(id: id, outcome: outcome, wasteReason: wasteReason, recipientId: recipientId)
    }
    func restoreItem(id: String) async throws -> Item { restores.append(id); return try await inner.restoreItem(id: id) }
    func fromPhoto(imageData: Data, mode: PhotoMode) async throws -> CandidatesResponse { try await inner.fromPhoto(imageData: imageData, mode: mode) }
    func parseText(_ text: String) async throws -> [Candidate] { try await inner.parseText(text) }
    func impact(range: ImpactRange) async throws -> Impact { try await inner.impact(range: range) }
    func tips() async throws -> [Tip] { try await inner.tips() }
    func recipesSuggest(maxResults: Int?, dietary: [String]?) async throws -> [Recipe] { try await inner.recipesSuggest(maxResults: maxResults, dietary: dietary) }
}

@MainActor
final class FridgeModelTests: XCTestCase {
    private var haptics: RecordingHaptics!
    private var savedProvider: HapticsProviding!

    override func setUp() async throws {
        savedProvider = Haptics.provider
        haptics = RecordingHaptics()
        Haptics.provider = haptics
    }
    override func tearDown() async throws { Haptics.provider = savedProvider }

    private func make(_ fixture: MockFixture = .fridge, _ behavior: MockAPIClient.Behavior = .init(delay: .zero))
        -> (FridgeModel, SpyAPIClient, MockAPIClient) {
        let mock = MockAPIClient(fixture: fixture, behavior: behavior)
        let spy = SpyAPIClient(mock)
        return (FridgeModel(api: spy), spy, mock)
    }

    private func until(_ timeout: TimeInterval = 3, _ cond: () async -> Bool, file: StaticString = #filePath, line: UInt = #line) async {
        let end = Date().addingTimeInterval(timeout)
        while Date() < end { if await cond() { return }; try? await Task.sleep(for: .milliseconds(20)) }
        XCTFail("condition not met in \(timeout) s", file: file, line: line)
    }

    private func ids(_ m: FridgeModel, _ s: Storage = .fridge) -> [String] {
        guard case .content(let secs) = m.state(for: s) else { return [] }
        return secs.flatMap { $0.items.map(\.id) }
    }
    private func groups(_ m: FridgeModel) -> [FoodGroup] {
        guard case .content(let secs) = m.state(for: .fridge) else { return [] }
        return secs.map(\.foodGroup)
    }
    private func item(_ m: FridgeModel, _ id: String) -> Item {
        guard case .content(let secs) = m.state(for: .fridge) else { fatalError("no content") }
        return secs.flatMap(\.items).first { $0.id == id }!
    }
    private func serverItem(_ mock: MockAPIClient, _ id: String) async -> Item { await mock.currentItems().first { $0.id == id }! }

    // MARK: Loading and states

    func testStartsLoadingThenGroupsInDesignOrder() async {
        let (m, _, _) = make()
        guard case .loading = m.state(for: .fridge) else { return XCTFail("should start in .loading") }
        await m.loadIfNeeded(.fridge)
        XCTAssertEqual(groups(m), [.protein, .veggies, .fruit, .dairy])
        XCTAssertEqual(ids(m), ["item-chicken", "item-eggs", "item-spinach", "item-carrots", "item-strawberries",
                                "item-bananas", "item-yogurt", "item-oatmilk"])
    }

    func testEmptyAndErrorStatesAndRetry() async {
        let (e, _, _) = make(.empty)
        await e.loadIfNeeded(.fridge)
        guard case .empty = e.state(for: .fridge) else { return XCTFail("empty fixture → .empty") }

        var b = MockAPIClient.Behavior(delay: .zero); b.failFirst["listItems"] = 1
        let (m, _, _) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        guard case .error = m.state(for: .fridge) else { return XCTFail("failure → .error") }
        await m.retry(.fridge)
        XCTAssertEqual(groups(m).count, 4, "retry loads content")
    }

    func testStorageFilterIsPerSegment() async {
        let (m, _, _) = make()
        await m.loadIfNeeded(.pantry)
        guard case .empty = m.state(for: .pantry) else { return XCTFail("fridge fixture has no pantry items") }
        guard case .loading = m.state(for: .fridge) else { return XCTFail("fridge not loaded yet") }
    }

    func testStaggerOnlyOnFirstLoadPerStorage() async {
        let (m, spy, _) = make()
        await m.loadIfNeeded(.fridge)
        XCTAssertEqual(m.staggerRestarts, 1)
        await m.loadIfNeeded(.fridge)          // no second fetch
        let lists = await spy.lists
        XCTAssertEqual(lists, 1)
        await m.refresh()
        await m.refresh()
        XCTAssertEqual(m.staggerRestarts, 1, "refresh must not restart the stagger")
        await m.loadIfNeeded(.pantry)          // empty: nothing to stagger
        XCTAssertEqual(m.staggerRestarts, 1)
    }

    func testRefreshFailureWithContentKeepsRowsAndShowsBanner() async {
        let (m, _, mock) = make()
        await m.loadIfNeeded(.fridge)
        await mock.setFailNetwork(true)
        await m.refresh()
        XCTAssertEqual(ids(m).count, 8, "rows stay on a failed refresh")
        XCTAssertNotNil(m.banner)
        XCTAssertNotNil(m.banner?.retry)
    }

    // MARK: Remove (optimistic)

    func testRemoveIsImmediateAndShowsToast() async {
        let (m, spy, mock) = make()
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-chicken"), choice: .init(outcome: .used), reduceMotion: false)
        // Synchronous: the row is gone before any await.
        XCTAssertFalse(ids(m).contains("item-chicken"))
        XCTAssertEqual(m.toast?.message, "Chicken thighs removed")
        await until { await spy.removes.count == 1 }
        let call = await spy.removes.first
        XCTAssertEqual(call, .init(id: "item-chicken", outcome: .used, reason: nil, recipient: nil))
        let server = await serverItem(mock, "item-chicken")
        XCTAssertEqual(server.outcome, .used)
        XCTAssertTrue(haptics.events.isEmpty, "the model plays no haptic on success (the view does): \(haptics.events)")
    }

    func testThrownOutSendsReasonAndDonatedSendsRecipient() async {
        let (m, spy, mock) = make()
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-strawberries"), choice: .init(outcome: .thrownOut, wasteReason: .forgot), reduceMotion: false)
        m.remove(item(m, "item-spinach"), choice: .init(outcome: .donated, recipientId: "user-marcus"), reduceMotion: true)
        await until { await spy.removes.count == 2 }
        let calls = await spy.removes
        XCTAssertEqual(calls[0], .init(id: "item-strawberries", outcome: .thrownOut, reason: .forgot, recipient: nil))
        XCTAssertEqual(calls[1], .init(id: "item-spinach", outcome: .donated, reason: nil, recipient: "user-marcus"))
        await until { await self.serverItem(mock, "item-spinach").share?.status == .fulfilled }
        XCTAssertEqual(m.toast?.message, "Baby spinach removed", "a second removal replaces the toast")
    }

    func testRemovingLastItemOfAGroupDropsTheSection() async {
        let (m, _, _) = make()
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-chicken"), choice: .init(outcome: .used), reduceMotion: false)
        m.remove(item(m, "item-eggs"), choice: .init(outcome: .used), reduceMotion: false)
        XCTAssertEqual(groups(m), [.veggies, .fruit, .dairy])
    }

    func testFailedRemoveRollsBackWithBannerAndErrorHaptic() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failures["removeItem"] = .network("offline")
        let (m, _, mock) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        let before = ids(m)
        m.remove(item(m, "item-spinach"), choice: .init(outcome: .used), reduceMotion: false)
        await until { self.ids(m) == before }
        XCTAssertEqual(ids(m), before, "row returns to its original position")
        XCTAssertNil(m.toast, "no Undo toast for a failed remove")
        XCTAssertEqual(m.banner?.message.contains("Baby spinach"), true, m.banner?.message ?? "nil")
        XCTAssertNotNil(m.banner?.retry)
        XCTAssertEqual(haptics.events, [.error])
        let server = await serverItem(mock, "item-spinach")
        XCTAssertFalse(server.isRemoved)
        // Retry from the banner once the server recovers.
        await mock.setFailure(nil, for: "removeItem")
        m.banner?.retry?()
        await until { await self.serverItem(mock, "item-spinach").isRemoved }
        XCTAssertFalse(ids(m).contains("item-spinach"))
    }

    func testRefreshRacingARemovalDoesNotResurrectTheRow() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.delays["removeItem"] = .milliseconds(400)
        let (m, _, _) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-eggs"), choice: .init(outcome: .used), reduceMotion: false)
        await m.refresh()   // server still has eggs active
        XCTAssertFalse(ids(m).contains("item-eggs"))
    }

    // MARK: Undo

    func testUndoRestoresAtSamePositionAndServer() async {
        let (m, spy, mock) = make()
        await m.loadIfNeeded(.fridge)
        let before = ids(m)
        m.remove(item(m, "item-carrots"), choice: .init(outcome: .donated), reduceMotion: false)
        await until { await self.serverItem(mock, "item-carrots").isRemoved }
        let hapticsBefore = haptics.events
        m.toast?.onUndo()
        XCTAssertEqual(ids(m), before, "Undo puts the row back immediately, in place")
        await until { await spy.restores == ["item-carrots"] }
        await until { await !self.serverItem(mock, "item-carrots").isRemoved }
        let server = await serverItem(mock, "item-carrots")
        XCTAssertEqual(server.share?.status, .open, "Undo reopens the listing the donation fulfilled")
        XCTAssertEqual(haptics.events, hapticsBefore, "Undo plays no haptic")
        XCTAssertNil(m.banner)
    }

    func testUndoBeforeRemoveSettlesStillRestores() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.delays["removeItem"] = .milliseconds(300)
        let (m, spy, mock) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-eggs"), choice: .init(outcome: .used), reduceMotion: false)
        m.toast?.onUndo()
        XCTAssertTrue(ids(m).contains("item-eggs"))
        await until { await spy.restores.count == 1 }
        let server = await serverItem(mock, "item-eggs")
        XCTAssertFalse(server.isRemoved, "server ends active after remove-then-restore")
    }

    func testUndoAfterFailedRemoveDoesNotCallRestoreOrBanner() async {
        var b = MockAPIClient.Behavior(delay: .zero)
        b.failures["removeItem"] = .network("offline"); b.delays["removeItem"] = .milliseconds(300)
        let (m, spy, _) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-eggs"), choice: .init(outcome: .used), reduceMotion: false)
        m.toast?.onUndo()
        try? await Task.sleep(for: .milliseconds(600))
        let restores = await spy.restores
        XCTAssertEqual(restores, [])
        XCTAssertNil(m.banner, "nothing to report: the person already undid it")
        XCTAssertEqual(ids(m).filter { $0 == "item-eggs" }.count, 1, "no duplicate row")
    }

    func testFailedRestoreRemovesAgainWithBanner() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failures["restoreItem"] = .network("offline")
        let (m, _, mock) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-yogurt"), choice: .init(outcome: .used), reduceMotion: false)
        await until { await self.serverItem(mock, "item-yogurt").isRemoved }
        m.toast?.onUndo()
        await until { !self.ids(m).contains("item-yogurt") && m.banner != nil }
        XCTAssertNotNil(m.banner?.retry, "a network failure offers Try again")
        XCTAssertEqual(haptics.events, [.error])
    }

    func testRestoreWindowExpiredHasNoRetry() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failures["restoreItem"] = .restoreWindowExpired
        let (m, _, mock) = make(.fridge, b)
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-yogurt"), choice: .init(outcome: .used), reduceMotion: false)
        await until { await self.serverItem(mock, "item-yogurt").isRemoved }
        m.toast?.onUndo()
        await until { m.banner != nil }
        XCTAssertNil(m.banner?.retry)
        XCTAssertTrue(m.banner?.message.contains("too late") ?? false, m.banner?.message ?? "")
    }

    func testToastTimeoutKeepsRemoval() async {
        let (m, spy, mock) = make()
        await m.loadIfNeeded(.fridge)
        m.remove(item(m, "item-oatmilk"), choice: .init(outcome: .used), reduceMotion: false)
        m.toast?.onTimeout()
        m.toast = nil
        await m.refresh()
        XCTAssertFalse(ids(m).contains("item-oatmilk"))
        let restores = await spy.restores
        XCTAssertEqual(restores, [])
        let server = await serverItem(mock, "item-oatmilk")
        XCTAssertTrue(server.isRemoved)
    }

    // MARK: Text

    func testSheetAndRowText() async {
        let (m, _, _) = make()
        await m.loadIfNeeded(.fridge)
        XCTAssertEqual(ItemText.sheetMeta(item(m, "item-spinach")), "Veggies · 5 oz · expires tomorrow · on Share")
        XCTAssertEqual(ItemText.meta(item(m, "item-strawberries")), "Photo check: looks spoiled")
        XCTAssertTrue(ItemText.meta(item(m, "item-bananas")).contains("photo check: ripe"))
        XCTAssertEqual(ItemText.quantity(item(m, "item-eggs")), "8")
        XCTAssertEqual(ItemText.quantity(item(m, "item-chicken")), "1.4 lb")
        XCTAssertTrue(ItemText.hasOpenListing(item(m, "item-carrots")))
        XCTAssertFalse(ItemText.hasOpenListing(item(m, "item-eggs")))
    }

    func testListingFixtureMatchesArtboard() {
        let items = MockData.items(for: .listing)
        let spinach = items.first { $0.id == "item-spinach" }!
        XCTAssertEqual(spinach.share?.status, .open)
        XCTAssertEqual(spinach.share?.claimedBy?.id, "user-marcus")
        XCTAssertEqual(spinach.share?.claimedBy?.name, "Marcus Ojeda")
        XCTAssertNil(items.first { $0.id == "item-carrots" }!.share?.claimedBy)
        XCTAssertEqual(MockFixture(name: "listing"), .listing)
    }

    func testMockRejectsRecipientOnNonDonated() async {
        let mock = MockAPIClient(fixture: .fridge, behavior: .init(delay: .zero))
        do { _ = try await mock.removeItem(id: "item-eggs", outcome: .used, wasteReason: nil, recipientId: "user-marcus"); XCTFail() }
        catch let e as APIError { guard case .server(400, "validation_error", _) = e else { return XCTFail("\(e)") } }
        catch { XCTFail("\(error)") }
    }
}
