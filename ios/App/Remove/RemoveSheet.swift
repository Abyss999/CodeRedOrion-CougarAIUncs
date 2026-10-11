import SwiftUI

/// Remove: outcome (`RemoveSheet` artboard, SCREENS #7). Core 3 tiles. *Used it* and *Gave it
/// away* remove at once (the caller removes the row and calls the API), show a checkmark with a
/// `.success` haptic, then dismiss. *Threw it away* pushes natively to the reason step.
struct RemoveSheet: View {
    let item: Item
    let onRemove: (RemoveChoice) -> Void
    let close: () -> Void

    @State private var chosen: RemoveOutcome?
    @State private var showReason = false
    @State private var contentHeight: CGFloat = Theme.Size.removeSheetEstimate

    init(item: Item, onRemove: @escaping (RemoveChoice) -> Void, close: @escaping () -> Void) {
        self.item = item
        self.onRemove = onRemove
        self.close = close
    }

    private var hasListing: Bool { ItemText.hasOpenListing(item) }
    /// Who a donation goes to: the claimer of the open listing. The app sends no `recipient_id`;
    /// the server credits the claimer (orchestrator ruling). No claimer: nothing is shown.
    private var claimer: ItemShare.Claimant? { hasListing ? item.share?.claimedBy : nil }

    var body: some View {
        NavigationStack {
            ScrollView {
                content
                    .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { contentHeight = $0 }
            }
            .scrollBounceBehavior(.basedOnSize)
            .background(Theme.Colors.ground)
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(isPresented: $showReason) {
                RemoveReasonView(item: item) { reason in
                    onRemove(RemoveChoice(outcome: .thrownOut, wasteReason: reason))
                } close: { close() }
            }
        }
        .presentationDetents([.height(contentHeight + Theme.Spacing.l), .large])
        .presentationDragIndicator(.visible)
        .presentationCornerRadius(Theme.Radius.sheet)
        .presentationBackground(Theme.Colors.ground)
        .accessibilityIdentifier(AccessibilityID.Remove.sheet)
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sheetSection) {
            header
            Text("What happened to it?")
                .font(Theme.Fonts.rowTitle)
                .foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            VStack(spacing: Theme.Spacing.tileGap) {
                RemoveOutcomeTile(outcome: .used, subtitle: "Counts as food saved", isChosen: chosen == .used) {
                    finish(.used)
                }
                RemoveOutcomeTile(outcome: .donated,
                                  subtitle: hasListing ? "Food saved. Closes your Share listing" : "Counts as food saved",
                                  isChosen: chosen == .donated) {
                    finish(.donated)
                }
                RemoveOutcomeTile(outcome: .thrownOut, subtitle: "Counts as waste. One quick question next",
                                  isChosen: false, leadsOn: true) {
                    guard chosen == nil else { return }
                    Haptics.selection()
                    showReason = true
                }
            }
            if let claimer {
                recipientLine(claimer)
            }
            Button {
                close()
            } label: {
                Text("Cancel")
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.sheetTextButton)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(AccessibilityID.Remove.cancel)
        }
        .padding(.horizontal, Theme.Spacing.gutter)
        .padding(.top, Theme.Spacing.l)
        .padding(.bottom, Theme.Spacing.s)
    }

    private var header: some View {
        HStack(spacing: Theme.Spacing.sm) {
            FoodGroupIcon(group: item.foodGroup, tile: Theme.Size.sheetHeaderTile)
            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                Text(item.name)
                    .font(Theme.Fonts.sheetTitle)
                    .foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier(AccessibilityID.Remove.title)
                Text(ItemText.sheetMeta(item))
                    .font(Theme.Fonts.sheetMeta)
                    .foregroundStyle(Theme.Colors.muted)
            }
        }
    }

    /// Static, non-interactive: "Gave it away goes to Marcus Ojeda".
    private func recipientLine(_ claimer: ItemShare.Claimant) -> some View {
        Label {
            Text("Gave it away goes to \(claimer.name)")
                .font(Theme.Fonts.meta)
                .foregroundStyle(Theme.Colors.inkSecondary)
                .fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: "person.crop.circle")
                .font(Theme.Fonts.meta)
                .foregroundStyle(Theme.Colors.muted)
        }
        .padding(.horizontal, Theme.Spacing.xxs)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("If you gave it away, it goes to \(claimer.name), who claimed it.")
        .accessibilityIdentifier(AccessibilityID.Remove.recipient)
    }

    /// Used / gave away: the removal happens now; the sheet waits only long enough for the
    /// checkmark to land (`Theme.Motion.confirmHold`).
    private func finish(_ outcome: RemoveOutcome) {
        guard chosen == nil else { return }
        chosen = outcome
        Haptics.success()
        onRemove(RemoveChoice(outcome: outcome))
        Task {
            try? await Task.sleep(for: Theme.Motion.confirmHold)
            close()
        }
    }
}
