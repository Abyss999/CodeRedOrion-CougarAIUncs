import SwiftUI

/// Routes the Add sheet's "other ways" (Type it, Say it, Barcode, Receipt) to their screens.
struct AddDestinationView: View {
    let destination: AddDestination
    /// Back to the Add menu.
    let onBack: () -> Void
    /// Switch to another destination ("Type it instead").
    let onOpen: (AddDestination) -> Void
    /// Items were added: close the sheet.
    let onFinished: () -> Void

    var body: some View {
        switch destination {
        case .text, .say:
            AddTextView(startMode: destination.textMode ?? .typing, onBack: onBack, onFinished: onFinished)
                .id(destination)
        case .barcode:
            BarcodeView(onBack: onBack, onType: { onOpen(.text) }, onFinished: onFinished)
        case .receipt:
            ReceiptView(onBack: onBack, onType: { onOpen(.text) }, onFinished: onFinished)
        }
    }
}
