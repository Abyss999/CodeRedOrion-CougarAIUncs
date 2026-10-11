import SwiftUI
import MapKit

/// `ClaimedItem`: the listing you claimed and where to pick it up. `pickup` is optional (the sharer may not
/// have set one yet, and older servers don't send it).
struct ClaimedItemView: View {
    let listing: PantryListing

    private var pickup: PickupSpot? {
        guard let p = listing.pickup else { return nil }
        let hasNote = !(p.note ?? "").isEmpty, hasPlace = !(p.placeName ?? "").isEmpty
        return hasNote || hasPlace || coordinate(p) != nil ? p : nil
    }

    private func coordinate(_ p: PickupSpot) -> CLLocationCoordinate2D? {
        guard let lat = p.lat, let lng = p.lng else { return nil }
        let c = CLLocationCoordinate2D(latitude: lat, longitude: lng)
        return CLLocationCoordinate2DIsValid(c) ? c : nil
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                HStack(spacing: Theme.Spacing.sm) {
                    FoodGroupIcon(group: listing.item.category.foodGroup, tile: Theme.Size.sheetHeaderTile)
                    VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                        Text(listing.item.name).font(Theme.Fonts.sheetTitle).foregroundStyle(Theme.Colors.ink)
                            .accessibilityAddTraits(.isHeader)
                        HStack(spacing: Theme.Spacing.xs) {
                            Text("From \(listing.ownerName)").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                            if let badge = ExpiryBadgeModel.make(expiry: listing.item.predictedExpiry, freshness: nil) {
                                ExpiryBadge(model: badge)
                            }
                        }
                    }
                }
                .accessibilityElement(children: .combine)
                Label("You claimed this", systemImage: "checkmark.circle.fill")
                    .font(Theme.Fonts.badge).foregroundStyle(Theme.Colors.forest)
                    .padding(.horizontal, Theme.Spacing.sm).padding(.vertical, Theme.Spacing.s)
                    .background(Theme.Colors.limeTint, in: Capsule())
                Text("Pickup spot").font(Theme.Fonts.cardHeading).foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                pickupCard
            }
            .padding(Theme.Spacing.gutter)
        }
        .background(Theme.Colors.ground.ignoresSafeArea())
        .navigationTitle("Claimed item")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier(AccessibilityID.ClaimedItem.screen)
    }

    @ViewBuilder private var pickupCard: some View {
        if let p = pickup {
            VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    if let place = p.placeName, !place.isEmpty {
                        Text(place).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    }
                    if let note = p.note, !note.isEmpty {
                        Text(note).font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.inkSecondary)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier(AccessibilityID.ClaimedItem.pickup)
                if let c = coordinate(p) {
                    Map(initialPosition: .region(MKCoordinateRegion(center: c, latitudinalMeters: 400, longitudinalMeters: 400)),
                        interactionModes: []) {
                        Marker(p.placeName ?? "Pickup spot", coordinate: c).tint(Theme.Colors.forest)
                    }
                    .frame(height: Theme.Size.mapPreview)
                    .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                    .accessibilityLabel("Map preview of the pickup spot")
                    .accessibilityIdentifier(AccessibilityID.ClaimedItem.map)
                    Button { open(p, c) } label: {
                        Label("Open in Maps", systemImage: "map")
                            .font(Theme.Fonts.button).foregroundStyle(Theme.Colors.onForest)
                            .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                            .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
                            .contentShape(Rectangle())
                    }
                    .accessibilityIdentifier(AccessibilityID.ClaimedItem.openMaps)
                }
            }
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        } else {
            VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                Label("No pickup spot yet", systemImage: "mappin.slash")
                    .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                Text("\(SocialText.firstName(listing.ownerName)) hasn't added one. Message them to sort out the handoff.")
                    .font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted)
            }
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(AccessibilityID.ClaimedItem.pickup)
        }
    }

    private func open(_ p: PickupSpot, _ c: CLLocationCoordinate2D) {
        let item = MKMapItem(placemark: MKPlacemark(coordinate: c))
        item.name = p.placeName ?? "Pickup spot"
        item.openInMaps()
    }
}
