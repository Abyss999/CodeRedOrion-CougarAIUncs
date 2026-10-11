import SwiftUI

/// Home tab (SCREENS #4, #26, #28): tip at the top, greeting + settings gear + Impact pill,
/// "Use these first", "Cook tonight", and the HomeEmpty / skeleton / ServerError states.
///
/// Navigation that belongs to later PRs is a closure (default no-op) so this screen never reaches
/// into another screen's folder: Settings, Impact, Recipe detail, Item detail and the Settings ›
/// Debug "Server address" row all hook in through `RootTabView`.
struct HomeView: View {
    @Environment(AppEnvironment.self) private var env
    @MotionReduced private var reduceMotion
    @State private var model: HomeModel
    @State private var toast: UndoToastItem?
    @State private var undoTapped = false
    /// The tip message the person dismissed. Stored, so a dismissed tip stays gone across launches;
    /// a different tip (new message) shows again.
    @AppStorage("home.dismissedTip") private var dismissedTip = ""

    var onOpenSettings: () -> Void
    var onOpenImpact: () -> Void
    var onOpenRecipe: (Recipe) -> Void
    var onOpenItem: (Item) -> Void
    var onOpenServerSettings: () -> Void
    var onSeeAllFood: () -> Void
    var onAddFood: () -> Void

    init(api: APIClient,
         onOpenSettings: @escaping () -> Void = {},
         onOpenImpact: @escaping () -> Void = {},
         onOpenRecipe: @escaping (Recipe) -> Void = { _ in },
         onOpenItem: @escaping (Item) -> Void = { _ in },
         onOpenServerSettings: @escaping () -> Void = {},
         onSeeAllFood: @escaping () -> Void = {},
         onAddFood: @escaping () -> Void = {}) {
        _model = State(initialValue: HomeModel(api: api))
        self.onOpenSettings = onOpenSettings
        self.onOpenImpact = onOpenImpact
        self.onOpenRecipe = onOpenRecipe
        self.onOpenItem = onOpenItem
        self.onOpenServerSettings = onOpenServerSettings
        self.onSeeAllFood = onSeeAllFood
        self.onAddFood = onAddFood
    }

    private var firstName: String? {
        env.auth.user?.displayName.split(separator: " ").first.map(String.init)
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l) {
                HomeHeader(name: firstName,
                           savedKg: isError ? nil : model.savedKg,
                           onOpenSettings: onOpenSettings,
                           onOpenImpact: onOpenImpact)
                if showsOfflineBanner {
                    HomeOfflineBanner(message: bannerMessage) { Task { await retry() } }
                        .motionTransition(.opacity)
                }
                content
                VersionLabel()
                    .frame(maxWidth: .infinity)
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.s)
            .padding(.bottom, Theme.Spacing.l)
        }
        .refreshable { await model.refresh() }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .accessibilityIdentifier(AccessibilityID.Home.screen)
        .motionAnimation(Theme.Motion.quick, value: dismissedTip)
        .motionAnimation(Theme.Motion.quick, value: model.refreshFailed)
        .undoToast(item: $toast)
        .task {
            await model.loadIfNeeded()
            #if DEBUG
            if env.launch.showToast, toast == nil {
                toast = UndoToastItem(message: "Baby spinach removed", onUndo: { undoTapped = true })
            }
            #endif
        }
        .overlay(alignment: .topLeading) {
            #if DEBUG
            if undoTapped {
                Text("Undo tapped")
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.muted)
                    .accessibilityIdentifier(AccessibilityID.Toast.marker)
            }
            #endif
        }
    }

    // MARK: State

    private var isError: Bool { if case .error = model.state { true } else { false } }

    private var showsOfflineBanner: Bool { isError || model.refreshFailed }

    private var bannerMessage: String {
        if case .error(let error) = model.state, !((error as? APIError)?.isNetwork ?? false) {
            return "BiteDown ran into a problem. Try again."
        }
        return "Can't reach BiteDown. Check your connection."
    }

    private func retry() async {
        if isError { await model.retry() } else { await model.refresh() }
    }

    // MARK: Content

    @ViewBuilder private var content: some View {
        switch model.state {
        case .loading:
            loading
        case .error:
            section("Use these first") {
                HomeErrorCard(host: env.baseURL.current.host() ?? env.baseURL.current.absoluteString,
                              retry: { Task { await model.retry() } },
                              onChangeServer: onOpenServerSettings)
            }
        case .empty:
            loaded(empty: true)
        case .content:
            loaded(empty: false)
        }
    }

    private var loading: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            section("Use these first") {
                SkeletonList(screen: AccessibilityID.Home.screen, count: HomeModel.useFirstLimit)
            }
            section("Cook tonight") {
                RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
                    .fill(Theme.Colors.limeTint)
                    .frame(height: 112)
                    .shimmering()
                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .accessibilityHidden(true)
            }
        }
        .motionTransition(.opacity)
    }

    @ViewBuilder private func loaded(empty: Bool) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.l) {
            if let tip = model.tip, tip.message != dismissedTip {
                HomeTipCard(message: tip.message) { dismissedTip = tip.message }
                    .staggeredAppearance(index: 0, controller: model.stagger)
                    .motionTransition(.opacity)
            }
            section("Use these first", trailing: empty ? nil : AnyView(seeAll)) {
                if empty { emptyUseFirst } else { useFirstList }
            }
            .staggeredAppearance(index: 1, controller: model.stagger)
            section("Cook tonight") {
                if let recipe = model.recipe {
                    HomeCookCard(recipe: recipe) { onOpenRecipe(recipe) }
                } else {
                    HomeCookPlaceholder(text: model.recipesUnavailable
                                        ? "Recipes aren't available right now. Pull down to try again."
                                        : "Recipes appear once you've added a few items")
                }
            }
            .staggeredAppearance(index: 2, controller: model.stagger)
        }
        .motionTransition(.opacity)
    }

    private var seeAll: some View {
        Button(action: onSeeAllFood) {
            Text("See all")
                .font(Theme.Fonts.body.weight(.medium))
                .foregroundStyle(Theme.Colors.forest)
                .frame(minHeight: Theme.Size.minTouch)
                .padding(.leading, Theme.Spacing.s)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("See all food")
        .accessibilityIdentifier(AccessibilityID.Home.seeAll)
    }

    private var useFirstList: some View {
        VStack(spacing: 0) {
            ForEach(Array(model.useFirst.enumerated()), id: \.element.id) { index, item in
                HomeItemRow(item: item) { onOpenItem(item) }
                if index < model.useFirst.count - 1 { Divider().overlay(Theme.Colors.hairline) }
            }
        }
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Home.useFirst)
    }

    /// HomeEmpty: an Add food card in place of the list.
    private var emptyUseFirst: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm + Theme.Spacing.xxs) {
            HStack(spacing: Theme.Spacing.sm) {
                Image(systemName: "refrigerator")
                    .font(.title3)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(width: Theme.Size.avatar, height: Theme.Size.avatar)
                    .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.avatar, style: .continuous))
                    .accessibilityHidden(true)
                Text("Add food and we'll show what to use first")
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Button(action: onAddFood) {
                Text("Add food")
                    .font(Theme.Fonts.button)
                    .foregroundStyle(Theme.Colors.onForest)
                    .padding(.horizontal, Theme.Spacing.l - Theme.Spacing.xxs)
                    .frame(minWidth: 120, minHeight: Theme.Size.minTouch)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(AccessibilityID.Home.addFood)
        }
        .padding(.horizontal, Theme.Spacing.m)
        .padding(.vertical, Theme.Spacing.gutter)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.State.empty(AccessibilityID.Home.screen))
    }

    private func section<Body: View>(_ title: String, trailing: AnyView? = nil,
                                     @ViewBuilder _ body: () -> Body) -> some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.tileGap) {
            HStack(alignment: .firstTextBaseline) {
                Text(title)
                    .font(Theme.Fonts.section)
                    .foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: 0)
                trailing
            }
            body()
        }
    }
}
