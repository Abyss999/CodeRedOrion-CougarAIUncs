import SwiftUI

/// One detection box, normalised to 0...1 of the photo.
struct DetectionBox: Identifiable, Equatable {
    let id: Int
    let rect: CGRect
    let isOn: Bool

    /// `bbox` is `[x1, y1, x2, y2]`, either 0...1 or pixels of the uploaded image. Nil, malformed or empty boxes
    /// give nil: the Gemini fallback sends no boxes, and then nothing is drawn.
    static func normalized(_ bbox: [Double]?, pixelSize: CGSize) -> CGRect? {
        guard let b = bbox, b.count == 4, b.allSatisfy({ $0.isFinite && $0 >= 0 }) else { return nil }
        var (x1, y1, x2, y2) = (b[0], b[1], b[2], b[3])
        if b.max() ?? 0 > 1.0001 {
            guard pixelSize.width > 0, pixelSize.height > 0 else { return nil }
            x1 /= pixelSize.width; x2 /= pixelSize.width; y1 /= pixelSize.height; y2 /= pixelSize.height
        }
        let rect = CGRect(x: min(x1, x2), y: min(y1, y2), width: abs(x2 - x1), height: abs(y2 - y1))
            .intersection(CGRect(x: 0, y: 0, width: 1, height: 1))
        return rect.isNull || rect.width <= 0 || rect.height <= 0 ? nil : rect
    }
}

/// The photo with a box on each detected item. Boxes draw on with a stroke trim (0.4 s; Reduce Motion: a fade).
/// Unticked items get a dashed box, so the state is never colour alone.
struct PhotoBoxOverlay: View {
    let photo: UIImage
    let boxes: [DetectionBox]
    let height: CGFloat
    @MotionReduced private var reduceMotion
    @State private var drawn = false

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous).fill(Theme.Colors.track)
            GeometryReader { geo in
                let fitted = fittedRect(in: geo.size)
                ZStack(alignment: .topLeading) {
                    Image(uiImage: photo).resizable().frame(width: fitted.width, height: fitted.height)
                    ForEach(boxes) { box in
                        let r = CGRect(x: box.rect.minX * fitted.width, y: box.rect.minY * fitted.height,
                                       width: box.rect.width * fitted.width, height: box.rect.height * fitted.height)
                        RoundedRectangle(cornerRadius: Theme.Radius.bar, style: .continuous)
                            .trim(from: 0, to: reduceMotion || drawn ? 1 : 0)
                            .stroke(Theme.Colors.lime, style: StrokeStyle(lineWidth: Theme.AddFlow.boxLine, dash: box.isOn ? [] : [6, 4]))
                            .opacity(reduceMotion ? (drawn ? 1 : 0) : (box.isOn ? 1 : 0.7))
                            .frame(width: r.width, height: r.height)
                            .offset(x: r.minX, y: r.minY)
                    }
                }
                .frame(width: fitted.width, height: fitted.height)
                .position(x: geo.size.width / 2, y: geo.size.height / 2)
            }
        }
        .frame(height: height)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .onAppear { withAnimation(Theme.AddFlow.boxDraw) { drawn = true } }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Your photo, with a box on each item found")
        .accessibilityAddTraits(.isImage)
        .accessibilityIdentifier(AccessibilityID.PhotoReview.photo)
    }

    private func fittedRect(in size: CGSize) -> CGSize {
        let aspect = photo.size.width / max(photo.size.height, 1)
        let w = min(size.width, size.height * aspect)
        return CGSize(width: w, height: w / max(aspect, 0.01))
    }
}
