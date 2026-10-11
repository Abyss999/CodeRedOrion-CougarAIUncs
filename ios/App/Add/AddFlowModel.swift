import SwiftUI
import Observation

/// Where the Add sheet's other entry points lead. Add text, barcode and receipt are built in the next PR (2b);
/// until then they land on `AddPlaceholderView`.
enum AddDestination: String, Hashable {
    case text, say, barcode, receipt

    var title: String {
        switch self {
        case .text: "Type it"
        case .say: "Say it"
        case .barcode: "Barcode"
        case .receipt: "Receipt"
        }
    }

    /// Both text destinations open the same AddText screen (2b); this is the mode it starts in.
    var textMode: AddTextMode? {
        switch self {
        case .text: .typing
        case .say: .dictation
        default: nil
        }
    }
}

enum AddTextMode: String, Hashable { case typing, dictation }

/// What failed in `PhotoReviewError`.
struct PhotoFailure: Equatable {
    /// 502 or no connection: show the banner with "Try again".
    var message: String
}

/// Drives the Add sheet: the menu, then the photo path (analyzing -> review / none / failed).
@MainActor
@Observable
final class AddFlowModel {
    enum Stage: Equatable {
        case menu
        case analyzing
        case review
        case none
        case failed(PhotoFailure)
        case destination(AddDestination)
    }

    private(set) var stage: Stage = .menu
    private(set) var photo: UIImage?
    private(set) var photoPixelSize: CGSize = .zero
    private(set) var review: PhotoReviewModel?
    private(set) var mode: PhotoMode = .fridge
    private var photoData: Data?
    private var task: Task<Void, Never>?
    private let api: APIClient

    /// Gemini enrichment is opt-in (PR #79). A backend without it ignores the field.
    static let enrich: [PhotoEnrichment] = [.expiry, .nutrition]

    init(api: APIClient) { self.api = api }

    var isMenu: Bool { stage == .menu }

    func analyze(image: UIImage, mode: PhotoMode) {
        guard let prepared = PhotoPrep.prepare(image) else {
            stage = .failed(PhotoFailure(message: "We couldn't read that photo. Try another one."))
            return
        }
        self.mode = mode
        photoData = prepared.data
        photoPixelSize = prepared.pixelSize
        photo = UIImage(data: prepared.data)
        run()
    }

    /// Runs (or re-runs, for "Try again") the detection on the current photo.
    func run() {
        guard let data = photoData else { stage = .menu; return }
        task?.cancel()
        stage = .analyzing
        let mode = mode
        task = Task { [api] in
            do {
                let response: CandidatesResponse
                if let client = api as? PhotoEnrichingClient {
                    response = try await client.fromPhoto(imageData: data, mode: mode, enrich: Self.enrich)
                } else {
                    response = try await api.fromPhoto(imageData: data, mode: mode)
                }
                if Task.isCancelled { return }
                if response.candidates.isEmpty {
                    stage = .none
                } else {
                    review = PhotoReviewModel(candidates: response.candidates, mode: mode, api: api)
                    stage = .review
                }
            } catch is CancellationError {
                return
            } catch {
                if Task.isCancelled { return }
                stage = .failed(PhotoFailure(message: Self.message(for: error)))
            }
        }
    }

    func cancel() {
        task?.cancel()
        reset()
    }

    func reset() {
        task?.cancel()
        photo = nil; photoData = nil; review = nil
        stage = .menu
    }

    func open(_ destination: AddDestination) { stage = .destination(destination) }

    static func message(for error: Error) -> String {
        if let api = error as? APIError {
            if case .server(let status, _, _) = api, status == 502 || status == 503 {
                return "Photo analysis is down right now. Your photo wasn't saved."
            }
            return api.errorDescription ?? "Something went wrong."
        }
        return error.localizedDescription
    }
}
