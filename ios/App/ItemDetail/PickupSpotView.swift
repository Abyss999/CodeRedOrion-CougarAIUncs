import SwiftUI

/// Pickup spot editor (`PickupSpot` artboard): an optional note (120 max) and/or an Apple Maps pin,
/// plus spots saved on this device. `save` stores the result (a PATCH on an open listing, or held
/// until the item is shared); `nil` removes the spot. The sheet closes only after `save` succeeds.
struct PickupSpotView: View {
    let initial: Pickup?
    let save: (Pickup?) async throws -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var note: String
    @State private var pin: PickupPin?
    @State private var showPicker = false
    @State private var saving = false
    @State private var errorMessage: String?
    @State private var askName = false
    @State private var spotName = ""
    @State private var store = SavedPickupSpotsStore.shared

    init(initial: Pickup?, save: @escaping (Pickup?) async throws -> Void) {
        self.initial = initial
        self.save = save
        _note = State(initialValue: initial?.note ?? "")
        if let lat = initial?.lat, let lng = initial?.lng {
            _pin = State(initialValue: PickupPin(lat: lat, lng: lng, name: initial?.placeName))
        }
    }

    /// What the form holds right now; nil when it is empty.
    private var draft: Pickup? {
        let trimmed = note.trimmingCharacters(in: .whitespacesAndNewlines)
        let p = Pickup(note: trimmed.isEmpty ? nil : trimmed, lat: pin?.lat, lng: pin?.lng, placeName: pin?.name)
        return p.isValid ? p : nil
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                    if let errorMessage {
                        BannerView(style: .error, message: errorMessage, dismiss: { self.errorMessage = nil },
                                   identifiers: BannerIdentifiers(container: AccessibilityID.PickupSpot.error),
                                   horizontalInset: 0)
                    }
                    noteField
                    pinCard
                    savedSection
                    if initial != nil {
                        Button { commit(nil) } label: {
                            Text("Remove pickup spot")
                                .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.urgentInk)
                                .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(saving)
                        .accessibilityIdentifier(AccessibilityID.PickupSpot.remove)
                    }
                }
                .padding(.horizontal, Theme.Spacing.gutter)
                .padding(.vertical, Theme.Spacing.m)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(Theme.Colors.ground.ignoresSafeArea())
            .navigationTitle("Pickup spot")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.accessibilityIdentifier(AccessibilityID.PickupSpot.cancel)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { commit(draft) }
                        .fontWeight(.bold)
                        .disabled(saving || (draft == nil && initial == nil))
                        .accessibilityIdentifier(AccessibilityID.PickupSpot.done)
                }
            }
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .presentationCornerRadius(Theme.Radius.sheet)
        .presentationBackground(Theme.Colors.ground)
        .interactiveDismissDisabled(saving)
        .sheet(isPresented: $showPicker) {
            PinPickerView(initial: pin) { picked in pin = picked }
        }
        .alert("Name this spot", isPresented: $askName) {
            TextField("Home, Lab…", text: $spotName)
            Button("Save") { if let draft { store.add(name: spotName, pickup: draft) } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("It stays on this phone, so you can reuse it next time.")
        }
        .accessibilityIdentifier(AccessibilityID.PickupSpot.screen)
    }

    // MARK: Note

    private var noteField: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.stack) {
            Text("Note").font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.inkSecondary).accessibilityHidden(true)
            TextField("Where should they look?", text: $note, axis: .vertical)
                .lineLimit(2...5)
                .font(Theme.Fonts.body)
                .foregroundStyle(Theme.Colors.ink)
                .padding(.horizontal, Theme.Spacing.sm).padding(.vertical, Theme.Spacing.sm)
                .frame(minHeight: Theme.Size.minTouch, alignment: .topLeading)
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                    .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                .onChange(of: note) { _, new in
                    if new.count > Pickup.noteLimit { note = String(new.prefix(Pickup.noteLimit)) }
                }
                .accessibilityLabel("Note")
                .accessibilityIdentifier(AccessibilityID.PickupSpot.note)
            Text("\(note.count)/\(Pickup.noteLimit)")
                .font(Theme.Fonts.meta.monospacedDigit()).foregroundStyle(Theme.Colors.muted)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .accessibilityLabel("\(note.count) of \(Pickup.noteLimit) characters")
                .accessibilityIdentifier(AccessibilityID.PickupSpot.noteCount)
        }
    }

    // MARK: Pin

    private var pinCard: some View {
        VStack(spacing: 0) {
            if let pin {
                PickupMapPreview(pickup: Pickup(lat: pin.lat, lng: pin.lng, placeName: pin.name),
                                 width: nil, height: Theme.Size.pickupPreview)
                    .frame(maxWidth: .infinity)
                HStack(spacing: Theme.Spacing.sm) {
                    Image(systemName: "mappin.and.ellipse").foregroundStyle(Theme.Colors.forest).accessibilityHidden(true)
                    Text(pin.name ?? "Dropped pin")
                        .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier(AccessibilityID.PickupSpot.pinName)
                    Button("Move pin") { showPicker = true }
                        .font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.forest)
                        .frame(minHeight: Theme.Size.minTouch)
                        .accessibilityIdentifier(AccessibilityID.PickupSpot.movePin)
                    Button { self.pin = nil } label: {
                        Image(systemName: "xmark").font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.muted)
                            .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch).contentShape(Rectangle())
                    }
                    .accessibilityLabel("Remove pin")
                }
                .padding(.leading, Theme.Spacing.m)
                .padding(.trailing, Theme.Spacing.xs)
            } else {
                Button { showPicker = true } label: {
                    HStack(spacing: Theme.Spacing.sm) {
                        Image(systemName: "mappin.and.ellipse").accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                            Text("Add a map pin").font(Theme.Fonts.rowTitle)
                            Text("Search, drop a pin, or use your location")
                                .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Image(systemName: "chevron.right").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(Theme.Colors.forest)
                    .padding(.horizontal, Theme.Spacing.m)
                    .frame(minHeight: Theme.Size.minTouch + Theme.Spacing.s)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(AccessibilityID.PickupSpot.addPin)
            }
        }
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
    }

    // MARK: Saved spots

    private var savedSection: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.s) {
            if !store.spots.isEmpty {
                GroupHeaderText(text: "Use a saved spot")
                VStack(spacing: 0) {
                    ForEach(store.spots) { spot in
                        HStack(spacing: 0) {
                            Button { apply(spot) } label: {
                                HStack(spacing: Theme.Spacing.sm) {
                                    Image(systemName: spot.systemImage)
                                        .foregroundStyle(Theme.Colors.forest)
                                        .frame(width: Theme.Size.savedSpotIcon, height: Theme.Size.savedSpotIcon)
                                        .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous))
                                        .accessibilityHidden(true)
                                    VStack(alignment: .leading, spacing: 0) {
                                        Text(spot.name).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                                        Text(spot.detail).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted).lineLimit(1)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                }
                                .padding(.leading, Theme.Spacing.sm)
                                .frame(minHeight: Theme.Size.savedSpotRow)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityElement(children: .combine)
                            .accessibilityHint("Fills the note and pin from this saved spot")
                            .accessibilityIdentifier(AccessibilityID.PickupSpot.saved(spot.id))
                            Button { store.remove(id: spot.id) } label: {
                                Image(systemName: "trash").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                                    .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch).contentShape(Rectangle())
                            }
                            .accessibilityLabel("Delete saved spot \(spot.name)")
                            .accessibilityIdentifier(AccessibilityID.PickupSpot.savedDelete(spot.id))
                        }
                        if spot.id != store.spots.last?.id { Divider().overlay(Theme.Colors.hairline) }
                    }
                }
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            }
            Button {
                spotName = ""
                askName = true
            } label: {
                Label("Save this spot", systemImage: "bookmark")
                    .font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.forest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch, alignment: .leading)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                    .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                        .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(draft == nil)
            .opacity(draft == nil ? 0.5 : 1)
            .accessibilityHint("Keeps this spot on this phone to reuse later")
            .accessibilityIdentifier(AccessibilityID.PickupSpot.saveSpot)
        }
    }

    // MARK: Actions

    private func apply(_ spot: SavedPickupSpot) {
        note = spot.pickup.note ?? ""
        if let lat = spot.pickup.lat, let lng = spot.pickup.lng {
            pin = PickupPin(lat: lat, lng: lng, name: spot.pickup.placeName)
        } else {
            pin = nil
        }
        Haptics.selection()
    }

    private func commit(_ pickup: Pickup?) {
        guard !saving else { return }
        saving = true
        errorMessage = nil
        Task {
            do {
                try await save(pickup)
                saving = false
                dismiss()
            } catch {
                saving = false
                errorMessage = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            }
        }
    }
}
