import Foundation

/// Mock pickup-spot calls. Rules mirror docs/API.md: a spot needs a note (1-120 chars) or a lat+lng pair;
/// `PATCH` is owner only and needs an open listing.
extension MockAPIClient {
    private func validatePickup(_ p: Pickup?) throws {
        guard let p else { return }
        if let n = p.note, n.trimmingCharacters(in: .whitespacesAndNewlines).count > Pickup.noteLimit {
            throw validation("note must be 120 characters or fewer.")
        }
        if (p.lat == nil) != (p.lng == nil) { throw validation("lat and lng must be sent together.") }
        if let lat = p.lat, let lng = p.lng, abs(lat) > 90 || abs(lng) > 180 { throw validation("lat/lng out of range.") }
        guard p.isValid else { throw validation("pickup needs a note or a lat/lng pair.") }
    }

    private func normalized(_ p: Pickup?) -> Pickup? {
        guard let p else { return nil }
        let place = p.placeName?.trimmingCharacters(in: .whitespacesAndNewlines)
        return Pickup(note: p.trimmedNote, lat: p.lat, lng: p.lng, placeName: (place?.isEmpty ?? true) ? nil : place)
    }

    func share(itemId: String, audience: ShareAudience, pickup: Pickup?) async throws -> Listing {
        try validatePickup(pickup)
        var listing = try await createShare(itemId: itemId, groupId: audience.groupId)
        let spot = normalized(pickup)
        if let l = social.listings.firstIndex(where: { $0.id == listing.id }) {
            social.listings[l].pickup = spot
            social.listings[l].pickupSet = spot != nil
            listing = social.listings[l]
        }
        if let i = items.firstIndex(where: { $0.id == itemId }) {
            items[i].share?.audience = listing.audience ?? audience.listingAudience
            items[i].share?.pickup = spot
        }
        return listing
    }

    func updatePickup(listingId: String, pickup: Pickup?) async throws -> Listing {
        try await gate("updatePickup")
        try validatePickup(pickup)
        guard let l = social.listings.firstIndex(where: { $0.id == listingId }) else { throw notFound("Listing") }
        guard social.listings[l].status == .open else { throw conflict("listing_closed", "That listing is closed.") }
        let spot = normalized(pickup)
        social.listings[l].pickup = spot
        social.listings[l].pickupSet = spot != nil
        if let i = items.firstIndex(where: { $0.share?.id == listingId }) { items[i].share?.pickup = spot }
        return social.listings[l]
    }
}
