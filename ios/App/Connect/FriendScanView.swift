import SwiftUI
import VisionKit

/// FriendScan artboard: a QR scanner (DataScannerViewController) that adds the friend on a hit.
/// Simulator / unsupported devices get a DEBUG-only manual code field. Shows `FriendAddedView` on success.
struct FriendScanView: View {
    @State var model: FriendAddModel
    let close: () -> Void
    /// A code from a deep link that requires confirmation before submission.
    var initialCode: String?
    @FocusState private var manualFocused: Bool

    init(api: APIClient, initialCode: String? = nil, close: @escaping () -> Void) {
        _model = State(initialValue: FriendAddModel(api: api))
        self.initialCode = initialCode
        self.close = close
    }

    private var scannerAvailable: Bool { DataScannerViewController.isSupported && DataScannerViewController.isAvailable }

    var body: some View {
        Group {
            if let result = model.result {
                FriendAddedView(result: result, scanAnother: initialCode == nil ? { model.reset() } : nil, done: close)
                    .navigationBarBackButtonHidden()
            } else if let initialCode {
                confirmBody(code: initialCode)
            } else {
                scanBody
            }
        }
    }

    private func confirmBody(code: String) -> some View {
        VStack(spacing: Theme.Spacing.m) {
            Spacer()
            Text("Add this person as a friend?")
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.ink)
                .multilineTextAlignment(.center)
            if model.isAdding {
                ProgressView("Adding friend")
            }
            if let message = model.errorMessage {
                Text(message)
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.urgentInk)
            }
            Spacer()
            Button("Add") { model.submit(payload: code) }
                .disabled(model.isAdding)
                .accessibilityIdentifier(AccessibilityID.FriendScan.confirmAdd)
            Button("Cancel", action: close)
                .accessibilityIdentifier(AccessibilityID.FriendScan.confirmCancel)
        }
        .padding(Theme.Spacing.gutter)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .accessibilityIdentifier(AccessibilityID.FriendScan.confirm)
    }

    private var scanBody: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.m) {
                scanner
                    .frame(maxWidth: .infinity)
                    .frame(height: Theme.Size.scanWindow)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous)
                            .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline)
                    }
                if model.isAdding {
                    ProgressView("Adding friend")
                        .font(Theme.Fonts.meta)
                        .foregroundStyle(Theme.Colors.muted)
                }
                if let message = model.errorMessage {
                    Label(message, systemImage: "exclamationmark.circle.fill")
                        .font(Theme.Fonts.meta.weight(.semibold))
                        .foregroundStyle(Theme.Colors.urgentInk)
                        .padding(Theme.Spacing.sm)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.Colors.urgentBg, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                        .accessibilityIdentifier(AccessibilityID.FriendScan.error)
                        .onAppear { AccessibilityNotification.Announcement(message).post() }
                }
                #if DEBUG
                manualEntry
                #endif
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.vertical, Theme.Spacing.m)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .navigationTitle("Scan a friend's code")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier(AccessibilityID.FriendScan.screen)
    }

    @ViewBuilder private var scanner: some View {
        if scannerAvailable {
            FriendQRScanner { model.submit(payload: $0) }
                .accessibilityLabel("Camera. Point it at a friend's BiteDown code.")
                .accessibilityIdentifier(AccessibilityID.FriendScan.scanner)
        } else {
            VStack(spacing: Theme.Spacing.s) {
                Image(systemName: "qrcode.viewfinder").font(.largeTitle)
                Text(DataScannerViewController.isSupported
                     ? "Camera access is off. Allow it in Settings to scan a code."
                     : "This device can't scan codes.")
                    .font(Theme.Fonts.callout)
                    .multilineTextAlignment(.center)
            }
            .foregroundStyle(Theme.Colors.muted)
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Theme.Colors.limeTint)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(AccessibilityID.FriendScan.scanner)
        }
    }

    #if DEBUG
    private var manualEntry: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            Text("Type a code instead")
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.inkSecondary)
            HStack(spacing: Theme.Spacing.s) {
                TextField("Code or bitedown:// link", text: $model.manualText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($manualFocused)
                    .submitLabel(.go)
                    .onSubmit { model.submit(payload: model.manualText) }
                    .font(Theme.Fonts.body)
                    .foregroundStyle(Theme.Colors.ink)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .frame(minHeight: Theme.Size.connectControl)
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                            .strokeBorder(manualFocused ? Theme.Colors.forest : Theme.Colors.border,
                                          lineWidth: manualFocused ? Theme.Stroke.selected : Theme.Stroke.hairline)
                    }
                    .accessibilityLabel("Friend code")
                    .accessibilityIdentifier(AccessibilityID.FriendScan.manualField)
                Button { model.submit(payload: model.manualText) } label: {
                    Text("Add")
                        .font(Theme.Fonts.badge)
                        .foregroundStyle(Theme.Colors.onForest)
                        .padding(.horizontal, Theme.Spacing.m)
                        .frame(minHeight: Theme.Size.connectControl)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                }
                .disabled(model.isAdding || model.manualText.trimmingCharacters(in: .whitespaces).isEmpty)
                .accessibilityIdentifier(AccessibilityID.FriendScan.manualAdd)
            }
            Text("Debug only. Try friend-ana on the mock API.")
                .font(Theme.Fonts.meta)
                .foregroundStyle(Theme.Colors.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    #endif
}

/// `DataScannerViewController` limited to QR codes. Reports each recognised payload string.
struct FriendQRScanner: UIViewControllerRepresentable {
    let onCode: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let vc = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
                                           qualityLevel: .balanced, recognizesMultipleItems: false,
                                           isHighFrameRateTrackingEnabled: false, isPinchToZoomEnabled: true,
                                           isGuidanceEnabled: false, isHighlightingEnabled: true)
        vc.delegate = context.coordinator
        try? vc.startScanning()
        return vc
    }

    func updateUIViewController(_ uiViewController: DataScannerViewController, context: Context) {
        context.coordinator.onCode = onCode
    }

    static func dismantleUIViewController(_ uiViewController: DataScannerViewController, coordinator: Coordinator) {
        uiViewController.stopScanning()
    }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        var onCode: (String) -> Void
        private var lastPayload: String?
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            for case .barcode(let b) in addedItems {
                guard let payload = b.payloadStringValue, payload != lastPayload else { continue }
                lastPayload = payload
                onCode(payload)
                return
            }
        }
    }
}
