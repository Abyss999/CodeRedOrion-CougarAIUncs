import SwiftUI
import Observation

@MainActor
@Observable
final class RecipesModel {
    enum ScreenState {
        case loading
        case error(Error)
        /// Nothing came back at all (empty fridge).
        case empty
        /// Recipes exist but the current filters hide them all.
        case filteredOut(onlyWhatIHaveHidAll: Bool)
        case content([Recipe])
    }

    var onlyWhatIHave = true
    var expiringFirst = true
    var underThirty = false
    var vegetarian = false

    private(set) var all: [Recipe]?
    private(set) var error: Error?
    private(set) var isRefreshing = false
    /// Bumped on each fresh result so the list can stagger once per new result.
    private(set) var resultToken = 0
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    var state: ScreenState {
        guard let all else { return error.map(ScreenState.error) ?? .loading }
        if all.isEmpty { return .empty }
        let shown = visible
        if shown.isEmpty {
            return .filteredOut(onlyWhatIHaveHidAll: onlyWhatIHave && !applying(all, onlyHave: false).isEmpty)
        }
        return .content(shown)
    }

    var visible: [Recipe] { applying(all ?? [], onlyHave: onlyWhatIHave) }

    private func applying(_ recipes: [Recipe], onlyHave: Bool) -> [Recipe] {
        var r = recipes
        if onlyHave { r = r.filter(\.needsNothing) }
        if underThirty { r = r.filter { $0.minutes < 30 } }
        if expiringFirst {
            r = r.enumerated().sorted { a, b in
                switch (a.element.soonestExpiry, b.element.soonestExpiry) {
                case let (x?, y?): return x != y ? x < y : a.offset < b.offset
                case (_?, nil): return true
                case (nil, _?): return false
                default: return a.offset < b.offset
                }
            }.map(\.element)
        }
        return r
    }

    func loadIfNeeded() async {
        guard all == nil else { return }
        await load()
    }

    /// Retry from the error state: back to the skeleton.
    func retry() async {
        error = nil
        await load()
    }

    /// "New suggestions" button / pull to refresh.
    func refresh() async { await load() }

    func toggleVegetarian() async {
        vegetarian.toggle()
        await load()
    }

    func showNeedsAFewThings() { onlyWhatIHave = false }

    func clearFilters() {
        onlyWhatIHave = false; underThirty = false; expiringFirst = false
    }

    private func load() async {
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            let recipes = try await api.recipesSuggest(maxResults: 10, dietary: vegetarian ? ["vegetarian"] : nil)
            all = recipes
            error = nil
            resultToken += 1
        } catch is CancellationError {
            return
        } catch {
            if (error as? URLError)?.code == .cancelled { return }
            self.error = error
        }
    }

    /// Friendly copy for Gemini hiccups (502 upstream, 429 rate limit) before the generic message.
    static func friendlyMessage(for error: Error) -> String {
        if case let APIError.server(status, _, _) = error {
            if status == 429 { return "We're getting a lot of recipe requests. Give it a minute and try again." }
            if status == 502 || status == 503 || status == 504 { return "The recipe helper is taking a break. Try again in a moment." }
        }
        return error.localizedDescription
    }

    /// The error to hand to `ErrorStateView`: network errors keep their offline look, the rest get friendly copy.
    static func displayError(_ error: Error) -> Error {
        if (error as? APIError)?.isNetwork ?? false { return error }
        return APIError.invalidRequest(friendlyMessage(for: error))
    }
}
