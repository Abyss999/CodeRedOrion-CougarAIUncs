import SwiftUI

/// AddText ("Type it" / "Say it"): a text field with a mic, `POST /items/parse-text`, then a review list of
/// `DetectedItemRow`s and "Add N items".
@MainActor
@Observable
final class AddTextModel {
    enum Phase: Equatable { case input, parsing, failed(String), none, reviewing }

    var text = ""
    private(set) var phase: Phase = .input
    private(set) var review: AddReviewModel?
    private let api: APIClient
    private var task: Task<Void, Never>?

    init(api: APIClient) { self.api = api }

    var canFind: Bool { !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && phase != .parsing }

    func find() {
        guard canFind else { return }
        let input = text
        task?.cancel()
        phase = .parsing
        task = Task {
            do {
                let candidates = try await api.parseText(input)
                if Task.isCancelled { return }
                if candidates.isEmpty {
                    phase = .none
                } else {
                    review = AddReviewModel(rows: candidates.map { AddReviewRow(candidate: $0) }, source: "text", api: api)
                    phase = .reviewing
                }
            } catch is CancellationError {
                return
            } catch {
                if Task.isCancelled { return }
                phase = .failed((error as? LocalizedError)?.errorDescription ?? "Something went wrong. Try again.")
            }
        }
    }

    func backToInput() { task?.cancel(); review = nil; phase = .input }
}

struct AddTextView: View {
    let startMode: AddTextMode
    let onBack: () -> Void
    let onFinished: () -> Void

    @Environment(AppEnvironment.self) private var env
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var model: AddTextModel?
    @State private var dictation: DictationController?
    @State private var mode: AddTextMode
    @FocusState private var focused: Bool

    init(startMode: AddTextMode, onBack: @escaping () -> Void, onFinished: @escaping () -> Void) {
        self.startMode = startMode; self.onBack = onBack; self.onFinished = onFinished
        _mode = State(initialValue: startMode)
    }

    var body: some View {
        Group {
            if let model, let dictation { content(model, dictation) } else { Color.clear }
        }
        .task {
            if model == nil { model = AddTextModel(api: env.api) }
            if dictation == nil { dictation = DictationController(simulated: env.launch.useMockAPI, micDenied: env.launch.micDenied) }
        }
    }

    @ViewBuilder private func content(_ model: AddTextModel, _ dictation: DictationController) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                    header
                    if model.phase == .reviewing, let review = model.review {
                        reviewSection(model, review)
                    } else {
                        inputSection(model, dictation)
                    }
                }
                .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.m).padding(.bottom, Theme.Spacing.m)
            }
            .scrollBounceBehavior(.basedOnSize)
            .scrollDismissesKeyboard(.interactively)
            if model.phase == .reviewing, let review = model.review {
                AddConfirmFooter(title: addItemsTitle(review.addCount), isSaving: review.phase == .saving,
                                 enabled: review.canConfirm, error: review.addError,
                                 confirmID: AccessibilityID.AddText.confirm, errorID: AccessibilityID.AddText.confirmError) {
                    Task { await review.confirm() }
                }
                .onChange(of: review.phase) { _, phase in if case .done = phase { onFinished() } }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.AddText.screen)
        .onChange(of: dictation.isListening) { was, now in
            // Dictation just ended with something heard: go straight to the items.
            if was && !now, mode == .dictation { model.text = dictation.transcript; model.find() }
        }
        .onChange(of: dictation.transcript) { _, new in if dictation.isListening || mode == .dictation { model.text = new } }
    }

    private var header: some View {
        HStack(spacing: Theme.Spacing.tileGap) {
            BackButton(action: { dictation?.stop(); onBack() }, id: AccessibilityID.AddText.back)
            Text("Type or say it")
                .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(AccessibilityID.AddText.title)
            Spacer(minLength: 0)
        }
    }

    // MARK: Input

    private func inputSection(_ model: AddTextModel, _ dictation: DictationController) -> some View {
        @Bindable var model = model
        return VStack(alignment: .leading, spacing: Theme.Spacing.m) {
            if case .denied(let kind) = dictation.state {
                PermissionCard(kind: kind, alternativeTitle: "Type it instead", alternative: {
                    dictation.reset(); mode = .typing; focused = true
                })
                .padding(.horizontal, -Theme.Spacing.gutter)
            }
            if case .unavailable(let message) = dictation.state {
                BannerView(style: .warning, message: message, identifiers: BannerIdentifiers(container: AccessibilityID.AddText.notice), horizontalInset: 0)
            }
            if mode == .dictation { micButton(dictation, large: true) }
            FormField(label: "What did you get?", error: nil, identifier: AccessibilityID.AddText.field) {
                HStack(alignment: .top, spacing: Theme.Spacing.s) {
                    TextField("2 lb chicken, a bag of spinach, a dozen eggs", text: $model.text, axis: .vertical)
                        .lineLimit(3...8)
                        .focused($focused)
                        .font(Theme.Fonts.body).foregroundStyle(Theme.Colors.ink)
                        .submitLabel(.done)
                        .onSubmit { model.find() }
                        .disabled(dictation.isListening)
                    if mode == .typing { micButton(dictation, large: false) }
                }
                .padding(Theme.Spacing.sm)
                .frame(minHeight: Theme.Size.minTouch)
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                .overlay {
                    RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                        .strokeBorder(focused ? Theme.Colors.forest : Theme.Colors.border,
                                      lineWidth: focused ? Theme.Stroke.selected : Theme.Stroke.hairline)
                }
            }
            if dictation.isListening {
                Text("Listening… tap the mic to stop")
                    .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
                    .accessibilityIdentifier(AccessibilityID.AddText.status)
            }
            switch model.phase {
            case .parsing:
                HStack(spacing: Theme.Spacing.s) {
                    ProgressView()
                    Text("Working out what you got…").font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(AccessibilityID.AddText.parsing)
            case .failed(let message):
                BannerView(style: .error, message: message, retryTitle: "Try again", retry: { model.find() },
                           identifiers: BannerIdentifiers(container: AccessibilityID.AddText.error, retry: AccessibilityID.AddText.error + ".retry"),
                           horizontalInset: 0)
            case .none:
                BannerView(style: .info, message: "We couldn't find any food in that. Try naming the items, like \"two bananas and a loaf of bread\".",
                           identifiers: BannerIdentifiers(container: AccessibilityID.AddText.empty), horizontalInset: 0)
            default:
                EmptyView()
            }
            Button { focused = false; model.find() } label: {
                Text("Find the items")
                    .font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .contentShape(Rectangle())
            }
            .disabled(!model.canFind || dictation.isListening)
            .opacity(model.canFind && !dictation.isListening ? 1 : 0.45)
            .accessibilityIdentifier(AccessibilityID.AddText.find)
        }
    }

    private func micButton(_ dictation: DictationController, large: Bool) -> some View {
        let diameter: CGFloat = large ? 64 : Theme.Size.minTouch
        return Button {
            focused = false
            if large == false { mode = .dictation }
            dictation.toggle()
        } label: {
            ZStack {
                if dictation.isListening { ListeningPulse(diameter: diameter, color: Theme.Colors.urgentInk) }
                Image(systemName: dictation.isListening ? "stop.fill" : "mic.fill")
                    .font(large ? Theme.Fonts.sheetTitle : Theme.Fonts.button)
                    .foregroundStyle(dictation.isListening ? Theme.Colors.onForest : Theme.Colors.forest)
                    .frame(width: diameter, height: diameter)
                    .background(dictation.isListening ? Theme.Colors.urgentInk : Theme.Colors.limeTint, in: Circle())
            }
            .frame(maxWidth: large ? .infinity : nil)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dictation.isListening ? "Stop listening" : "Say it")
        .accessibilityHint(dictation.isListening ? "" : "Speak the food you want to add")
        .accessibilityIdentifier(AccessibilityID.AddText.mic)
    }

    // MARK: Review

    private func reviewSection(_ model: AddTextModel, _ review: AddReviewModel) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack {
                Text(review.rows.count == 1 ? "We understood 1 item" : "We understood \(review.rows.count) items")
                    .font(Theme.Fonts.cardHeading).foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier(AccessibilityID.AddText.results)
                Spacer(minLength: Theme.Spacing.s)
                Button { model.backToInput() } label: {
                    Text("Edit").font(Theme.Fonts.segmentSelected).foregroundStyle(Theme.Colors.forest)
                        .frame(minWidth: Theme.Size.minTouch, minHeight: Theme.Size.minTouch)
                        .contentShape(Rectangle())
                }
                .accessibilityLabel("Edit what you wrote")
                .accessibilityIdentifier(AccessibilityID.AddText.edit)
            }
            AddReviewList(model: review, showsPrice: false, idPrefix: AccessibilityID.AddText.rows)
        }
    }
}
