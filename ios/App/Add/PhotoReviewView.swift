import SwiftUI

/// PhotoReview: what was found, a "Looks spoiled" section to decide on, and Add N items.
/// Rows are the shared `DetectedItemRow` with a `QuantityStepper` and the inline amount editor.
struct PhotoReviewView: View {
    @Bindable var model: PhotoReviewModel
    let photo: UIImage?
    let photoPixelSize: CGSize
    let onBack: () -> Void
    let onAddMissed: () -> Void
    let onFinished: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @MotionReduced private var reduceMotion
    @State private var shown = false

    var body: some View {
        Group { content }
            .onChange(of: model.phase) { _, phase in
                // Everything went through: close the sheet. With a failed toss the done view stays up.
                if case .done = phase, model.tossFailures.isEmpty { onFinished() }
            }
    }

    @ViewBuilder private var content: some View {
        if case .done(let added) = model.phase, !model.tossFailures.isEmpty {
            doneView(added: added)
        } else {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Spacing.sm + 2) {
                        header
                        // Collapsed at accessibility sizes, so the list gets the room.
                        if !dynamicTypeSize.isAccessibilitySize { photoBlock }
                        if !model.spoiledIndices.isEmpty { spoiledSection }
                        foundList
                        Button(action: onAddMissed) {
                            Text("+ Add something we missed")
                                .font(Theme.Fonts.segmentSelected)
                                .foregroundStyle(Theme.Colors.forest)
                                .frame(minHeight: Theme.Size.minTouch)
                                .contentShape(Rectangle())
                        }
                        .accessibilityIdentifier(AccessibilityID.PhotoReview.missed)
                    }
                    .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.m)
                }
                .scrollBounceBehavior(.basedOnSize)
                footer
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(AccessibilityID.PhotoReview.screen)
            .onAppear { shown = true }
        }
    }

    // MARK: Header and photo

    private var header: some View {
        HStack(spacing: Theme.Spacing.tileGap) {
            BackButton(action: onBack, id: AccessibilityID.PhotoReview.back)
            Text(model.title)
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(AccessibilityID.PhotoReview.title)
            Spacer(minLength: 0)
        }
    }

    @ViewBuilder private var photoBlock: some View {
        if let photo {
            let boxes = model.rows.enumerated().compactMap { i, row -> DetectionBox? in
                // No `bbox` (the Gemini fallback): no box for that item.
                DetectionBox.normalized(row.candidate.bbox, pixelSize: photoPixelSize)
                    .map { DetectionBox(id: i, rect: $0, isOn: row.isSpoiled ? row.decision != .toss : row.isOn) }
            }
            PhotoBoxOverlay(photo: photo, boxes: boxes, height: Theme.AddFlow.reviewPhotoHeight)
        }
    }

    // MARK: Looks spoiled

    private var spoiledSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.stack) {
            Label {
                Text("Looks spoiled").textCase(.uppercase).tracking(Theme.Tracking.groupHeader)
            } icon: {
                Image(systemName: "exclamationmark.triangle")
            }
            .font(Theme.Fonts.groupHeader)
            .fixedSize(horizontal: false, vertical: true)
            .foregroundStyle(Theme.Colors.urgentInk)
            .accessibilityAddTraits(.isHeader)
            VStack(spacing: 0) {
                ForEach(model.spoiledIndices, id: \.self) { i in
                    spoiledRow(i)
                    if i != model.spoiledIndices.last { Divider().overlay(Theme.Colors.hairline) }
                }
            }
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        }
        .accessibilityIdentifier(AccessibilityID.PhotoReview.spoiledSection)
    }

    private func spoiledRow(_ i: Int) -> some View {
        let row = model.rows[i]
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        return layout {
            HStack(spacing: Theme.Spacing.sm) {
                FoodGroupIcon(group: row.candidate.foodGroup)
                Text(row.candidate.name)
                    .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: Theme.Spacing.s) {
                decisionButton("Toss it", tint: Theme.Colors.urgentInk, fill: Theme.Colors.urgentBg,
                               selected: row.decision == .toss, label: "Toss \(row.candidate.name)", id: AccessibilityID.PhotoReview.toss(i)) { model.decide(.toss, at: i) }
                decisionButton("Keep it", tint: Theme.Colors.forest, fill: Theme.Colors.limeTint,
                               selected: row.decision == .keep, label: "Keep \(row.candidate.name)", id: AccessibilityID.PhotoReview.keep(i)) { model.decide(.keep, at: i) }
            }
        }
        .padding(.vertical, Theme.Spacing.sm - 2).padding(.leading, Theme.Spacing.m - 2).padding(.trailing, Theme.Spacing.sm - 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.PhotoReview.row(i))
    }

    private func decisionButton(_ title: String, tint: Color, fill: Color, selected: Bool, label: String, id: String,
                                action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: Theme.Spacing.xs) {
                if selected { Image(systemName: "checkmark").font(Theme.Fonts.badge) }
                Text(title).font(Theme.Fonts.segmentSelected)
            }
            .foregroundStyle(tint)
            .padding(.horizontal, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.minTouch)
            .background(selected ? fill : Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                    .strokeBorder(selected ? tint : Theme.Colors.border, lineWidth: selected ? Theme.Stroke.selected : Theme.Stroke.hairline)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(id)
    }

    // MARK: Found items

    private var foundList: some View {
        let found = model.foundIndices
        return VStack(spacing: 0) {
            ForEach(Array(found.enumerated()), id: \.element) { position, i in
                foundRow(i)
                    .opacity(shown || reduceMotion ? 1 : 0)
                    .animation(Theme.Motion.animation(Theme.Motion.staggerItem.delay(Theme.Motion.staggerDelay(index: position)), reduceMotion: reduceMotion), value: shown)
                if position != found.count - 1 { Divider().overlay(Theme.Colors.hairline) }
            }
        }
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
    }

    private func foundRow(_ i: Int) -> some View {
        let row = model.rows[i]
        let ids = DetectedRowIdentifiers(row: AccessibilityID.PhotoReview.row(i), check: AccessibilityID.PhotoReview.rowCheck(i),
                                         badge: AccessibilityID.PhotoReview.badge(i))
        return DetectedItemRow(
            content: row.content,
            isOn: Binding(get: { model.rows[i].isOn }, set: { model.setOn($0, at: i) }),
            ids: ids,
            trailing: {
                QuantityStepper(
                    name: row.candidate.name,
                    amount: Binding(get: { model.rows[i].amount }, set: { model.setAmount($0, at: i) }),
                    unit: row.unit, isEditing: row.isEditing,
                    onEditAmount: { withMotion(reduceMotion: reduceMotion) { model.setEditing(!model.rows[i].isEditing, at: i) } },
                    ids: (AccessibilityID.PhotoReview.less(i), AccessibilityID.PhotoReview.more(i), AccessibilityID.PhotoReview.amountButton(i)))
            },
            expansion: {
                if row.isEditing {
                    QuantityEditor(
                        name: row.candidate.name,
                        amount: Binding(get: { model.rows[i].amount }, set: { model.setAmount($0, at: i) }),
                        unit: Binding(get: { model.rows[i].unit }, set: { model.setUnit($0, at: i) }),
                        ids: (AccessibilityID.PhotoReview.amountField(i), AccessibilityID.PhotoReview.unitMenu(i), AccessibilityID.PhotoReview.amountDone(i)),
                        onDone: { withMotion(reduceMotion: reduceMotion) { model.setEditing(false, at: i) } })
                        .motionTransition(.opacity.combined(with: .move(edge: .top)))
                }
            })
    }

    // MARK: Footer

    private var footer: some View {
        VStack(spacing: Theme.Spacing.s) {
            if let error = model.addError {
                BannerView(style: .error, message: error, retryTitle: "Try again", retry: { Task { await model.confirm() } },
                           identifiers: BannerIdentifiers(container: AccessibilityID.PhotoReview.error, retry: AccessibilityID.PhotoReview.errorRetry),
                           horizontalInset: 0)
            }
            if model.undecidedCount > 0 {
                Text("Decide on spoiled items to continue")
                    .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                    .accessibilityIdentifier(AccessibilityID.PhotoReview.hint)
            }
            Button { Task { await model.confirm() } } label: {
                Group {
                    if model.phase == .saving {
                        ProgressView().tint(Theme.Colors.onForest)
                    } else {
                        Text(confirmTitle).numericChange(value: model.addCount)
                    }
                }
                .font(Theme.Fonts.button)
                .foregroundStyle(Theme.Colors.onForest)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                .contentShape(Rectangle())
            }
            .disabled(!model.canConfirm)
            .opacity(model.canConfirm || model.phase == .saving ? 1 : 0.45)
            .accessibilityLabel(model.phase == .saving ? "Adding" : confirmTitle)
            .accessibilityIdentifier(AccessibilityID.PhotoReview.confirm)
        }
        .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.sm).padding(.bottom, Theme.Spacing.m)
        .background(Theme.Colors.ground)
        .overlay(alignment: .top) { Divider().overlay(Theme.Colors.hairline) }
    }

    private var confirmTitle: String {
        if model.addCount > 0 { return model.addCount == 1 ? "Add 1 item" : "Add \(model.addCount) items" }
        return model.tossCount > 0 ? "Done" : "Add 0 items"
    }

    // MARK: Done (only shown when a toss failed; otherwise the sheet closes)

    private func doneView(added: Int) -> some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.m) {
                Image(systemName: "checkmark")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(width: Theme.AddFlow.statusDisc, height: Theme.AddFlow.statusDisc)
                    .background(Theme.Colors.limeTint, in: Circle())
                    .accessibilityHidden(true)
                Text(added == 0 ? "All done" : (added == 1 ? "Added 1 item" : "Added \(added) items"))
                    .font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array(model.tossFailures.enumerated()), id: \.element.id) { n, failure in
                    BannerView(style: .error,
                               message: "Couldn't mark \(failure.name) as thrown out. It's in your fridge as Looks off.",
                               retryTitle: "Try again",
                               retry: { Task { await model.retryToss(failure) } },
                               identifiers: BannerIdentifiers(container: AccessibilityID.PhotoReview.tossBanner(n)),
                               horizontalInset: 0)
                }
                Button(action: onFinished) {
                    Text("Done").font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier(AccessibilityID.PhotoReview.doneButton)
            }
            .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.xl)
        }
        .accessibilityIdentifier(AccessibilityID.PhotoReview.done)
        .onChange(of: model.tossFailures.isEmpty) { _, empty in if empty { onFinished() } }
    }
}
