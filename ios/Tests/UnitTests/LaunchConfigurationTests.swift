import XCTest
@testable import FoodWasteReducer

/// Each `-UITest*` flag parses to its property, implies the mock, and maps to the documented
/// `MockAPIClient.Behavior`. UI tests (and the screen PRs) rely on these exact spellings.
final class LaunchConfigurationTests: XCTestCase {
    private func config(_ args: String...) -> LaunchConfiguration { LaunchConfiguration(arguments: args) }

    private func serverError(_ e: APIError?) -> (Int, String)? {
        guard case .server(let s, let c, _)? = e else { return nil }
        return (s, c)
    }

    // MARK: Parsing

    func testNoArgumentsIsLiveAndInert() {
        let c = LaunchConfiguration(arguments: [])
        XCTAssertEqual(c, LaunchConfiguration())
        XCTAssertFalse(c.useMockAPI)
        XCTAssertNil(c.seed); XCTAssertNil(c.undoWindow)
        let b = c.mockBehavior
        XCTAssertFalse(b.failNetwork)
        XCTAssertTrue(b.failures.isEmpty); XCTAssertTrue(b.failFirst.isEmpty); XCTAssertTrue(b.delays.isEmpty)
        XCTAssertNil(b.failThrownOut); XCTAssertFalse(b.expiredSession); XCTAssertFalse(b.photoFindsNothing)
    }

    func testFlagSpellings() {
        XCTAssertEqual(LaunchConfiguration.flagSignedOut, "-UITestSignedOut")
        XCTAssertEqual(LaunchConfiguration.flagExpiredSession, "-UITestExpiredSession")
        XCTAssertEqual(LaunchConfiguration.flagServerDown, "-UITestServerDown")
        XCTAssertEqual(LaunchConfiguration.flagPhotoNone, "-UITestPhotoNone")
        XCTAssertEqual(LaunchConfiguration.flagPhoto502, "-UITestPhoto502")
        XCTAssertEqual(LaunchConfiguration.flagCameraDenied, "-UITestCameraDenied")
        XCTAssertEqual(LaunchConfiguration.flagTossFails, "-UITestTossFails")
        XCTAssertEqual(LaunchConfiguration.flagRecipes502, "-UITestRecipes502")
        XCTAssertEqual(LaunchConfiguration.flagGoogle409, "-UITestGoogle409")
        XCTAssertEqual(LaunchConfiguration.flagClaimConflict, "-UITestClaimConflict")
        XCTAssertEqual(LaunchConfiguration.flagEmailUnknown, "-UITestEmailUnknown")
        XCTAssertEqual(LaunchConfiguration.flagFailBatch, "-UITestFailBatch")
        XCTAssertEqual(LaunchConfiguration.flagFailShare, "-UITestFailShare")
    }

    func testEachNewFlagSetsOnlyItsOwnPropertyAndImpliesMock() {
        let cases: [(String, KeyPath<LaunchConfiguration, Bool>)] = [
            ("-UITestSignedOut", \.signedOut), ("-UITestExpiredSession", \.expiredSession), ("-UITestServerDown", \.serverDown),
            ("-UITestPhotoNone", \.photoNone), ("-UITestPhoto502", \.photo502), ("-UITestCameraDenied", \.cameraDenied),
            ("-UITestTossFails", \.tossFails), ("-UITestRecipes502", \.recipes502), ("-UITestGoogle409", \.google409),
            ("-UITestClaimConflict", \.claimConflict), ("-UITestEmailUnknown", \.emailUnknown),
            ("-UITestFailBatch", \.failBatch), ("-UITestFailShare", \.failShare),
        ]
        for (flag, path) in cases {
            let c = config(flag)
            XCTAssertTrue(c[keyPath: path], flag)
            XCTAssertTrue(c.useMockAPI, "\(flag) only makes sense against the mock")
            for (other, otherPath) in cases where other != flag {
                // expiredSession implies signedIn; no other new flag may switch on a sibling.
                XCTAssertFalse(c[keyPath: otherPath], "\(flag) leaked into \(other)")
            }
        }
    }

    func testUnknownFlagsAreIgnored() {
        let c = config("-UITestSomethingNew", "-NSDoubleLocalizedStrings", "YES")
        XCTAssertEqual(c, LaunchConfiguration())
    }

    func testFlagsAreCaseSensitive() {
        XCTAssertFalse(config("-uitestmockapi").useMockAPI)
        XCTAssertFalse(config("-UITestSignedout").signedOut)
    }

    // MARK: Session flags

    func testSignedOutWinsOverSignedIn() {
        let c = config("-UITestSignedIn", "-UITestSignedOut")
        XCTAssertTrue(c.signedOut); XCTAssertFalse(c.signedIn)
        let reversed = config("-UITestSignedOut", "-UITestSignedIn")
        XCTAssertFalse(reversed.signedIn, "argument order must not matter")
    }

    func testExpiredSessionStartsSignedIn() {
        let c = config("-UITestExpiredSession")
        XCTAssertTrue(c.signedIn)
        XCTAssertTrue(c.mockBehavior.expiredSession)
    }

    func testSeedAndUndoWindowParsing() {
        XCTAssertEqual(config("-UITestSeed", "empty").seed, "empty")
        XCTAssertTrue(config("-UITestSeed", "empty").useMockAPI)
        XCTAssertNil(config("-UITestSeed").seed, "a trailing -UITestSeed with no value is ignored")
        XCTAssertEqual(config("-UITestUndoWindow", "30").undoWindow, .milliseconds(30_000))
        XCTAssertEqual(config("-UITestUndoWindow", "0.5").undoWindow, .milliseconds(500))
        XCTAssertNil(config("-UITestUndoWindow", "0").undoWindow)
        XCTAssertNil(config("-UITestUndoWindow", "-3").undoWindow)
        XCTAssertNil(config("-UITestUndoWindow", "soon").undoWindow)
        XCTAssertNil(config("-UITestUndoWindow").undoWindow)
    }

    func testCameraDeniedChangesNoMockBehavior() {
        let b = config("-UITestCameraDenied").mockBehavior
        XCTAssertTrue(b.failures.isEmpty); XCTAssertFalse(b.failNetwork); XCTAssertFalse(b.photoFindsNothing)
        XCTAssertEqual(config("-UITestCameraDenied").mockDelay, LaunchConfiguration.defaultDelay)
    }

    // MARK: Behavior mapping

    func testServerDownFailsEverythingLikeFailNetwork() {
        XCTAssertTrue(config("-UITestServerDown").mockBehavior.failNetwork)
        XCTAssertTrue(config("-UITestFailNetwork").mockBehavior.failNetwork)
    }

    func testPhotoNoneAndPhoto502() {
        XCTAssertTrue(config("-UITestPhotoNone").mockBehavior.photoFindsNothing)
        let b = config("-UITestPhoto502").mockBehavior
        for m in ["fromPhoto", "fromReceipt"] {
            let e = serverError(b.failures[m])
            XCTAssertEqual(e?.0, 502, m); XCTAssertEqual(e?.1, "upstream_unavailable", m)
        }
        XCTAssertNil(b.failures["barcode"])
        XCTAssertNil(b.failures["parseText"], "text add still works when the vision service is down")
    }

    func testErrorFlagsMapToDocumentedStatusAndCode() {
        let expectations: [(String, String, Int, String)] = [
            ("-UITestRecipes502", "recipesSuggest", 502, "upstream_unavailable"),
            ("-UITestGoogle409", "googleSignIn", 409, "account_exists_use_password"),
            ("-UITestClaimConflict", "claimShare", 409, "already_claimed"),
            ("-UITestEmailUnknown", "requestFriend", 404, "not_found"),
        ]
        for (flag, method, status, code) in expectations {
            let b = config(flag).mockBehavior
            let e = serverError(b.failures[method])
            XCTAssertEqual(e?.0, status, flag); XCTAssertEqual(e?.1, code, flag)
            XCTAssertEqual(b.failures.count, 1, "\(flag) fails only \(method)")
        }
    }

    func testFailBatchAndFailShareAreNetworkErrorsOnTheirMethods() {
        let batch = config("-UITestFailBatch").mockBehavior
        XCTAssertEqual(Set(batch.failures.keys), ["removeBatch", "restoreBatch"])
        if case .network? = batch.failures["removeBatch"] {} else { XCTFail("network error expected") }
        let share = config("-UITestFailShare").mockBehavior
        XCTAssertEqual(Set(share.failures.keys), ["createShare"])
    }

    func testTossFailsOnlyThrownOut() {
        let b = config("-UITestTossFails").mockBehavior
        XCTAssertNotNil(b.failThrownOut)
        XCTAssertTrue(b.failures.isEmpty, "used / donated keep working")
    }

    func testFridgeFlagsStillMapAsBefore() {
        XCTAssertNotNil(config("-UITestFailList").mockBehavior.failures["listItems"])
        XCTAssertEqual(config("-UITestFailListOnce").mockBehavior.failFirst["listItems"], 1)
        XCTAssertNotNil(config("-UITestFailRemove").mockBehavior.failures["removeItem"])
        XCTAssertNotNil(config("-UITestFailRestore").mockBehavior.failures["restoreItem"])
        XCTAssertEqual(config("-UITestRestoreNotRemoved").mockBehavior.failures["restoreItem"], .notRemoved)
        XCTAssertEqual(config("-UITestLoadingForever").mockBehavior.delays["listItems"], LaunchConfiguration.foreverDelay)
        XCTAssertEqual(config("-UITestSlowRemove").mockBehavior.delays["removeItem"], LaunchConfiguration.slowDelay)
        XCTAssertEqual(config("-UITestSlowRestore").mockBehavior.delays["restoreItem"], LaunchConfiguration.slowDelay)
        XCTAssertEqual(config("-UITestSlowNetwork").mockDelay, LaunchConfiguration.slowDelay)
        XCTAssertEqual(config("-UITestMockAPI").mockDelay, LaunchConfiguration.defaultDelay)
    }

    func testFlagsCombine() {
        let c = config("-UITestSignedIn", "-UITestPhoto502", "-UITestFailShare", "-UITestTossFails", "-UITestSeed", "long")
        XCTAssertTrue(c.signedIn)
        let b = c.mockBehavior
        XCTAssertEqual(Set(b.failures.keys), ["fromPhoto", "fromReceipt", "createShare"])
        XCTAssertNotNil(b.failThrownOut)
        XCTAssertEqual(c.seed, "long")
    }

    // MARK: End to end: flag -> Mock behaviour

    private func mock(_ args: String...) -> MockAPIClient {
        let c = LaunchConfiguration(arguments: args)
        var b = c.mockBehavior
        b.delay = .zero
        return MockAPIClient(fixture: MockFixture(name: c.seed), behavior: b, signedIn: c.signedIn)
    }

    private func expect(_ status: Int, _ code: String, file: StaticString = #filePath, line: UInt = #line,
                        _ op: () async throws -> Void) async {
        do { try await op(); XCTFail("expected \(status) \(code)", file: file, line: line) }
        catch {
            guard case .server(let s, let c, _)? = error as? APIError else { return XCTFail("\(error)", file: file, line: line) }
            XCTAssertEqual(s, status, file: file, line: line); XCTAssertEqual(c, code, file: file, line: line)
        }
    }

    func testFlagsDriveTheMockEndToEnd() async throws {
        await expect(502, "upstream_unavailable") { _ = try await self.mock("-UITestPhoto502").fromReceipt(imageData: Data([1])) }
        await expect(502, "upstream_unavailable") { _ = try await self.mock("-UITestPhoto502").fromPhoto(imageData: Data([1]), mode: .fridge) }
        await expect(502, "upstream_unavailable") { _ = try await self.mock("-UITestRecipes502").recipesSuggest() }
        await expect(409, "account_exists_use_password") { _ = try await self.mock("-UITestGoogle409").googleSignIn(idToken: "t") }
        await expect(409, "already_claimed") { _ = try await self.mock("-UITestClaimConflict").claimShare(id: "share-sourdough") }
        await expect(404, "not_found") { _ = try await self.mock("-UITestEmailUnknown").requestFriend(email: "marcus@example.com") }
        let none = try await mock("-UITestPhotoNone").fromPhoto(imageData: Data([1]), mode: .fridge)
        XCTAssertTrue(none.candidates.isEmpty)
    }

    func testFailBatchLeavesSingleRemoveWorking() async throws {
        let c = mock("-UITestFailBatch", "-UITestSignedIn")
        do { _ = try await c.removeBatch(ids: ["item-eggs"], outcome: .used); XCTFail() } catch {}
        do { _ = try await c.restoreBatch(ids: ["item-eggs"]); XCTFail() } catch {}
        let single = try await c.removeItem(id: "item-eggs", outcome: .used)
        XCTAssertTrue(single.isRemoved)
    }

    func testTossFailsEndToEnd() async throws {
        let c = mock("-UITestTossFails", "-UITestSignedIn")
        do { _ = try await c.removeItem(id: "item-eggs", outcome: .thrownOut, wasteReason: .forgot); XCTFail() } catch {}
        let still = try await c.listItems().allItems.map(\.id)
        XCTAssertTrue(still.contains("item-eggs"), "a failed toss leaves the item in the fridge")
        _ = try await c.removeItem(id: "item-eggs", outcome: .donated)
    }

    func testFailShareEndToEnd() async throws {
        let c = mock("-UITestFailShare", "-UITestSignedIn")
        do { _ = try await c.createShare(itemId: "item-eggs", groupId: nil); XCTFail() } catch {}
        _ = try await c.listShares()
    }

    func testServerDownEndToEndIncludingHealth() async throws {
        let c = mock("-UITestServerDown")
        do { _ = try await c.health(); XCTFail("health must fail when the server is down") }
        catch let e as APIError { if case .network = e {} else { XCTFail("\(e)") } }
        do { _ = try await c.listItems(); XCTFail() } catch {}
    }

    func testSignedOutMockRejectsAuthedCallsWhenAuthStoreIsEmpty() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage(nil))
        let c = LaunchConfiguration(arguments: ["-UITestSignedOut", "-UITestSignedIn"])
        var b = c.mockBehavior; b.delay = .zero
        let api = MockAPIClient(behavior: b, auth: store, signedIn: c.signedIn)
        do { _ = try await api.listItems(); XCTFail() } catch { XCTAssertEqual(error as? APIError, .unauthorized) }
        let session = try await api.login(email: "priya@example.com", password: "password1")
        XCTAssertEqual(session.user.email, "priya@example.com")
        _ = try await api.listItems()
    }

    func testExpiredSessionEndToEnd() async throws {
        let store = await AuthStore(storage: InMemorySessionStorage(AuthSession(token: "t", user: MockData.priya)))
        let c = LaunchConfiguration(arguments: ["-UITestExpiredSession"])
        var b = c.mockBehavior; b.delay = .zero
        let api = MockAPIClient(behavior: b, auth: store, signedIn: c.signedIn)
        do { _ = try await api.listItems(); XCTFail() } catch { XCTAssertEqual(error as? APIError, .unauthorized) }
        let signedIn = await store.isSignedIn
        XCTAssertFalse(signedIn)
    }

    // MARK: AppEnvironment wiring

    @MainActor func testEnvironmentPicksMockForNewFlagsAndLiveWithout() {
        let live = AppEnvironment.make(launch: LaunchConfiguration(arguments: []))
        XCTAssertTrue(live.api is LiveAPIClient)
        for flag in ["-UITestSignedOut", "-UITestCameraDenied", "-UITestServerDown", "-UITestFailShare"] {
            let env = AppEnvironment.make(launch: LaunchConfiguration(arguments: [flag]))
            XCTAssertTrue(env.api is MockAPIClient, flag)
            XCTAssertTrue(env.launch.useMockAPI)
        }
    }

    @MainActor func testEnvironmentStartsSignedOutOrInPerFlag() async {
        let out = AppEnvironment.make(launch: LaunchConfiguration(arguments: ["-UITestSignedIn", "-UITestSignedOut"]))
        let outSigned = await out.auth.isSignedIn
        XCTAssertFalse(outSigned)
        let inn = AppEnvironment.make(launch: LaunchConfiguration(arguments: ["-UITestSignedIn"]))
        let inSigned = await inn.auth.isSignedIn
        XCTAssertTrue(inSigned)
    }
}
