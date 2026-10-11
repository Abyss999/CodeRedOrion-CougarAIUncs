import SwiftUI
import PhotosUI

/// Item detail (`ItemDetail` artboard) and, once someone has claimed the item's open listing,
/// ItemShared (round 4): editable fields saved with `PATCH /items/:id`, "Check again", "What to look
/// for", the share switch with an audience picker, and the pickup spot.
///
/// Entry point: `ItemDetailView(item:)`. Push it inside a `NavigationStack`. `onChange` fires once
/// when the screen goes away after something was saved, so the list can refresh; `onRemove` lets the
/// Fridge run its optimistic removal with Undo (without it the item is removed directly).
struct ItemDetailView: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss
    @State private var model: ItemDetailModel
    @State private var photoSelection: PhotosPickerItem?
    @State private var showAudience = false
    @State private var showPickup = false
    @State private var removing: Item?
    @State private var removed = false

    private let onChange: ((Item) -> Void)?
    private let onRemove: ((Item, RemoveChoice) -> Void)?

    init(item: Item, onChange: ((Item) -> Void)? = nil, onRemove: ((Item, RemoveChoice) -> Void)? = nil) {
        _model = State(initialValue: ItemDetailModel(item: item))
        self.onChange = onChange
        self.onRemove = onRemove
    }

    /// An open listing with a claimer: the ItemShared layout.
    private var isSharedLayout: Bool { model.isShared && model.claimer != nil }

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.sm) {
                titleRow
                ItemFieldsCard(model: model, photoSelection: $photoSelection)
                WhatToLookForSection(group: model.item.foodGroup)
                if isSharedLayout {
                    SharedPantryCard(model: model) { showPickup = true }
                } else {
                    ShareSwitchCard(model: model, onSwitch: handleSwitch) { showPickup = true }
                }
                actions
                footer
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.vertical, Theme.Spacing.s)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                Button {
                    Task { if await model.save() { dismiss() } }
                } label: {
                    Text(model.isSaving ? "Saving…" : "Save").fontWeight(.semibold)
                        .frame(minHeight: Theme.Size.minTouch)
                }
                .disabled(!model.isDirty || model.isSaving)
                .accessibilityIdentifier(AccessibilityID.ItemDetail.save)
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            if let notice = model.notice {
                BannerView(style: notice.style, message: notice.message, dismiss: { model.notice = nil },
                           identifiers: BannerIdentifiers(container: AccessibilityID.ItemDetail.banner))
                    .padding(.vertical, Theme.Spacing.s)
                    .motionTransition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .motionAnimation(Theme.Motion.standard, value: model.notice)
        .onAppear { model.api = env.api }
        .onDisappear { if model.didChange && !removed { onChange?(model.item) } }
        .onChange(of: photoSelection) { _, picked in
            guard let picked else { return }
            Task {
                defer { photoSelection = nil }
                if let data = try? await picked.loadTransferable(type: Data.self) {
                    await model.checkAgain(imageData: data)
                } else {
                    model.notice = .init(style: .error, message: "Couldn't read that photo.")
                }
            }
        }
        .sheet(isPresented: $showAudience) {
            ShareAudienceSheet(groups: model.groups, loading: model.groupsLoading, error: model.groupsError,
                               retry: { Task { await model.loadGroups() } }) { audience in
                Task { _ = await model.startSharing(audience: audience) }
            }
            .task { await model.loadGroups() }
        }
        .sheet(isPresented: $showPickup) {
            PickupSpotView(initial: model.pickup) { try await model.savePickup($0) }
        }
        .sheet(item: $removing, onDismiss: { if removed { dismiss() } }) { item in
            RemoveSheet(item: item) { choice in
                removed = true
                if let onRemove {
                    onRemove(item, choice)
                } else if let api = model.api {
                    Task { _ = try? await api.removeItem(id: item.id, outcome: choice.outcome, wasteReason: choice.wasteReason,
                                                          recipientId: choice.recipientId) }
                }
            } close: {
                removing = nil
            }
        }
        .accessibilityIdentifier(isSharedLayout ? AccessibilityID.ItemDetail.shared : AccessibilityID.ItemDetail.screen)
    }

    // MARK: Pieces

    private var titleRow: some View {
        HStack(spacing: Theme.Spacing.sm) {
            FoodGroupIcon(group: model.item.foodGroup, tile: Theme.Size.detailTile)
            VStack(alignment: .leading, spacing: 0) {
                Text("Name").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted).accessibilityHidden(true)
                TextField("Name", text: $model.name)
                    .font(Theme.Fonts.itemTitle).foregroundStyle(Theme.Colors.ink)
                    .submitLabel(.done)
                    .frame(minHeight: Theme.Size.minTouch)
                    .accessibilityLabel("Name")
                    .accessibilityIdentifier(AccessibilityID.ItemDetail.name)
            }
            if let badge = ExpiryBadgeModel.make(for: model.item) {
                ExpiryBadge(model: badge).accessibilityIdentifier(AccessibilityID.ItemDetail.badge)
            }
        }
        .padding(.top, Theme.Spacing.s)
    }

    @ViewBuilder private var actions: some View {
        if isSharedLayout, let claimer = model.claimer {
            VStack(spacing: Theme.Spacing.tileGap) {
                Button { removing = model.item } label: {
                    Label("Given to \(claimer.name.split(separator: " ").first.map(String.init) ?? claimer.name)",
                          systemImage: "checkmark")
                        .font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Given to \(claimer.name): removes \(model.item.name) as donated")
                .accessibilityIdentifier(AccessibilityID.ItemDetail.sharedGivenTo)
                HStack(spacing: Theme.Spacing.tileGap) {
                    secondaryAction("Remove", id: AccessibilityID.ItemDetail.sharedRemove) { removing = model.item }
                        .accessibilityLabel("Remove: choose what happened")
                    secondaryAction("Stop sharing", id: AccessibilityID.ItemDetail.sharedStop) {
                        Task { await model.stopSharing() }
                    }
                    .disabled(model.isSharing)
                }
            }
            .padding(.top, Theme.Spacing.s)
        } else {
            Button { removing = model.item } label: {
                Text("Remove from \(model.storage.displayName.lowercased())")
                    .font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.top, Theme.Spacing.s)
            .accessibilityIdentifier(AccessibilityID.ItemDetail.remove)
        }
    }

    private func secondaryAction(_ title: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.forest)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton - Theme.Spacing.xs)
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous)
                    .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    @ViewBuilder private var footer: some View {
        if let added = model.item.addedAt {
            Text("Added \(added.formatted(.dateTime.month(.abbreviated).day()))\(model.item.source == "photo" ? " from a fridge photo" : "")")
                .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                .frame(maxWidth: .infinity)
        }
    }

    // MARK: Share switch

    private func handleSwitch(_ on: Bool) {
        if on {
            Task { await model.loadGroups() }
            showAudience = true
        } else {
            Task { await model.stopSharing() }
        }
    }
}
