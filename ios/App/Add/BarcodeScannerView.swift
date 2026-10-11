import SwiftUI
import VisionKit

/// Live barcode scanning with `DataScannerViewController`. Only create it when `isUsable` is true.
struct BarcodeScannerView: UIViewControllerRepresentable {
    var onCode: (String) -> Void

    /// False on the Simulator and on devices without the scanner (or with camera access off).
    static var isUsable: Bool { DataScannerViewController.isSupported && DataScannerViewController.isAvailable }

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let vc = DataScannerViewController(recognizedDataTypes: [.barcode()], qualityLevel: .balanced,
                                           recognizesMultipleItems: false, isHighFrameRateTrackingEnabled: false,
                                           isPinchToZoomEnabled: true, isGuidanceEnabled: true, isHighlightingEnabled: true)
        vc.delegate = context.coordinator
        DispatchQueue.main.async { try? vc.startScanning() }
        return vc
    }

    func updateUIViewController(_ uiViewController: DataScannerViewController, context: Context) {
        context.coordinator.onCode = onCode
    }

    static func dismantleUIViewController(_ uiViewController: DataScannerViewController, coordinator: Coordinator) {
        uiViewController.stopScanning()
    }

    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        var onCode: (String) -> Void
        private var fired = false
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            for item in addedItems {
                if case .barcode(let code) = item, let value = code.payloadStringValue, Self.isLookupCode(value) { fire(value, dataScanner); return }
            }
        }

        func dataScanner(_ dataScanner: DataScannerViewController, didTapOn item: RecognizedItem) {
            if case .barcode(let code) = item, let value = code.payloadStringValue, Self.isLookupCode(value) { fire(value, dataScanner) }
        }

        private func fire(_ value: String, _ scanner: DataScannerViewController) {
            guard !fired else { return }
            fired = true
            scanner.stopScanning()
            onCode(value)
        }

        /// The API takes 6-14 digit codes.
        static func isLookupCode(_ s: String) -> Bool { (6...14).contains(s.count) && s.allSatisfy(\.isNumber) }
    }
}
