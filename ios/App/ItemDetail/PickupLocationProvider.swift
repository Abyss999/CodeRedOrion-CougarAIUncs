import CoreLocation
import Observation

/// One-shot "use my location" with When-In-Use permission (`NSLocationWhenInUseUsageDescription`).
@MainActor
@Observable
final class PickupLocationProvider: NSObject, CLLocationManagerDelegate {
    var coordinate: CLLocationCoordinate2D?
    var isLocating = false
    /// Shown under the button when permission is denied or the fix fails.
    var message: String?

    @ObservationIgnored private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    func request() {
        message = nil
        switch manager.authorizationStatus {
        case .notDetermined:
            isLocating = true
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            isLocating = true
            manager.requestLocation()
        default:
            message = "Location is off for BiteDown. Turn it on in Settings, or search for the place instead."
        }
    }

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        Task { @MainActor in
            switch status {
            case .authorizedWhenInUse, .authorizedAlways:
                if self.isLocating { manager.requestLocation() }
            case .denied, .restricted:
                if self.isLocating {
                    self.isLocating = false
                    self.message = "Location is off for BiteDown. Turn it on in Settings, or search for the place instead."
                }
            default: break
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let last = locations.last else { return }
        let c = last.coordinate
        Task { @MainActor in
            self.coordinate = c
            self.isLocating = false
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            self.isLocating = false
            self.message = "Couldn't find your location. Search for the place instead."
        }
    }
}
