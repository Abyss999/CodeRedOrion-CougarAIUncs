import SwiftUI
import MapKit

/// Non-interactive Apple Maps preview with a pin (ItemShared thumbnail 72 pt, editor preview 140 pt).
/// Hidden from VoiceOver as a map; callers describe the spot in text next to it.
struct PickupMapPreview: View {
    let pickup: Pickup
    var width: CGFloat?
    var height: CGFloat

    var body: some View {
        if let lat = pickup.lat, let lng = pickup.lng {
            let coordinate = CLLocationCoordinate2D(latitude: lat, longitude: lng)
            Map(initialPosition: .region(MKCoordinateRegion(center: coordinate,
                                                            latitudinalMeters: 400, longitudinalMeters: 400)),
                interactionModes: []) {
                Marker(pickup.title, coordinate: coordinate).tint(Theme.Colors.forest)
            }
            .mapControlVisibility(.hidden)
            .frame(width: width, height: height)
            .allowsHitTesting(false)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Map preview: pin at \(pickup.title)")
        }
    }
}

enum PickupMaps {
    /// Opens the pin in Apple Maps.
    static func open(_ pickup: Pickup) {
        guard let lat = pickup.lat, let lng = pickup.lng else { return }
        let location = CLLocation(latitude: lat, longitude: lng)
        let item: MKMapItem
        if #available(iOS 26.0, *) {
            item = MKMapItem(location: location, address: nil)
        } else {
            item = MKMapItem(placemark: MKPlacemark(coordinate: location.coordinate))
        }
        item.name = pickup.title
        item.openInMaps()
    }
}
