import SwiftUI

// Tokens and accessibility ids for Item detail / ItemShared / PickupSpot. Kept in this folder as
// extensions so the shared Theme.swift and AccessibilityID.swift stay untouched (append-only rule).
// The orchestrator folds these into DESIGN_SYSTEM.md.

extension Theme.Fonts {
    /// Item name field (ItemDetail artboard: Outfit 26 / 600).
    static let itemTitle = Theme.Fonts.display(26, relativeTo: .title)
}

extension Theme.Size {
    /// Row height in the item field card (artboard: 46).
    static let detailRow: CGFloat = 46
    /// Food-group tile beside the name (artboard: 56).
    static let detailTile: CGFloat = 56
    /// Share switch hit area (round 4: a 44 pt control; the switch itself is 51 wide).
    static let shareSwitchWidth: CGFloat = 51
    /// Map thumbnail on ItemShared (artboard: 72) and the preview in the PickupSpot editor (140).
    static let pickupThumb: CGFloat = 72
    static let pickupPreview: CGFloat = 140
    /// Saved-spot icon tile (artboard: 32).
    static let savedSpotIcon: CGFloat = 32
    /// Saved-spot row minimum height (artboard: 56).
    static let savedSpotRow: CGFloat = 56
}

extension AccessibilityID.ItemDetail {
    static let name = "itemdetail.name"
    static let badge = "itemdetail.badge"
    static let save = "itemdetail.save"
    static let quantity = "itemdetail.quantity"
    static let unit = "itemdetail.unit"
    static let foodGroup = "itemdetail.foodgroup"
    static let storage = "itemdetail.storage"
    static let expiry = "itemdetail.expiry"
    static let freshness = "itemdetail.freshness"
    static let checkAgain = "itemdetail.checkagain"
    static let lookFor = "itemdetail.lookfor"
    static let shareSwitch = "itemdetail.share.switch"
    static let shareStatus = "itemdetail.share.status"
    static let pickupRow = "itemdetail.pickup.row"
    static let remove = "itemdetail.remove"
    static let banner = "itemdetail.banner"
    static let audienceSheet = "itemdetail.audience.sheet"
    static let audienceFriends = "itemdetail.audience.friends"
    static func audienceGroup(_ id: String) -> String { "itemdetail.audience.group.\(id)" }
    static let audienceConfirm = "itemdetail.audience.confirm"
    static let audienceCancel = "itemdetail.audience.cancel"

    // ItemShared (an open listing someone claimed)
    static let shared = "itemshared"
    static let sharedAudience = "itemshared.audience"
    static let sharedClaimer = "itemshared.claimer"
    static let sharedPickup = "itemshared.pickup"
    static let sharedPickupEdit = "itemshared.pickup.edit"
    static let sharedOpenInMaps = "itemshared.openinmaps"
    static let sharedGivenTo = "itemshared.givento"
    static let sharedRemove = "itemshared.remove"
    static let sharedStop = "itemshared.stop"
}

extension AccessibilityID {
    enum PickupSpot {
        static let screen = "pickupspot"
        static let note = "pickupspot.note"
        static let noteCount = "pickupspot.note.count"
        static let cancel = "pickupspot.cancel"
        static let done = "pickupspot.done"
        static let addPin = "pickupspot.pin.add"
        static let movePin = "pickupspot.pin.move"
        static let pinName = "pickupspot.pin.name"
        static func saved(_ id: String) -> String { "pickupspot.saved.\(id)" }
        static func savedDelete(_ id: String) -> String { "pickupspot.saved.\(id).delete" }
        static let saveSpot = "pickupspot.save"
        static let saveName = "pickupspot.save.name"
        static let remove = "pickupspot.remove"
        static let error = "pickupspot.error"
        // Pin picker
        static let pinPicker = "pickupspot.picker"
        static let search = "pickupspot.picker.search"
        static func result(_ index: Int) -> String { "pickupspot.picker.result.\(index)" }
        static let useLocation = "pickupspot.picker.location"
        static let dropPin = "pickupspot.picker.drop"
        static let pinDone = "pickupspot.picker.done"
        static let pinCancel = "pickupspot.picker.cancel"
        static let locationMessage = "pickupspot.picker.location.message"
    }
}
