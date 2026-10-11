import SwiftUI
import PhotosUI
import VisionKit

/// Receipt path: VisionKit document camera or a library photo, `POST /items/from-receipt`, then ReceiptReview
/// (`DetectedItemRow` with the printed line, the price trailing, non-food unticked).
@MainActor
@Observable
final class ReceiptModel {
    enum Phase: Equatable {
        case choose
        case analyzing
        /// The receipt service is down (502/503): the live API has no OCR yet.
        case unavailable
        case failed(String)
        case none
        case reviewing
    }

    private(set) var phase: Phase = .choose
    private(set) var review: AddReviewModel?
    private var photoData: Data?
    private var task: Task<Void, Never>?
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    func analyze(image: UIImage) {
        guard let prepared = PhotoPrep.prepare(image) else {
            phase = .failed("We couldn't read that photo. Try another one.")
            return
        }
        photoData = prepared.data
        run()
    }

    func run() {
        guard let data = photoData else { phase = .choose; return }
        task?.cancel()
        phase = .analyzing
        task = Task {
            do {
                let r = try await api.fromReceipt(imageData: data)
                if Task.isCancelled { return }
                if r.candidates.isEmpty {
                    phase = .none
                } else {
                    let rows = r.candidates.map {
                        AddReviewRow(candidate: $0.candidate, rawLine: $0.receiptText, price: $0.price ?? $0.candidate.estPrice, nonFoodDetection: true)
                    }
                    review = AddReviewModel(rows: rows, source: "receipt", total: r.total, api: api)
                    phase = .reviewing
                }
            } catch is CancellationError {
                return
            } catch {
                if Task.isCancelled { return }
                if case APIError.server(let status, _, _) = error, status == 502 || status == 503 {
                    phase = .unavailable
                } else {
                    phase = .failed((error as? LocalizedError)?.errorDescription ?? "Something went wrong. Try again.")
                }
            }
        }
    }

    func reset() { task?.cancel(); review = nil; photoData = nil; phase = .choose }
}

struct ReceiptView: View {
    let onBack: () -> Void
    let onType: () -> Void
    let onFinished: () -> Void

    @Environment(AppEnvironment.self) private var env
    @State private var model: ReceiptModel?
    @State private var showScanner = false
    @State private var showLibrary = false
    @State private var pickedItem: PhotosPickerItem?

    var body: some View {
        Group {
            if let model { content(model) } else { Color.clear }
        }
        .task { if model == nil { model = ReceiptModel(api: env.api) } }
        .fullScreenCover(isPresented: $showScanner) {
            DocumentScannerView(onImage: { image in showScanner = false; model?.analyze(image: image) },
                                onCancel: { showScanner = false })
                .ignoresSafeArea()
        }
        .photosPicker(isPresented: $showLibrary, selection: $pickedItem, matching: .images)
        .onChange(of: pickedItem) { _, item in
            guard let item else { return }
            pickedItem = nil
            Task {
                if let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) {
                    model?.analyze(image: image)
                }
            }
        }
    }

    private func content(_ model: ReceiptModel) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                    header(model)
                    switch model.phase {
                    case .choose: choose(model)
                    case .analyzing: analyzing
                    case .unavailable:
                        problem(icon: "receipt", title: "Receipts aren't available right now",
                                message: "Receipt reading is switched off for the moment. You can type what you bought instead.",
                                id: AccessibilityID.Receipt.unavailable, retry: nil, model: model)
                    case .failed(let message):
                        problem(icon: "exclamationmark.triangle", title: "That didn't work", message: message,
                                id: AccessibilityID.Receipt.error, retry: { model.run() }, model: model)
                    case .none:
                        problem(icon: "questionmark.circle", title: "We couldn't read any items",
                                message: "Try again with the whole receipt in view and good light.",
                                id: AccessibilityID.Receipt.empty, retry: nil, model: model)
                    case .reviewing:
                        if let review = model.review { reviewList(review) }
                    }
                }
                .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.m).padding(.bottom, Theme.Spacing.m)
            }
            .scrollBounceBehavior(.basedOnSize)
            if model.phase == .reviewing, let review = model.review {
                AddConfirmFooter(title: addItemsTitle(review.addCount), isSaving: review.phase == .saving,
                                 enabled: review.canConfirm, error: review.addError,
                                 confirmID: AccessibilityID.Receipt.confirm, errorID: AccessibilityID.Receipt.confirmError) {
                    Task { await review.confirm() }
                }
                .onChange(of: review.phase) { _, phase in if case .done = phase { onFinished() } }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Receipt.screen)
    }

    private func header(_ model: ReceiptModel) -> some View {
        HStack(spacing: Theme.Spacing.tileGap) {
            BackButton(action: { model.phase == .reviewing ? model.reset() : onBack() }, id: AccessibilityID.Receipt.back)
            VStack(alignment: .leading, spacing: 0) {
                Text(model.phase == .reviewing ? "Review receipt" : "Receipt")
                    .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier(AccessibilityID.Receipt.title)
                if model.phase == .reviewing, let review = model.review {
                    Text(review.foodCount == 1 ? "1 food item" : "\(review.foodCount) food items")
                        .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
                }
            }
            Spacer(minLength: 0)
        }
    }

    // MARK: Choose / analyzing

    private func choose(_ model: ReceiptModel) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            Text("Lay the receipt flat and get all of it in view.")
                .font(Theme.Fonts.body).foregroundStyle(Theme.Colors.inkSecondary)
            Button { startScan(model) } label: {
                Label("Scan a receipt", systemImage: "doc.viewfinder")
                    .font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier(AccessibilityID.Receipt.scan)
            Button { showLibrary = true } label: {
                Text("Choose a photo from your library")
                    .font(Theme.Fonts.segmentSelected).foregroundStyle(Theme.Colors.forest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier(AccessibilityID.Receipt.library)
        }
    }

    private func startScan(_ model: ReceiptModel) {
        if env.launch.useMockAPI {
            // No document camera in the Simulator or UI tests: use a stand-in photo.
            model.analyze(image: MockPhoto.image())
        } else if VNDocumentCameraViewController.isSupported {
            showScanner = true
        } else {
            showLibrary = true
        }
    }

    private var analyzing: some View {
        VStack(spacing: Theme.Spacing.sm) {
            ProgressView().controlSize(.large)
            Text("Reading your receipt…").font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 240)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(AccessibilityID.Receipt.analyzing)
    }

    private func problem(icon: String, title: String, message: String, id: String, retry: (() -> Void)?, model: ReceiptModel) -> some View {
        VStack(spacing: Theme.Spacing.m) {
            Image(systemName: icon)
                .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.forest)
                .frame(width: Theme.AddFlow.statusDisc, height: Theme.AddFlow.statusDisc)
                .background(Theme.Colors.limeTint, in: Circle())
                .accessibilityHidden(true)
            Text(title).font(Theme.Fonts.cardHeading).foregroundStyle(Theme.Colors.ink)
                .multilineTextAlignment(.center).accessibilityAddTraits(.isHeader)
            Text(message).font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted).multilineTextAlignment(.center)
            if let retry {
                Button(action: retry) {
                    Text("Try again").font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier(id + ".retry")
            } else if model.phase != .unavailable {
                Button { model.reset() } label: {
                    Text("Scan again").font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier(id + ".again")
            }
            Button(action: onType) {
                Text("Type it instead").font(Theme.Fonts.segmentSelected).foregroundStyle(Theme.Colors.forest)
                    .frame(minHeight: Theme.Size.minTouch).contentShape(Rectangle())
            }
            .accessibilityIdentifier(AccessibilityID.Receipt.typeInstead)
        }
        .frame(maxWidth: .infinity)
        .padding(Theme.Spacing.l)
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(id)
    }

    // MARK: Review

    private func reviewList(_ review: AddReviewModel) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            AddReviewList(model: review, showsPrice: true, idPrefix: AccessibilityID.Receipt.rows)
            if let total = review.total {
                HStack {
                    Text("Receipt total").font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
                    Spacer(minLength: Theme.Spacing.s)
                    Text(total, format: .currency(code: "USD")).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                }
                .padding(.horizontal, Theme.Spacing.xs)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(AccessibilityID.Receipt.total)
            }
        }
    }
}

/// VisionKit document camera. Returns the first scanned page.
struct DocumentScannerView: UIViewControllerRepresentable {
    var onImage: (UIImage) -> Void
    var onCancel: () -> Void

    func makeUIViewController(context: Context) -> VNDocumentCameraViewController {
        let vc = VNDocumentCameraViewController()
        vc.delegate = context.coordinator
        return vc
    }
    func updateUIViewController(_ uiViewController: VNDocumentCameraViewController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, VNDocumentCameraViewControllerDelegate {
        let parent: DocumentScannerView
        init(_ parent: DocumentScannerView) { self.parent = parent }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFinishWith scan: VNDocumentCameraScan) {
            if scan.pageCount > 0 { parent.onImage(scan.imageOfPage(at: 0)) } else { parent.onCancel() }
        }
        func documentCameraViewControllerDidCancel(_ controller: VNDocumentCameraViewController) { parent.onCancel() }
        func documentCameraViewController(_ controller: VNDocumentCameraViewController, didFailWithError error: Error) { parent.onCancel() }
    }
}
