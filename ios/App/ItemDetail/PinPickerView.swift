import SwiftUI
import MapKit

/// What the pin picker returns.
struct PickupPin: Hashable, Sendable {
    var lat: Double
    var lng: Double
    var name: String?
}

/// Full-screen map to choose a pin: search for a place, tap the map, drop a pin at the map centre
/// (the VoiceOver-friendly route), or use your location. Nothing is saved until "Use this pin".
struct PinPickerView: View {
    let initial: PickupPin?
    let onPick: (PickupPin) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var position: MapCameraPosition
    @State private var pin: PickupPin?
    @State private var center: CLLocationCoordinate2D?
    @State private var query = ""
    @State private var results: [MKMapItem] = []
    @State private var searching = false
    @State private var searchMessage: String?
    @State private var location = PickupLocationProvider()
    @FocusState private var searchFocused: Bool

    init(initial: PickupPin?, onPick: @escaping (PickupPin) -> Void) {
        self.initial = initial
        self.onPick = onPick
        _pin = State(initialValue: initial)
        if let initial {
            _position = State(initialValue: .region(MKCoordinateRegion(
                center: CLLocationCoordinate2D(latitude: initial.lat, longitude: initial.lng),
                latitudinalMeters: 600, longitudinalMeters: 600)))
        } else {
            _position = State(initialValue: .userLocation(fallback: .automatic))
        }
    }

    var body: some View {
        NavigationStack {
            MapReader { proxy in
                Map(position: $position) {
                    if let pin {
                        Marker(pin.name ?? "Pickup spot", coordinate: CLLocationCoordinate2D(latitude: pin.lat, longitude: pin.lng))
                            .tint(Theme.Colors.forest)
                    }
                }
                .onMapCameraChange(frequency: .onEnd) { ctx in center = ctx.region.center }
                .onTapGesture { point in
                    if let c = proxy.convert(point, from: .local) { drop(c, name: nil) }
                }
            }
            .safeAreaInset(edge: .top, spacing: 0) { searchBar }
            .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar }
            .navigationTitle("Choose a pin")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .accessibilityIdentifier(AccessibilityID.PickupSpot.pinCancel)
                }
            }
            .onChange(of: location.coordinate?.latitude) { _, _ in
                if let c = location.coordinate { drop(c, name: "My location", recenter: true) }
            }
        }
        .accessibilityIdentifier(AccessibilityID.PickupSpot.pinPicker)
    }

    // MARK: Pieces

    private var searchBar: some View {
        VStack(spacing: Theme.Spacing.s) {
            HStack(spacing: Theme.Spacing.s) {
                Image(systemName: "magnifyingglass").foregroundStyle(Theme.Colors.muted).accessibilityHidden(true)
                TextField("Search for a place", text: $query)
                    .focused($searchFocused)
                    .submitLabel(.search)
                    .onSubmit { Task { await search() } }
                    .font(Theme.Fonts.body)
                    .foregroundStyle(Theme.Colors.ink)
                    .accessibilityIdentifier(AccessibilityID.PickupSpot.search)
                if searching { ProgressView() }
                else if !query.isEmpty {
                    Button { query = ""; results = []; searchMessage = nil } label: {
                        Image(systemName: "xmark.circle.fill").foregroundStyle(Theme.Colors.muted)
                            .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch).contentShape(Rectangle())
                    }
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(.leading, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.minTouch)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
            .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }

            if let searchMessage {
                Text(searchMessage).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            if !results.isEmpty {
                VStack(spacing: 0) {
                    ForEach(Array(results.prefix(5).enumerated()), id: \.offset) { index, item in
                        Button {
                            let c = item.placemark.coordinate
                            drop(c, name: item.name, recenter: true)
                            results = []
                            searchFocused = false
                        } label: {
                            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                                Text(item.name ?? "Place").font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                                if let sub = subtitle(item) {
                                    Text(sub).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted).lineLimit(1)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.horizontal, Theme.Spacing.sm)
                            .frame(minHeight: Theme.Size.minTouch)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier(AccessibilityID.PickupSpot.result(index))
                        if index < min(results.count, 5) - 1 { Divider().overlay(Theme.Colors.hairline) }
                    }
                }
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            }
        }
        .padding(.horizontal, Theme.Spacing.gutter)
        .padding(.vertical, Theme.Spacing.s)
    }

    private var bottomBar: some View {
        VStack(spacing: Theme.Spacing.s) {
            if let message = location.message {
                Text(message).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.urgentInk)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(AccessibilityID.PickupSpot.locationMessage)
            }
            if let pin {
                Label(pin.name ?? "Dropped pin", systemImage: "mappin.circle.fill")
                    .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(AccessibilityID.PickupSpot.pinName)
            } else {
                Text("Search, tap the map, or drop a pin at the centre.")
                    .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(spacing: Theme.Spacing.s) {
                secondary("Use my location", systemImage: "location", id: AccessibilityID.PickupSpot.useLocation) {
                    location.request()
                }
                .disabled(location.isLocating)
                secondary("Drop pin here", systemImage: "scope", id: AccessibilityID.PickupSpot.dropPin) {
                    if let center { drop(center, name: nil) }
                }
                .disabled(center == nil)
            }
            Button {
                if let pin { onPick(pin); dismiss() }
            } label: {
                Text("Use this pin")
                    .font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                    .background(pin == nil ? Theme.Colors.muted : Theme.Colors.forest,
                                in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(pin == nil)
            .accessibilityIdentifier(AccessibilityID.PickupSpot.pinDone)
        }
        .padding(.horizontal, Theme.Spacing.gutter)
        .padding(.vertical, Theme.Spacing.sm)
        .background(.bar)
    }

    private func secondary(_ title: String, systemImage: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: systemImage)
                .font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.forest)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                    .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(id)
    }

    // MARK: Actions

    private func drop(_ c: CLLocationCoordinate2D, name: String?, recenter: Bool = false) {
        pin = PickupPin(lat: c.latitude, lng: c.longitude, name: name)
        if recenter {
            position = .region(MKCoordinateRegion(center: c, latitudinalMeters: 600, longitudinalMeters: 600))
        }
    }

    private func subtitle(_ item: MKMapItem) -> String? {
        let p = item.placemark
        let parts = [p.thoroughfare, p.locality].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: ", ")
    }

    private func search() async {
        let text = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        searching = true
        searchMessage = nil
        defer { searching = false }
        let request = MKLocalSearch.Request()
        request.naturalLanguageQuery = text
        if let center { request.region = MKCoordinateRegion(center: center, latitudinalMeters: 20_000, longitudinalMeters: 20_000) }
        do {
            let response = try await MKLocalSearch(request: request).start()
            results = response.mapItems
            if results.isEmpty { searchMessage = "No places found. Try another name, or tap the map." }
        } catch {
            results = []
            searchMessage = "Search isn't available right now. Tap the map to drop a pin instead."
        }
    }
}
