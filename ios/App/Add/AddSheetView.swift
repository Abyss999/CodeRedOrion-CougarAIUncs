import SwiftUI
import PhotosUI

/// The sheet the Add tab presents: the menu (AddSheet, or CameraDenied when camera access is off), then the
/// photo path (PhotoAnalyzing -> PhotoReview / PhotoReviewError). Text, barcode and receipt land on a
/// placeholder until the next PR.
struct AddSheetView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @State private var flow: AddFlowModel?
    @State private var cameraDenied = false
    @State private var cameraMode: PhotoMode?
    @State private var libraryMode: PhotoMode = .fridge
    @State private var showLibrary = false
    @State private var pickedItem: PhotosPickerItem?
    @State private var detent: PresentationDetent = .medium

    var body: some View {
        Group {
            if let flow { content(flow) } else { Color.clear }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .presentationDetents(flow?.isMenu ?? true ? [.medium, .large] : [.large], selection: $detent)
        .presentationDragIndicator(.visible)
        .presentationCornerRadius(Theme.Radius.sheet)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Add.sheet)
        .task {
            if flow == nil { flow = AddFlowModel(api: env.api) }
            refreshCameraAccess()
            if dynamicTypeSize.isAccessibilitySize { detent = .large }
        }
        .onChange(of: scenePhase) { _, phase in if phase == .active { refreshCameraAccess() } }
        .onChange(of: flow?.stage) { _, stage in if let stage, stage != .menu { detent = .large } }
        .fullScreenCover(item: $cameraMode) { mode in
            CameraPicker(onImage: { image in cameraMode = nil; flow?.analyze(image: image, mode: mode) },
                         onCancel: { cameraMode = nil })
                .ignoresSafeArea()
        }
        .photosPicker(isPresented: $showLibrary, selection: $pickedItem, matching: .images)
        .onChange(of: pickedItem) { _, item in
            guard let item else { return }
            pickedItem = nil
            Task {
                if let data = try? await item.loadTransferable(type: Data.self), let image = UIImage(data: data) {
                    flow?.analyze(image: image, mode: libraryMode)
                }
            }
        }
    }

    @ViewBuilder private func content(_ flow: AddFlowModel) -> some View {
        switch flow.stage {
        case .menu:
            menu(flow)
        case .analyzing:
            PhotoAnalyzingView(photo: flow.photo, onCancel: { flow.cancel() })
        case .review:
            if let review = flow.review {
                PhotoReviewView(model: review, photo: flow.photo, photoPixelSize: flow.photoPixelSize,
                                onBack: { flow.reset() }, onAddMissed: { flow.open(.text) }, onFinished: { dismiss() })
            }
        case .none:
            PhotoReviewErrorView(kind: .noFood, photo: flow.photo,
                                 onBack: { flow.reset() }, onRetry: { flow.run() },
                                 onRetake: { retake(flow) }, onType: { flow.open(.text) })
        case .failed(let failure):
            PhotoReviewErrorView(kind: .failed(failure.message), photo: flow.photo,
                                 onBack: { flow.reset() }, onRetry: { flow.run() },
                                 onRetake: { retake(flow) }, onType: { flow.open(.text) })
        case .destination(let destination):
            AddDestinationView(destination: destination, onBack: { flow.reset() }, onOpen: { flow.open($0) }, onFinished: { dismiss() })
        }
    }

    // MARK: Menu

    private func menu(_ flow: AddFlowModel) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.sheetSection) {
                header
                if cameraDenied { deniedMenu(flow) } else { enabledMenu(flow) }
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.m)
            .padding(.bottom, Theme.Spacing.xl)
        }
        .scrollBounceBehavior(.basedOnSize)
    }

    private var header: some View {
        HStack {
            Text("Add food")
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: Theme.Spacing.s)
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(Theme.Fonts.badge)
                    .foregroundStyle(Theme.Colors.forest)
                    .padding(Theme.Spacing.sm)
                    .frame(minWidth: Theme.Size.minTouch, minHeight: Theme.Size.minTouch)
                    .background(Theme.Colors.surface, in: Circle())
                    .overlay { Circle().strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                    .contentShape(Circle())
            }
            .accessibilityLabel("Close")
            .accessibilityIdentifier(AccessibilityID.Add.close)
        }
    }

    private var columns: [GridItem] {
        let count = dynamicTypeSize.isAccessibilitySize ? 1 : 2
        return Array(repeating: GridItem(.flexible(), spacing: Theme.Spacing.tileGap), count: count)
    }

    /// The Receipt tile is unavailable while OCR isn't live (the live backend answers 502). The mock (UI tests,
    /// demos) keeps it on.
    private var receiptAvailable: Bool { env.launch.useMockAPI && !env.launch.receiptUnavailable }

    private func enabledMenu(_ flow: AddFlowModel) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sheetSection) {
            HeroTile(title: "Snap a photo", subtitle: "Your whole fridge, or just one item", state: .enabled) { capture(.fridge, flow) }
            LazyVGrid(columns: columns, spacing: Theme.Spacing.tileGap) {
                OptionTile(key: "text", symbol: "keyboard", title: "Type it", subtitle: "\"2 lb chicken, milk\"", state: .enabled) { flow.open(.text) }
                OptionTile(key: "say", symbol: "mic.fill", title: "Say it", subtitle: "\"Two lemons and some milk\"", state: .enabled) { flow.open(.say) }
                OptionTile(key: "barcode", symbol: "barcode", title: "Barcode", subtitle: "Boxes, cans, jars", state: .enabled) { flow.open(.barcode) }
                OptionTile(key: "receipt", symbol: "receipt", title: "Receipt", subtitle: receiptAvailable ? "Add a whole shop" : "Not available right now",
                           state: receiptAvailable ? .enabled : .unavailable("Unavailable")) { flow.open(.receipt) }
            }
            Button { libraryMode = .fridge; showLibrary = true } label: {
                Text("Choose a photo from your library")
                    .font(Theme.Fonts.segmentSelected)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier(AccessibilityID.Add.library)
        }
    }

    /// CameraDenied: the permission card, camera options shown as "Off", typing still works.
    private func deniedMenu(_ flow: AddFlowModel) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sheetSection) {
            PermissionCard(kind: .camera, alternativeTitle: "Type it instead", alternative: { flow.open(.text) })
                .padding(.horizontal, -Theme.Spacing.gutter)   // the card insets itself
            HeroTile(title: "Snap a photo", subtitle: nil, state: .off) {}
            LazyVGrid(columns: columns, spacing: Theme.Spacing.tileGap) {
                OptionTile(key: "text", symbol: "keyboard", title: "Type it", subtitle: "\"2 lb chicken, milk\"", state: .enabled) { flow.open(.text) }
                OptionTile(key: "say", symbol: "mic.fill", title: "Say it", subtitle: "\"Two lemons and some milk\"", state: .enabled) { flow.open(.say) }
                OptionTile(key: "barcode", symbol: "barcode", title: "Barcode", subtitle: nil, state: .off) {}
                OptionTile(key: "receipt", symbol: "receipt", title: "Receipt", subtitle: nil, state: .off) {}
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Add.cameraDenied)
    }

    // MARK: Capture

    private func refreshCameraAccess() { cameraDenied = CameraAccess.isDenied(launch: env.launch) }

    private func capture(_ mode: PhotoMode, _ flow: AddFlowModel) {
        if CameraAccess.isDenied(launch: env.launch) { cameraDenied = true; return }
        if env.launch.useMockAPI {
            // The camera can't run in the Simulator or UI tests: use a stand-in photo.
            flow.analyze(image: MockPhoto.image(), mode: mode)
        } else if CameraAccess.hasCamera {
            cameraMode = mode
        } else {
            libraryMode = mode
            showLibrary = true
        }
    }

    private func retake(_ flow: AddFlowModel) {
        flow.reset()
        capture(flow.mode, flow)
    }
}

extension PhotoMode: Identifiable {
    var id: String { rawValue }
}
