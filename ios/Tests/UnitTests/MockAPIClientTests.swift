import XCTest
@testable import FoodWasteReducer

final class MockAPIClientTests: XCTestCase {
    private func client(_ fixture: MockFixture = .fridge, _ b: MockAPIClient.Behavior = .init(delay: .zero)) -> MockAPIClient {
        MockAPIClient(fixture: fixture, behavior: b, signedIn: true)
    }

    func testListGroupedByFoodGroupFollowsDesignOrderAndOmitsEmpty() async throws {
        let listing = try await client().listItems(storage: nil, groupBy: .foodGroup)
        guard case .grouped(let sections) = listing else { return XCTFail("expected grouped") }
        XCTAssertEqual(sections.map(\.foodGroup), [.protein, .veggies, .fruit, .dairy])
        for s in sections { XCTAssertTrue(s.items.allSatisfy { $0.foodGroup == s.foodGroup }) }
    }

    func testItemsWithinSectionSortedByExpiry() async throws {
        let listing = try await client().listItems(storage: nil, groupBy: .foodGroup)
        guard case .grouped(let sections) = listing else { return XCTFail() }
        for s in sections {
            let dates = s.items.compactMap(\.predictedExpiry)
            XCTAssertEqual(dates, dates.sorted(), "\(s.foodGroup)")
        }
    }

    func testFlatListSortedAndStorageFilter() async throws {
        let c = client()
        let all = try await c.listItems(storage: nil, groupBy: nil).allItems
        XCTAssertEqual(all.count, 8)
        XCTAssertEqual(all.compactMap(\.predictedExpiry), all.compactMap(\.predictedExpiry).sorted())
        let pantry = try await c.listItems(storage: .pantry, groupBy: nil).allItems
        XCTAssertTrue(pantry.isEmpty)
    }

    func testArtboardFixtureBadges() async throws {
        let items = try await client().listItems(storage: nil, groupBy: nil).allItems
        func badge(_ id: String) -> String? { ExpiryBadgeModel.make(for: items.first { $0.id == id }!)?.text }
        XCTAssertEqual(badge("item-chicken"), "Today")
        XCTAssertEqual(badge("item-spinach"), "1 day")
        XCTAssertEqual(badge("item-strawberries"), "Check")
        XCTAssertEqual(badge("item-bananas"), "Use soon")
    }

    func testEmptyAndExpiredAndLongFixtures() async throws {
        let empty = try await client(.empty).listItems(storage: nil, groupBy: nil).allItems
        XCTAssertTrue(empty.isEmpty)
        let expired = try await client(.expired).listItems(storage: nil, groupBy: nil).allItems
        XCTAssertTrue(expired.contains { ExpiryBadgeModel.make(for: $0)?.text == "Expired" })
        let long = try await client(.long).listItems(storage: nil, groupBy: nil).allItems
        XCTAssertGreaterThanOrEqual(long.count, 30)
        XCTAssertEqual(Set(long.map(\.foodGroup)).count, 9)
        XCTAssertEqual(MockFixture(name: "nonsense"), .fridge)
        XCTAssertEqual(MockFixture(name: nil), .fridge)
    }

    func testRemoveChangesStateAndRestoreUndoes() async throws {
        let c = client()
        let removed = try await c.removeItem(id: "item-chicken", outcome: .used)
        XCTAssertTrue(removed.isRemoved)
        XCTAssertEqual(removed.outcome, .used)
        var ids = try await c.listItems(storage: nil, groupBy: nil).allItems.map(\.id)
        XCTAssertFalse(ids.contains("item-chicken"))
        XCTAssertEqual(ids.count, 7)
        let restored = try await c.restoreItem(id: "item-chicken")
        XCTAssertFalse(restored.isRemoved)
        XCTAssertNil(restored.outcome)
        ids = try await c.listItems(storage: nil, groupBy: nil).allItems.map(\.id)
        XCTAssertTrue(ids.contains("item-chicken"))
    }

    func testRemoveValidationMatchesAPIRules() async throws {
        let c = client()
        await assertThrows(c, code: "validation_error") { _ = try await c.removeItem(id: "item-eggs", outcome: .thrownOut) }
        await assertThrows(c, code: "validation_error") { _ = try await c.removeItem(id: "item-eggs", outcome: .used, wasteReason: .expired) }
        let ok = try await c.removeItem(id: "item-eggs", outcome: .thrownOut, wasteReason: .forgot)
        XCTAssertEqual(ok.wasteReason, .forgot)
        await assertThrows(c, code: "already_removed") { _ = try await c.removeItem(id: "item-eggs", outcome: .used) }
        await assertThrows(c, code: "not_found") { _ = try await c.removeItem(id: "nope", outcome: .used) }
    }

    func testRemovedAfterExpiry() async throws {
        let c = client(.expired)
        let item = try await c.removeItem(id: "item-milk", outcome: .thrownOut, wasteReason: .expired)
        XCTAssertEqual(item.removedAfterExpiry, true)
    }

    func testCreateAndPatch() async throws {
        let c = client()
        let created = try await c.createItem(NewItem(name: "Tofu", category: .other, foodGroup: .protein, quantity: 2))
        XCTAssertEqual(created.name, "Tofu")
        XCTAssertEqual(created.storage, .fridge)
        XCTAssertNotNil(created.predictedExpiry)
        let after = try await c.listItems(storage: nil, groupBy: nil).allItems
        XCTAssertEqual(after.count, 9)
        let patched = try await c.patchItem(id: created.id, ItemPatch(name: "Firm tofu", predictedExpiry: "2026-12-01"))
        XCTAssertEqual(patched.name, "Firm tofu")
        XCTAssertEqual(patched.expirySource, "user")
        await assertThrows(c, code: "validation_error") { _ = try await c.createItems([]) }
    }

    func testFailureInjection() async throws {
        let c = client(.fridge, .init(delay: .zero, failNetwork: true))
        do { _ = try await c.listItems(storage: nil, groupBy: nil); XCTFail("expected network error") }
        catch let e as APIError { XCTAssertTrue(e.isNetwork) }
        await c.setFailNetwork(false)
        _ = try await c.listItems(storage: nil, groupBy: nil)

        await c.setFailure(.server(status: 500, code: "internal_error", message: "boom"), for: "tips")
        await assertThrows(c, code: "internal_error") { _ = try await c.tips() }
        await c.setFailure(nil, for: "tips")
        let tips = try await c.tips()
        XCTAssertFalse(tips.isEmpty)
    }

    func testFailFirstThenSucceedForRetry() async throws {
        let c = client(.fridge, .init(delay: .zero, failFirst: ["listItems": 2]))
        for _ in 0..<2 {
            do { _ = try await c.listItems(storage: nil, groupBy: nil); XCTFail("should fail") } catch {}
        }
        _ = try await c.listItems(storage: nil, groupBy: nil)
        let calls = await c.calls(to: "listItems")
        XCTAssertEqual(calls, 3)
    }

    func testSignedOutMockThrowsUnauthorized() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage())
        let c = MockAPIClient(fixture: .fridge, behavior: .init(delay: .zero), auth: store, signedIn: false)
        do { _ = try await c.listItems(storage: nil, groupBy: nil); XCTFail() }
        catch { XCTAssertEqual(error as? APIError, .unauthorized) }
        let s = try await c.login(email: "priya@example.com", password: "password1")
        XCTAssertEqual(s.user.displayName, "Priya")
        _ = try await c.listItems(storage: nil, groupBy: nil)
        let signedIn = await store.isSignedIn
        XCTAssertTrue(signedIn)
    }

    func testAuthEdgeCases() async throws {
        let c = client()
        await assertThrows(c, code: "invalid_credentials") { _ = try await c.login(email: "a@b.com", password: "wrong-password") }
        await assertThrows(c, code: "email_taken") { _ = try await c.signup(email: "taken@example.com", password: "longenough", displayName: "X") }
        await assertThrows(c, code: "validation_error") { _ = try await c.signup(email: "n@e.com", password: "short", displayName: "X") }
    }

    func testPhotoParseImpactRecipes() async throws {
        let c = client()
        let fridge = try await c.fromPhoto(imageData: Data(), mode: .fridge)
        XCTAssertGreaterThan(fridge.candidates.count, 1)
        let single = try await c.fromPhoto(imageData: Data(), mode: .single)
        XCTAssertEqual(single.candidates.count, 1)
        let parsed = try await c.parseText("two bananas and a loaf of bread")
        XCTAssertEqual(parsed.count, 2)
        await assertThrows(c, code: "validation_error") { _ = try await c.parseText("   ") }
        let impact = try await c.impact(range: .all)
        XCTAssertEqual(impact.saved.count, 23)
        let recipes = try await c.recipesSuggest(maxResults: 2, dietary: nil)
        XCTAssertEqual(recipes.count, 2)
    }

    func testDeleteAccountClearsItems() async throws {
        let c = client()
        try await c.deleteAccount()
        let left = await c.currentItems()
        XCTAssertTrue(left.isEmpty)
    }

    private func assertThrows(_ c: MockAPIClient, code: String, file: StaticString = #filePath, line: UInt = #line,
                              _ op: () async throws -> Void) async {
        do { try await op(); XCTFail("expected \(code)", file: file, line: line) }
        catch let e as APIError { XCTAssertEqual(e.code, code, file: file, line: line) }
        catch { XCTFail("unexpected \(error)", file: file, line: line) }
    }
}
