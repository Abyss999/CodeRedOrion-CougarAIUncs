import SwiftUI
import Observation

/// Loading state for one list.
enum Load<Value> {
    case loading
    case failed(Error)
    case loaded(Value)

    var value: Value? { if case .loaded(let v) = self { v } else { nil } }
}

/// Shared state for the Social tab, Food Pantry, MyRequests and ClaimedItem.
@MainActor
@Observable
final class SocialModel {
    var requests: Load<[HelpRequest]> = .loading
    var mine: Load<[HelpRequest]> = .loading
    var pantry: Load<[PantryListing]> = .loading
    /// Failed action on a list that is on screen (claim, cancel, offer refresh).
    var banner: String?
    private let api: APIClient
    private var loadedOnce = false

    init(api: APIClient) { self.api = api }

    // MARK: Loading

    func loadIfNeeded() async {
        guard !loadedOnce else { return }
        loadedOnce = true
        await refresh()
    }

    func refresh() async {
        async let a: Void = loadRequests()
        async let b: Void = loadPantry()
        _ = await (a, b)
    }

    func loadRequests() async {
        if case .failed = requests { requests = .loading }
        do { requests = .loaded(try await api.listRequests()) } catch is CancellationError {} catch {
            if requests.value == nil { requests = .failed(error) } else { banner = error.localizedDescription }
        }
    }

    func loadPantry() async {
        if case .failed = pantry { pantry = .loading }
        do { pantry = .loaded(try await api.listShares()) } catch is CancellationError {} catch {
            if pantry.value == nil { pantry = .failed(error) } else { banner = error.localizedDescription }
        }
    }

    func loadMine() async {
        if case .failed = mine { mine = .loading }
        do { mine = .loaded(try await api.listMyRequests()) } catch is CancellationError {} catch {
            if mine.value == nil { mine = .failed(error) } else { banner = error.localizedDescription }
        }
    }

    // MARK: Request actions

    /// `POST /requests/:id/fulfil`; the note leaves the board. Throws so the sheet can show the error.
    func fulfil(_ request: HelpRequest, reduceMotion: Bool) async throws {
        _ = try await api.fulfilRequest(id: request.id)
        withMotion(reduceMotion: reduceMotion) {
            if case .loaded(var list) = requests { list.removeAll { $0.id == request.id }; requests = .loaded(list) }
        }
        Haptics.success()
    }

    /// `POST /requests`; the new note goes to the top of the board and of "Yours".
    func post(text: String, selection: AudienceSelection, groups: [SharingGroup]) async throws {
        let r = try await api.createRequest(text: text, friends: selection.friends,
                                            groupIds: selection.orderedGroupIds(in: groups))
        if case .loaded(var list) = requests { list.insert(r, at: 0); requests = .loaded(list) }
        if case .loaded(var list) = mine { list.insert(r, at: 0); mine = .loaded(list) }
        Haptics.success()
    }

    func cancel(_ request: HelpRequest, reduceMotion: Bool) async {
        do {
            let updated = try await api.cancelRequest(id: request.id)
            withMotion(reduceMotion: reduceMotion) {
                if case .loaded(var list) = mine, let i = list.firstIndex(where: { $0.id == request.id }) {
                    list[i] = updated; mine = .loaded(list)
                }
                if case .loaded(var list) = requests { list.removeAll { $0.id == request.id }; requests = .loaded(list) }
            }
            banner = nil
        } catch {
            banner = error.localizedDescription
            Haptics.error()
        }
    }

    // MARK: Pantry actions

    func claim(_ listing: PantryListing) async {
        do {
            _ = try await api.claimShare(id: listing.id)
            if case .loaded(var list) = pantry, let i = list.firstIndex(where: { $0.id == listing.id }) {
                list[i].claimedByMe = true; pantry = .loaded(list)
            }
            banner = nil
            Haptics.success()
            await loadPantry()   // the server may now include the pickup spot
        } catch {
            banner = (error as? APIError).flatMap { err -> String? in
                if case .server(_, let code, _) = err, code == "already_claimed" || code == "listing_closed" {
                    return "Someone else just claimed that."
                }
                return nil
            } ?? error.localizedDescription
            Haptics.error()
            await loadPantry()
        }
    }
}
