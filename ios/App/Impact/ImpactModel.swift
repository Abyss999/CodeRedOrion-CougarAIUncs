import SwiftUI
import Observation

/// State for the Impact screen: the selected range, one `Impact` per range, and the screen state.
/// Switching to a range that is already loaded shows it at once and refreshes quietly; a refresh
/// never flips the screen back to loading and never replays the chart animation.
@MainActor
@Observable
final class ImpactModel {
    enum ScreenState {
        case loading
        case error(Error)
        /// No events in this range yet.
        case empty
        case content(Impact)
    }

    var range: ImpactRange = .month {
        didSet { if range != oldValue { Task { await load(range) } } }
    }

    private(set) var impacts: [ImpactRange: Impact] = [:]
    private var errors: [ImpactRange: Error] = [:]
    /// The chart's entrance animation has played once; later appearances show it at rest.
    var chartRevealed = false
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    var state: ScreenState {
        if let impact = impacts[range] {
            return Self.isEmpty(impact) ? .empty : .content(impact)
        }
        if let error = errors[range] { return .error(error) }
        return .loading
    }

    static func isEmpty(_ impact: Impact) -> Bool { impact.saved.count + impact.wasted.count == 0 }

    func loadIfNeeded() async {
        if impacts[range] == nil { await load(range) }
    }

    /// Fetches `range`. A failure keeps content already on screen (a refresh failing is silent) and
    /// shows the error state only when there is nothing to show.
    func load(_ range: ImpactRange) async {
        if impacts[range] == nil { errors[range] = nil }
        do {
            impacts[range] = try await api.impact(range: range)
            errors[range] = nil
        } catch is CancellationError {
            return
        } catch {
            if impacts[range] == nil { errors[range] = error }
        }
    }

    func retry() async {
        errors[range] = nil
        await load(range)
    }

    func refresh() async { await load(range) }
}
