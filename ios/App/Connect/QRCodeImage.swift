import SwiftUI
import CoreImage
import CoreImage.CIFilterBuiltins

/// Renders text as a QR code (CIQRCodeGenerator), always ink-on-lime so a scanner sees dark on light,
/// even in dark mode. Colours are the fixed `qrInk` / `qrGround` tokens.
struct QRCodeImage: View {
    let text: String
    let size: CGFloat
    var label = "QR code"

    var body: some View {
        Group {
            if let image = Self.render(text) {
                Image(uiImage: image)
                    .interpolation(.none)
                    .resizable()
                    .scaledToFit()
            } else {
                Image(systemName: "qrcode").resizable().scaledToFit().foregroundStyle(Theme.Colors.qrInk)
            }
        }
        .padding(Theme.Spacing.sm)
        .frame(width: size, height: size)
        .background(Theme.Colors.qrGround, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
    }

    private static let context = CIContext()

    static func render(_ text: String) -> UIImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage else { return nil }
        let colored = output.applyingFilter("CIFalseColor", parameters: [
            "inputColor0": CIColor(color: UIColor(hex: 0x13261A)),
            "inputColor1": CIColor(color: UIColor(hex: 0xD9EC8F)),
        ])
        // Scale up by whole pixels so modules stay crisp.
        let scaled = colored.transformed(by: CGAffineTransform(scaleX: 10, y: 10))
        guard let cg = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: cg)
    }
}
