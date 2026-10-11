import SwiftUI
import UIKit
import AVFoundation

/// Camera access, read without prompting. `.notDetermined` is allowed: the system asks on first use.
enum CameraAccess {
    static func isDenied(launch: LaunchConfiguration) -> Bool {
        if launch.cameraDenied { return true }
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .denied, .restricted: return true
        default: return false
        }
    }
    static var hasCamera: Bool { UIImagePickerController.isSourceTypeAvailable(.camera) }
}

/// Resizes and re-encodes a photo for upload: upright pixels (so the server's box frame matches), long side
/// at most 2048 px, JPEG.
enum PhotoPrep {
    struct Prepared {
        let data: Data
        /// Pixel size of the encoded image (the frame `bbox` is in when the server sends pixels).
        let pixelSize: CGSize
    }

    static func prepare(_ image: UIImage, maxSide: CGFloat = 2048, quality: CGFloat = 0.8) -> Prepared? {
        let pixelW = image.size.width * image.scale, pixelH = image.size.height * image.scale
        guard pixelW > 0, pixelH > 0 else { return nil }
        let ratio = min(1, maxSide / max(pixelW, pixelH))
        let size = CGSize(width: (pixelW * ratio).rounded(), height: (pixelH * ratio).rounded())
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        format.opaque = true
        let upright = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        guard let data = upright.jpegData(compressionQuality: quality) else { return nil }
        return Prepared(data: data, pixelSize: size)
    }
}

/// Stand-in photo for the Simulator (no camera) and UI tests (`-UITestMockAPI`).
enum MockPhoto {
    static func image() -> UIImage {
        let size = CGSize(width: 900, height: 700)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            UIColor(hex: 0xE3EDCB).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            let blocks: [(CGRect, UInt32)] = [
                (CGRect(x: 90, y: 90, width: 270, height: 210), 0x8FD69A), (CGRect(x: 450, y: 90, width: 360, height: 210), 0xE8C46A),
                (CGRect(x: 90, y: 360, width: 270, height: 240), 0xF59AC6), (CGRect(x: 450, y: 360, width: 360, height: 240), 0x9DB7F0),
            ]
            for (rect, hex) in blocks {
                UIColor(hex: hex).setFill()
                UIBezierPath(roundedRect: rect, cornerRadius: 28).fill()
            }
        }
    }
}

/// System camera. Only used on a device (the Simulator has none).
struct CameraPicker: UIViewControllerRepresentable {
    var onImage: (UIImage) -> Void
    var onCancel: () -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker
        init(_ parent: CameraPicker) { self.parent = parent }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage { parent.onImage(image) } else { parent.onCancel() }
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.onCancel() }
    }
}
