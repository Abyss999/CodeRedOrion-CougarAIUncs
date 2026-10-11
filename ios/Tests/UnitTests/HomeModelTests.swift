import XCTest
@testable import FoodWasteReducer

/// Home tab state (SCREENS #4, #26, #28): what loads, in what order, and how it degrades.
/// Mock-backed, zero delay. The wire shape of the impact call is pinned in `HomeRequestShapeTests`.
@MainActor
final class HomeModelTests: XCTestCase {
    private func make(_ fixture: MockFixture = .fridge, _ behavior: MockAPIClient.Behavior = .init(delay: .zero))
        -> (HomeModel, MockAPIClient) {
        let mock = MockAPIClient(fixture: fixture, behavior: behavior)
        return (HomeModel(api: mock), mock)
    }

    private func isContent(_ s: HomeModel.ScreenState) -> Bool { if case .content = s { true } else { false } }
    private func isEmpty(_ s: HomeModel.ScreenState) -> Bool { if case .empty = s { true } else { false } }
    private func isError(_ s: HomeModel.ScreenState) -> Bool { if case .error = s { true } else { false } }
    private func isLoading(_ s: HomeModel.ScreenState) -> Bool { if case .loading = s { true } else { false } }

    // MARK: Content

    func testStartsLoadingThenShowsContent() async {
        let (m, _) = make()
        XCTAssertTrue(isLoading(m.state))
        await m.loadIfNeeded()
        XCTAssertTrue(isContent(m.state))
    }

    func testUseFirstIsTheThreeSoonestExpiringActiveItems() async {
        let (m, _) = make()
        await m.loadIfNeeded()
        // fridge fixture: chicken 0 d, spinach 1 d, strawberries 2 d, then bananas / yogurt 3 d.
        XCTAssertEqual(m.useFirst.map(\.id), ["item-chicken", "item-spinach", "item-strawberries"])
        XCTAssertLessThanOrEqual(m.useFirst.count, HomeModel.useFirstLimit)
    }

    func testRemovedItemsNeverAppearInUseFirst() async throws {
        let (m, mock) = make()
        _ = try await mock.removeItem(id: "item-chicken", outcome: .used, wasteReason: nil, recipient: .default)
        await m.loadIfNeeded()
        XCTAssertFalse(m.useFirst.map(\.id).contains("item-chicken"))
        XCTAssertEqual(m.useFirst.first?.id, "item-spinach")
    }

    func testSoonestPutsUndatedItemsLastAndBreaksTiesByName() {
        func item(_ id: String, _ name: String, _ expiry: Date?) -> Item {
            Item(id: id, ownerId: "u", groupId: nil, name: name, category: .dairy, foodGroup: .dairy,
                 storage: .fridge, quantity: 1, unit: "pc", estWeightKg: 0.5, estPrice: 1, source: "photo",
                 addedAt: Date(), predictedExpiry: expiry, expirySource: "default",
                 removedAt: nil, outcome: nil, wasteReason: nil, removedAfterExpiry: nil,
                 freshness: nil, freshnessCheckedAt: nil, confidence: nil, share: nil)
        }
        let d = Date(timeIntervalSince1970: 1_800_000_000)
        let sorted = HomeModel.soonest([item("n", "Zed", nil), item("b", "Beta", d), item("a", "Alpha", d),
                                        item("late", "Late", d.addingTimeInterval(86_400)), item("n2", "Apple", nil)], limit: 10)
        XCTAssertEqual(sorted.map(\.id), ["a", "b", "late", "n2", "n"])
    }

    func testSavedKgComesFromTheMonthRange() async {
        let (m, _) = make()
        await m.loadIfNeeded()
        let month = MockData.impact(range: .month).saved.kg
        let week = MockData.impact(range: .week).saved.kg
        XCTAssertNotEqual(month, week, "fixtures must differ for this check to mean anything")
        XCTAssertEqual(m.savedKg, month)
    }

    func testPillTextIsPoundsThroughWeightFormatter() async throws {
        let (m, _) = make()
        await m.loadIfNeeded()
        let kg = try XCTUnwrap(m.savedKg)
        XCTAssertEqual(kg, MockData.impact(range: .month).saved.kg)
        XCTAssertEqual(WeightFormatter(system: .us).string(kg: kg), WeightFormatter(system: .us).string(kg: MockData.impact(range: .month).saved.kg))
        XCTAssertTrue(WeightFormatter(system: .us).string(kg: kg).hasSuffix(" lb"), "a month of mock data is over a pound")
        XCTAssertTrue(WeightFormatter(system: .metric).string(kg: kg).hasSuffix(" kg"))
    }

    func testTipIsTheFirstTipOneObservation() async throws {
        let (m, _) = make()
        await m.loadIfNeeded()
        let tip = try XCTUnwrap(m.tip)
        XCTAssertEqual(tip, MockData.tips.first)
        XCTAssertLessThanOrEqual(tip.message.count, 100, "GET /tips lines run up to 100 characters")
    }

    func testCookTonightUsesTheFirstSuggestedRecipeWithItemObjects() async throws {
        let (m, _) = make()
        await m.loadIfNeeded()
        let r = try XCTUnwrap(m.recipe)
        XCTAssertEqual(r.title, "Chicken and spinach skillet")
        XCTAssertEqual(r.usesItems.map(\.itemId), ["item-chicken", "item-spinach"])
        XCTAssertFalse(m.recipesUnavailable)
    }

    func testEyebrowCountsItemsExpiringWithinTheWeek() {
        let now = Date()
        let cal = Calendar.current
        func d(_ n: Int) -> Date { cal.date(byAdding: .day, value: n, to: cal.startOfDay(for: now))! }
        func recipe(_ uses: [RecipeItem]) -> Recipe {
            Recipe(title: "R", minutes: 35, servings: 2, usesItems: uses, missingItems: [], steps: [], macros: nil, macrosEstimated: true)
        }
        let soon = RecipeItem(itemId: "a", name: "A", predictedExpiry: d(0))
        let edge = RecipeItem(itemId: "b", name: "B", predictedExpiry: d(7))
        let later = RecipeItem(itemId: "c", name: "C", predictedExpiry: d(8))
        XCTAssertEqual(HomeModel.eyebrow(for: recipe([soon, edge, later]), now: now), "Uses 2 items expiring this week")
        XCTAssertEqual(HomeModel.eyebrow(for: recipe([soon, later]), now: now), "Uses 1 item expiring this week")
        XCTAssertEqual(HomeModel.eyebrow(for: recipe([later]), now: now), "Uses 1 of your item")
        XCTAssertEqual(HomeModel.eyebrow(for: recipe([]), now: now), "Made with what you have")
    }

    func testRecipeDetailLine() {
        func r(_ s: Int?) -> Recipe { Recipe(title: "R", minutes: 35, servings: s, usesItems: [], missingItems: [], steps: [], macros: nil, macrosEstimated: true) }
        XCTAssertEqual(HomeModel.detail(for: r(2)), "35 min · 2 servings")
        XCTAssertEqual(HomeModel.detail(for: r(1)), "35 min · 1 serving")
        XCTAssertEqual(HomeModel.detail(for: r(nil)), "35 min")
    }

    // MARK: HomeEmpty

    func testEmptyFridgeIsTheEmptyStateWithNoTipAndNoRecipe() async {
        let (m, mock) = make(.empty)
        await m.loadIfNeeded()
        XCTAssertTrue(isEmpty(m.state))
        XCTAssertTrue(m.useFirst.isEmpty)
        XCTAssertNil(m.tip, "SCREENS #26: no tip on first use")
        XCTAssertNil(m.recipe)
        XCTAssertFalse(m.recipesUnavailable, "a muted placeholder, not an error")
        let recipeCalls = await mock.calls(to: "recipesSuggest")
        XCTAssertEqual(recipeCalls, 0, "no recipe request with nothing in the fridge")
    }

    /// SCREENS #26: the pill reads "0 lb saved" on first use. `-UITestSeed empty` must therefore return zero impact.
    func testEmptySeedReportsZeroSavedSoThePillReadsZero() async throws {
        let (m, _) = make(.empty)
        await m.loadIfNeeded()
        // IOS-41 (known, cross-PR): MockAPIClient.impact ignores the fixture. Flip when the Impact PR lands.
        XCTExpectFailure("IOS-41: mock impact ignores the empty seed", strict: false)
        XCTAssertEqual(m.savedKg, 0, "HomeEmpty artboard: '0 lb saved'")
    }

    // MARK: ServerError

    func testItemListFailureIsTheErrorState() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failNetwork = true
        let (m, _) = make(.fridge, b)
        await m.loadIfNeeded()
        XCTAssertTrue(isError(m.state))
        XCTAssertTrue(m.useFirst.isEmpty)
    }

    func testRetryAfterFailureShowsContent() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failFirst["listItems"] = 1
        let (m, _) = make(.fridge, b)
        await m.loadIfNeeded()
        XCTAssertTrue(isError(m.state))
        await m.retry()
        XCTAssertTrue(isContent(m.state))
        XCTAssertEqual(m.useFirst.count, 3)
    }

    func testRetryOnlyLeavesTheErrorOnceTheListLoads() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failures["listItems"] = .network("offline")
        let (m, mock) = make(.fridge, b)
        await m.loadIfNeeded()
        await m.retry()
        XCTAssertTrue(isError(m.state), "still down: stay on the error state")
        await mock.setFailure(nil, for: "listItems")
        await m.retry()
        XCTAssertTrue(isContent(m.state))
    }

    func testLoadIfNeededOnlyLoadsOnceButStaysRetryableAfterAnError() async {
        let (m, mock) = make()
        await m.loadIfNeeded()
        await m.loadIfNeeded()
        let lists = await mock.calls(to: "listItems")
        XCTAssertEqual(lists, 1, "second appearance of the tab keeps what is on screen")
    }

    func testErrorStateAfterFailedFirstLoadReloadsOnNextAppearance() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failFirst["listItems"] = 1
        let (m, _) = make(.fridge, b)
        await m.loadIfNeeded()
        XCTAssertTrue(isError(m.state))
        await m.loadIfNeeded()
        XCTAssertTrue(isContent(m.state), "switching back to the Home tab after an error should try again")
    }

    // MARK: Degradation of the secondary calls

    func testImpactFailureHidesThePillButKeepsTheScreen() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failures["impact"] = .network("x")
        let (m, _) = make(.fridge, b)
        await m.loadIfNeeded()
        XCTAssertTrue(isContent(m.state))
        XCTAssertNil(m.savedKg)
        XCTAssertEqual(m.useFirst.count, 3)
    }

    func testTipsFailureLeavesNoTip() async {
        var b = MockAPIClient.Behavior(delay: .zero); b.failures["tips"] = .network("x")
        let (m, _) = make(.fridge, b)
        await m.loadIfNeeded()
        XCTAssertTrue(isContent(m.state))
        XCTAssertNil(m.tip)
    }

    func testRecipes502ShowsAMutedCardNotTheErrorState() async {
        var b = MockAPIClient.Behavior(delay: .zero)
        b.failures["recipesSuggest"] = .server(status: 502, code: "upstream_unavailable", message: "x")
        let (m, _) = make(.fridge, b)
        await m.loadIfNeeded()
        XCTAssertTrue(isContent(m.state))
        XCTAssertNil(m.recipe)
        XCTAssertTrue(m.recipesUnavailable)
    }

    func testRefreshFailureKeepsStaleContentAndRaisesTheBanner() async {
        let (m, mock) = make()
        await m.loadIfNeeded()
        await mock.setFailure(.network("offline"), for: "listItems")
        await m.refresh()
        XCTAssertTrue(isContent(m.state))
        XCTAssertEqual(m.useFirst.count, 3, "stale content stays")
        XCTAssertTrue(m.refreshFailed)
        await mock.setFailure(nil, for: "listItems")
        await m.refresh()
        XCTAssertFalse(m.refreshFailed)
    }

    func testRefreshAfterRecipeAndTipChangesPicksThemUp() async {
        let (m, mock) = make()
        await m.loadIfNeeded()
        XCTAssertNotNil(m.tip)
        await mock.setFailure(.network("x"), for: "tips")
        await m.refresh()
        XCTAssertNil(m.tip)
    }

    func testLoadingForeverStaysInTheSkeleton() async throws {
        var b = MockAPIClient.Behavior(delay: .zero); b.delays["listItems"] = .seconds(3600)
        let (m, _) = make(.fridge, b)
        let task = Task { await m.loadIfNeeded() }
        try await Task.sleep(for: .milliseconds(300))
        XCTAssertTrue(isLoading(m.state))
        task.cancel()
    }
}
