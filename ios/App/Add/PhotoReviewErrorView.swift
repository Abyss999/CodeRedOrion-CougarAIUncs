import SwiftUI

/// PhotoReviewError: no food found, or the analysis failed (502 / offline). Retry, retake, or type instead.
struct PhotoReviewErrorView: View {
    enum Kind: Equatable {
        case noFood
        case failed(String)
    }

    let kind: Kind
    let photo: UIImage?
    let onBack: () -> Void
    let onRetry: () -> Void
    let onRetake: () -> Void
    let onType: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: Theme.Spacing.sheetSection + 4) {
                HStack {
                    BackButton(action: onBack, id: AccessibilityID.PhotoReview.back)
                    Spacer()
                }
                PhotoBlock(photo: photo, height: Theme.AddFlow.errorPhotoHeight)
                if kind == .noFood {
                    VStack(spacing: Theme.Spacing.s) {
                        Image(systemName: "magnifyingglass")
                            .font(.title2)
                            .foregroundStyle(Theme.Colors.forest)
                            .frame(width: Theme.AddFlow.statusDisc, height: Theme.AddFlow.statusDisc)
                            .background(Theme.Colors.limeTint, in: Circle())
                            .accessibilityHidden(true)
                        Text("We couldn't spot any food")
                            .font(Theme.Fonts.sheetTitle)
                            .foregroundStyle(Theme.Colors.ink)
                            .multilineTextAlignment(.center)
                            .accessibilityAddTraits(.isHeader)
                        if kind == .noFood {
                            Text("Try a closer, brighter photo, or type what you have.")
                                .font(Theme.Fonts.body).foregroundStyle(Theme.Colors.muted)
                                .multilineTextAlignment(.center)
                        }
                    }
                    .accessibilityElement(children: .combine)
                    .accessibilityIdentifier(AccessibilityID.PhotoReview.none)
                }
                if case .failed(let message) = kind {
                    BannerView(style: .error, message: message, retryTitle: "Try again", retry: onRetry,
                               identifiers: BannerIdentifiers(container: AccessibilityID.PhotoReview.failed, retry: AccessibilityID.PhotoReview.failedRetry),
                               horizontalInset: 0)
                }
                VStack(spacing: Theme.Spacing.tileGap) {
                    wideButton("Retake photo", prominent: true, id: AccessibilityID.PhotoReview.retake, action: onRetake)
                    wideButton("Type it instead", prominent: false, id: AccessibilityID.PhotoReview.typeInstead, action: onType)
                }
            }
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.m).padding(.bottom, Theme.Spacing.xl)
        }
        .scrollBounceBehavior(.basedOnSize)
    }

    private func wideButton(_ title: String, prominent: Bool, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(Theme.Fonts.button)
                .foregroundStyle(prominent ? Theme.Colors.onForest : Theme.Colors.forest)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                .background(prominent ? Theme.Colors.forest : Theme.Colors.surface,
                            in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                .overlay {
                    if !prominent {
                        RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous).strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline)
                    }
                }
                .contentShape(Rectangle())
        }
        .accessibilityIdentifier(id)
    }
}

/// The round back button used on the photo screens.
struct BackButton: View {
    let action: () -> Void
    let id: String

    var body: some View {
        Button(action: action) {
            Image(systemName: "chevron.left")
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.forest)
                .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                .background(Theme.Colors.surface, in: Circle())
                .overlay { Circle().strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                .contentShape(Circle())
        }
        .accessibilityLabel("Back")
        .accessibilityIdentifier(id)
    }
}
