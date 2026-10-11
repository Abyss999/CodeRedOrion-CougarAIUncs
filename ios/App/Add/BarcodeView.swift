import SwiftUI
import AVFoundation

/// Barcode path: scan (or, where the scanner can't run, a manual code field), `GET /items/barcode/:code`,
/// then BarcodeResult with add / not found / lookup-service-unreachable states.
@MainActor
@Observable
final class BarcodeModel {
    enum Phase: Equatable {
        case scanning
        case looking(String)
        case found
        case notFound(String)
        case unreachable(String)
        case invalid(String)
    }

    private(set) var phase: Phase = .scanning
    private(set) var result: BarcodeResult?
    var amount: Double = 1
    var unit = "piece"
    private(set) var isAdding = false
    private(set) var addError: String?
    private(set) var added = false
    private let api: APIClient
    private var task: Task<Void, Never>?

    init(api: APIClient) { self.api = api }

    func lookup(_ raw: String) {
        let code = raw.filter(\.isNumber)
        guard (6...14).contains(code.count) else {
            phase = .invalid("Barcodes have 6 to 14 digits. Check the number and try again.")
            return
        }
        task?.cancel()
        phase = .looking(code)
        task = Task {
            do {
                let r = try await api.barcode(code)
                if Task.isCancelled { return }
                result = r
                amount = r.candidate.quantity ?? 1
                unit = r.candidate.unit ?? "piece"
                addError = nil
                phase = .found
            } catch is CancellationError {
                return
            } catch let error as APIError {
                if Task.isCancelled { return }
                switch error {
                case .server(let status, _, _) where status == 404: phase = .notFound(code)
                case .server(let status, _, _) where status == 400: phase = .invalid("That code doesn't look right. Check the number and try again.")
                default: phase = .unreachable(code)
                }
            } catch {
                if Task.isCancelled { return }
                phase = .unreachable(code)
            }
        }
    }

    func scanAgain() { task?.cancel(); result = nil; phase = .scanning }

    func add() async {
        guard let result, !isAdding else { return }
        isAdding = true
        addError = nil
        var n = NewItem(candidate: result.candidate, source: "barcode")
        n.quantity = amount
        n.unit = unit
        do {
            _ = try await api.createItems([n])
            NotificationCenter.default.post(name: .itemsDidChange, object: nil)
            Haptics.success()
            added = true
        } catch {
            addError = (error as? LocalizedError)?.errorDescription ?? "Couldn't add that item."
            Haptics.error()
        }
        isAdding = false
    }
}

struct BarcodeView: View {
    let onBack: () -> Void
    let onType: () -> Void
    let onFinished: () -> Void

    @Environment(AppEnvironment.self) private var env
    @State private var model: BarcodeModel?
    @State private var manualCode = ""
    @FocusState private var manualFocused: Bool

    private var cameraDenied: Bool {
        env.launch.cameraDenied || [.denied, .restricted].contains(AVCaptureDevice.authorizationStatus(for: .video))
    }
    private var scannerUsable: Bool { !env.launch.useMockAPI && BarcodeScannerView.isUsable }

    var body: some View {
        Group {
            if let model { content(model) } else { Color.clear }
        }
        .task { if model == nil { model = BarcodeModel(api: env.api) } }
    }

    private func content(_ model: BarcodeModel) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                    header
                    switch model.phase {
                    case .scanning: scanning(model)
                    case .looking: looking
                    case .found: if let r = model.result { found(model, r) }
                    case .notFound(let code): notFound(model, code)
                    case .unreachable(let code): unreachable(model, code)
                    case .invalid(let message): invalid(model, message)
                    }
                }
                .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.m).padding(.bottom, Theme.Spacing.m)
            }
            .scrollBounceBehavior(.basedOnSize)
            .scrollDismissesKeyboard(.interactively)
            if case .found = model.phase {
                AddConfirmFooter(title: "Add to \(storageName(model))", isSaving: model.isAdding, enabled: !model.isAdding,
                                 error: model.addError, confirmID: AccessibilityID.Barcode.add,
                                 errorID: AccessibilityID.Barcode.addError) { Task { await model.add() } }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Barcode.screen)
        .onChange(of: model.added) { _, added in if added { onFinished() } }
    }

    private var header: some View {
        HStack(spacing: Theme.Spacing.tileGap) {
            BackButton(action: onBack, id: AccessibilityID.Barcode.back)
            Text("Barcode")
                .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 0)
        }
    }

    // MARK: Scanning

    @ViewBuilder private func scanning(_ model: BarcodeModel) -> some View {
        if cameraDenied {
            PermissionCard(kind: .camera, alternativeTitle: "Type it instead", alternative: onType)
                .padding(.horizontal, -Theme.Spacing.gutter)
        } else if scannerUsable {
            BarcodeScannerView { model.lookup($0) }
                .frame(height: 320)
                .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                .accessibilityLabel("Camera. Point it at a barcode.")
                .accessibilityIdentifier(AccessibilityID.Barcode.scanner)
            Text("Point the camera at the barcode on the box, can or jar.")
                .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
            #if DEBUG
            manualEntry(model)
            #endif
        } else {
            #if DEBUG
            BannerView(style: .info, message: "The scanner needs a real camera. Type a code instead.",
                       identifiers: BannerIdentifiers(container: "barcode.simulator"), horizontalInset: 0)
            manualEntry(model)
            #else
            ContentUnavailableView("Scanner not available", systemImage: "barcode.viewfinder",
                                   description: Text("This device can't scan barcodes. You can type the item instead."))
            Button(action: onType) { linkLabel("Type it instead") }
            #endif
        }
    }

    #if DEBUG
    private func manualEntry(_ model: BarcodeModel) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            FormField(label: "Barcode number", error: nil, identifier: AccessibilityID.Barcode.manualField) {
                TextField("016000275287", text: $manualCode)
                    .keyboardType(.numberPad)
                    .focused($manualFocused)
                    .font(Theme.Fonts.body).foregroundStyle(Theme.Colors.ink)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .frame(minHeight: Theme.Size.minTouch)
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                            .strokeBorder(manualFocused ? Theme.Colors.forest : Theme.Colors.border,
                                          lineWidth: manualFocused ? Theme.Stroke.selected : Theme.Stroke.hairline)
                    }
            }
            Button { manualFocused = false; model.lookup(manualCode) } label: {
                Text("Look it up").font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .contentShape(Rectangle())
            }
            .disabled(manualCode.filter(\.isNumber).isEmpty)
            .opacity(manualCode.filter(\.isNumber).isEmpty ? 0.45 : 1)
            .accessibilityIdentifier(AccessibilityID.Barcode.manualLookup)
            if env.launch.useMockAPI {
                ForEach(MockAddText.knownCodes, id: \.code) { sample in
                    Button { manualCode = sample.code; model.lookup(sample.code) } label: {
                        linkLabel("Try \(sample.label)")
                    }
                    .accessibilityIdentifier(AccessibilityID.Barcode.sample(sample.code))
                }
            }
        }
    }
    #endif

    private var looking: some View {
        VStack(spacing: Theme.Spacing.sm) {
            ProgressView()
            Text("Looking it up…").font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(AccessibilityID.Barcode.looking)
    }

    // MARK: Result

    private func storageName(_ model: BarcodeModel) -> String {
        switch model.result?.candidate.storage ?? .fridge {
        case .fridge: "fridge"
        case .pantry: "pantry"
        case .freezer: "freezer"
        }
    }

    private func found(_ model: BarcodeModel, _ r: BarcodeResult) -> some View {
        @Bindable var model = model
        let c = r.candidate
        let title = c.name
        return VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Text(r.quantityText.map { "\(title), \($0)" } ?? title)
                    .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier(AccessibilityID.Barcode.name)
                Text("Found on Open Food Facts · \(c.foodGroup.displayName)")
                    .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
                    .accessibilityIdentifier(AccessibilityID.Barcode.source)
            }
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                HStack {
                    Text("Quantity").font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    Spacer(minLength: Theme.Spacing.s)
                    QuantityStepper(name: c.name, amount: $model.amount, unit: model.unit, isEditing: false, onEditAmount: {},
                                    ids: (AccessibilityID.Barcode.less, AccessibilityID.Barcode.more, AccessibilityID.Barcode.amount))
                }
                Divider().overlay(Theme.Colors.hairline)
                HStack {
                    Text("Stored in \(storageName(model).capitalized)").font(Theme.Fonts.body).foregroundStyle(Theme.Colors.ink)
                    Spacer(minLength: Theme.Spacing.s)
                    if let expiry = c.predictedExpiry {
                        Text("Use by \(expiry.formatted(.dateTime.month(.abbreviated).day())) estimated")
                            .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            .padding(Theme.Spacing.m)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            HStack {
                Button(action: onType) { linkLabel("Not this? Type it instead") }
                    .accessibilityIdentifier(AccessibilityID.Barcode.typeInstead)
                Spacer(minLength: 0)
                Button { model.scanAgain() } label: { linkLabel("Scan another") }
                    .accessibilityIdentifier(AccessibilityID.Barcode.scanAgain)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Barcode.result)
    }

    // MARK: Problems

    private func notFound(_ model: BarcodeModel, _ code: String) -> some View {
        problem(icon: "questionmark.circle", title: "We don't know that one",
                message: "Open Food Facts has no product for \(code). Try scanning again, or type it instead.",
                id: AccessibilityID.Barcode.notFound, model: model, retry: nil)
    }

    private func unreachable(_ model: BarcodeModel, _ code: String) -> some View {
        problem(icon: "wifi.exclamationmark", title: "Can't look that up right now",
                message: "The product lookup isn't reachable. Check your connection, or type it instead.",
                id: AccessibilityID.Barcode.unreachable, model: model, retry: code)
    }

    private func invalid(_ model: BarcodeModel, _ message: String) -> some View {
        problem(icon: "exclamationmark.circle", title: "Check that code", message: message,
                id: AccessibilityID.Barcode.notFound, model: model, retry: nil)
    }

    private func problem(icon: String, title: String, message: String, id: String, model: BarcodeModel, retry: String?) -> some View {
        VStack(spacing: Theme.Spacing.m) {
            Image(systemName: icon)
                .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.forest)
                .frame(width: Theme.AddFlow.statusDisc, height: Theme.AddFlow.statusDisc)
                .background(Theme.Colors.limeTint, in: Circle())
                .accessibilityHidden(true)
            Text(title).font(Theme.Fonts.cardHeading).foregroundStyle(Theme.Colors.ink).accessibilityAddTraits(.isHeader)
            Text(message).font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted).multilineTextAlignment(.center)
            if let retry {
                Button { model.lookup(retry) } label: { primaryLabel("Try again") }
                    .accessibilityIdentifier(AccessibilityID.Barcode.retry)
            }
            Button { model.scanAgain() } label: { retry == nil ? AnyView(primaryLabel("Scan again")) : AnyView(linkLabel("Scan again")) }
                .accessibilityIdentifier(AccessibilityID.Barcode.scanAgain)
            Button(action: onType) { linkLabel("Type it instead") }
                .accessibilityIdentifier(AccessibilityID.Barcode.typeInstead)
        }
        .frame(maxWidth: .infinity)
        .padding(Theme.Spacing.l)
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(id)
    }

    private func primaryLabel(_ title: String) -> some View {
        Text(title).font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
            .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
            .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
            .contentShape(Rectangle())
    }

    private func linkLabel(_ title: String) -> some View {
        Text(title).font(Theme.Fonts.segmentSelected).foregroundStyle(Theme.Colors.forest)
            .frame(minHeight: Theme.Size.minTouch)
            .contentShape(Rectangle())
    }
}
