import Foundation

/// Canned inputs for the Add text / barcode / receipt paths on a mock launch (the Simulator has no microphone,
/// barcode scanner or document camera). The lookups themselves are `MockAPIClient.parseText`, `.barcode` and
/// `.fromReceipt`.
enum MockAddText {
    /// What "Say it" hears on a mock launch.
    static let sampleTranscript = "2 lb chicken thighs, a bag of spinach, a dozen eggs and some oat milk"

    /// Barcodes the mock knows (`MockData.barcode`), offered as chips on the DEBUG manual-code field.
    static let knownCodes: [(code: String, label: String)] = [
        ("016000275287", "Cheerios"),
        ("070470003795", "Chobani yogurt"),
        ("000000000000", "Unknown product"),
    ]
}
