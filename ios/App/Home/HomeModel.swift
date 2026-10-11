import SwiftUI
import Observation

/// Runs `op` and captures its outcome, so independent calls can run side by side (`async let`)
/// and one failing never cancels the others.
private func attempt<T: Sendable>(_ op: @Sendable () async throws -> T) async -> Result<T, Error> {
    do { return .success(try await op()) } catch { return .failure(error) }
}

/// State for the Home tab (SCREENS #4, #26, #28). The food list decides the screen state: if it
/// can't load, the whole screen is the ServerError state. Impact, tips and recipes are secondary:
/// when one of them fails its piece is simply left out (pill hidden, no tip, a muted recipe card).
@MainActor
@Observable
final class HomeModel {
    enum ScreenState {
        case loading
        case error(Error)
        /// No active items yet (HomeEmpty).
        case empty
        case content
    }

    private(set) var state: ScreenState = .loading
    /// The soonest-expiring active items, at most `useFirstLimit`.
    private(set) var useFirst: [Item] = []
    /// Food saved over the last 30 days (`GET /impact?range=month`), kg. nil when it couldn't load.
    private(set) var savedKg: Double?
    /// The first tip from `GET /tips` (the server orders them by priority).
    private(set) var tip: Tip?
    /// The recipe for "Cook tonight"; nil with none suggested or when the call failed.
    private(set) var recipe: Recipe?
    private(set) var recipesUnavailable = false
    /// True when a refresh failed while content is on screen (the offline banner shows over stale data).
    private(set) var refreshFailed = false
    let stagger = StaggerController()

    nonisolated static let useFirstLimit = 3

    private let api: APIClient
    private var loadedOnce = false

    init(api: APIClient) { self.api = api }

    /// First appearance of the tab. Later appearances keep what is on screen.
    func loadIfNeeded() async {
        guard !loadedOnce else { return }
        await load()
    }

    /// Pull to refresh: the content stays up, the stagger does not replay.
    func refresh() async { await load() }

    /// Retry from the error state: back to the skeleton, then the same load.
    func retry() async {
        state = .loading
        await load()
    }

    private func load() async {
        let api = self.api
        async let itemsResult = attempt { try await api.listItems(storage: nil, groupBy: nil) }
        async let impactResult = attempt { try await api.impact(range: .month) }
        async let tipsResult = attempt { try await api.tips() }

        let items: [Item]
        switch await itemsResult {
        case .success(let listing):
            items = listing.allItems.filter { !$0.isRemoved }
        case .failure(let error):
            if case .content = state {
                refreshFailed = true      // keep the stale content, show the banner
            } else {
                state = .error(error)
            }
            return
        }
        refreshFailed = false

        if case .success(let impact) = await impactResult { savedKg = impact.saved.kg } else if !loadedOnce { savedKg = nil }
        if case .success(let tips) = await tipsResult { tip = items.isEmpty ? nil : tips.first } else { tip = nil }
        useFirst = Self.soonest(items)

        if items.isEmpty {
            recipe = nil
            recipesUnavailable = false
        } else {
            switch await attempt({ try await api.recipesSuggest(maxResults: 3, dietary: nil) }) {
            case .success(let recipes): recipe = recipes.first; recipesUnavailable = false
            case .failure: recipe = nil; recipesUnavailable = true
            }
        }

        let first = !loadedOnce
        loadedOnce = true
        state = items.isEmpty ? .empty : .content
        if first { stagger.restart() }
    }

    /// Soonest expiry first; items without a date go last, in name order.
    static func soonest(_ items: [Item], limit: Int = useFirstLimit) -> [Item] {
        let sorted = items.sorted { a, b in
            switch (a.predictedExpiry, b.predictedExpiry) {
            case let (x?, y?): x != y ? x < y : a.name < b.name
            case (_?, nil): true
            case (nil, _?): false
            case (nil, nil): a.name < b.name
            }
        }
        return Array(sorted.prefix(limit))
    }

    /// The recipe's eyebrow: how many of its items expire within the week.
    static func eyebrow(for recipe: Recipe, now: Date = Date(), calendar: Calendar = .current) -> String {
        let today = calendar.startOfDay(for: now)
        let soon = recipe.usesItems.filter { item in
            guard let expiry = item.predictedExpiry else { return false }
            let days = calendar.dateComponents([.day], from: today, to: calendar.startOfDay(for: expiry)).day ?? 99
            return days <= 7
        }.count
        if soon > 0 { return "Uses \(soon) \(soon == 1 ? "item" : "items") expiring this week" }
        let n = recipe.usesItems.count
        return n > 0 ? "Uses \(n) of your \(n == 1 ? "item" : "items")" : "Made with what you have"
    }

    /// "35 min · 2 servings".
    static func detail(for recipe: Recipe) -> String {
        var parts = ["\(recipe.minutes) min"]
        if let s = recipe.servings { parts.append("\(s) \(s == 1 ? "serving" : "servings")") }
        return parts.joined(separator: " · ")
    }
}
