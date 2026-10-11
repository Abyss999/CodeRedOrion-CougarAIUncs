import Foundation

/// Pickup-spot calls (docs/API.md "Share / Food Pantry", branch feat/friend-qr-pickup).
extension LiveAPIClient {
    private struct PickupShareBody: Encodable {
        let itemId: String
        let groupId: String?
        let pickup: Pickup?
    }

    /// `{"pickup": {...}}` or `{"pickup": null}`: the key is always sent (null clears the spot).
    private struct PickupPatchBody: Encodable {
        let pickup: Pickup?
        enum CodingKeys: String, CodingKey { case pickup }
        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            if let pickup { try c.encode(pickup, forKey: .pickup) } else { try c.encodeNil(forKey: .pickup) }
        }
    }

    func share(itemId: String, audience: ShareAudience, pickup: Pickup?) async throws -> Listing {
        let r: ListingResponse = try await send("POST", "/share",
                                                body: PickupShareBody(itemId: itemId, groupId: audience.groupId, pickup: pickup))
        return r.listing
    }

    func updatePickup(listingId: String, pickup: Pickup?) async throws -> Listing {
        let r: ListingResponse = try await send("PATCH", "/share/\(Self.ids(listingId))", body: PickupPatchBody(pickup: pickup))
        return r.listing
    }
}
