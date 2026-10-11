import SwiftUI

/// Fridge tab (`Fridge` artboard, SCREENS #5): storage filter, items grouped by food group,
/// swipe → Remove, Undo toast, and the empty / loading / error states. Pull to refresh never
/// replays the stagger; it runs on each storage's first load only.
struct FridgeView: View {
    @Environment(AppEnvironment.self) private var env
    @MotionReduced private var reduceMotion
    @State private var model: FridgeModel
    @State private var removing: Item?

    private let screen = AccessibilityID.Fridge.screen

    init(api: APIClient) {
        _model = State(initialValue: FridgeModel(api: api))
    }

    var body: some View {
        List {
            header
            content
        }
        .listStyle(.insetGrouped)
        .listSectionSpacing(Theme.Spacing.m)
        .scrollContentBackground(.hidden)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .accessibilityIdentifier(AccessibilityID.Fridge.list)
        .refreshable { await model.refresh() }
        .safeAreaInset(edge: .top, spacing: 0) {
            if let banner = model.banner {
                FridgeBannerView(banner: banner) { model.banner = nil }
                    .padding(.vertical, Theme.Spacing.s)
                    .motionTransition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .motionAnimation(Theme.Motion.standard, value: model.banner?.id)
        .undoToast(item: $model.toast)
        .task(id: model.storage) { await model.loadIfNeeded(model.storage) }
        .onReceive(NotificationCenter.default.publisher(for: .itemsDidChange)) { _ in Task { await model.refresh() } }
        // The Undo toast appears (and its countdown starts) only after the sheet has gone.
        .sheet(item: $removing, onDismiss: { model.showPendingToast() }) { item in
            RemoveSheet(item: item) { choice in
                model.remove(item, choice: choice, reduceMotion: reduceMotion)
            } close: {
                removing = nil
            }
        }
        .overlay(alignment: .topLeading) { probes }
    }

    // MARK: Header

    /// Title and storage filter scroll with the list (so AX5 text doesn't pin half the screen).
    private var header: some View {
        Section {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                Text("Your food")
                    .font(Theme.Fonts.screenTitle)
                    .foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier(AccessibilityID.Fridge.title)
                StorageSegmentedControl(selection: $model.storage)
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets(top: Theme.Spacing.s, leading: 0, bottom: 0, trailing: 0))
            .listRowSeparator(.hidden)
        }
    }

    // MARK: Content

    @ViewBuilder private var content: some View {
        switch model.state(for: model.storage) {
        case .loading:
            stateRow { SkeletonList(screen: screen) }
        case .error(let error):
            stateRow {
                ErrorStateView(screen: screen, error: error) {
                    Task { await model.retry(model.storage) }
                }
            }
        case .empty:
            stateRow {
                EmptyStateView(screen: screen,
                               title: "Nothing in your \(model.storage.displayName.lowercased())",
                               message: "Food you add with the + tab shows up here, grouped by type.",
                               systemImage: model.storage == .freezer ? "snowflake" : "refrigerator")
            }
        case .content(let sections):
            ForEach(Array(sections.enumerated()), id: \.element.id) { sectionIndex, section in
                Section {
                    ForEach(section.items) { item in
                        row(item, staggerIndex: staggerIndex(sections, section: sectionIndex, item: item))
                    }
                } header: {
                    FridgeGroupHeader(section: section)
                        .staggeredAppearance(index: staggerIndex(sections, section: sectionIndex, item: nil),
                                             controller: model.stagger)
                }
            }
        }
    }

    private func row(_ item: Item, staggerIndex: Int) -> some View {
        FridgeItemRow(item: item)
            .staggeredAppearance(index: staggerIndex, controller: model.stagger)
            .listRowBackground(Theme.Colors.surface)
            .listRowSeparatorTint(Theme.Colors.hairline)
            .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                Button {
                    presentRemove(item)
                } label: {
                    Label("Remove", systemImage: "checkmark")
                }
                .tint(Theme.Colors.forest)
                .accessibilityIdentifier(AccessibilityID.Fridge.rowRemove(item.id))
            }
            .accessibilityAction(named: "Remove") { presentRemove(item) }
    }

    /// Cross-fades between states; a single full-width row with no card behind it.
    private func stateRow<V: View>(@ViewBuilder _ view: () -> V) -> some View {
        Section {
            view()
                .motionTransition(.opacity)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
                .listRowSeparator(.hidden)
        }
    }

    /// Position in reading order (headers and rows together), so the first screenful staggers
    /// top to bottom. Items past the cap share the last delay (`Theme.Motion.staggerDelay`).
    private func staggerIndex(_ sections: [ItemSection], section: Int, item: Item?) -> Int {
        var index = 0
        for s in sections.prefix(section) { index += 1 + s.items.count }
        guard let item else { return index }
        return index + 1 + (sections[section].items.firstIndex(of: item) ?? 0)
    }

    private func presentRemove(_ item: Item) {
        removing = item
    }

    // MARK: DEBUG probes

    @ViewBuilder private var probes: some View {
        #if DEBUG
        if env.launch.useMockAPI {
            VStack(spacing: 0) {
                DebugProbe(id: AccessibilityID.Probe.staggerCount, value: "\(model.staggerRestarts)")
                if let recorder = env.hapticsRecorder {
                    DebugProbe(id: AccessibilityID.Probe.haptics, value: recorder.joined)
                }
            }
        }
        #endif
    }
}
