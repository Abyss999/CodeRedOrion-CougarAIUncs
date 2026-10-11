import SwiftUI

/// Inline error banner (`fridge.remove.error`) for a rolled-back remove or undo, or a failed
/// refresh. A thin wrapper over the shared `BannerView`.
struct FridgeBannerView: View {
    let banner: FridgeBanner
    let dismiss: () -> Void

    var body: some View {
        BannerView(
            style: .error, message: banner.message,
            retry: banner.retry.map { retry in { retry() } },
            dismiss: dismiss,
            identifiers: BannerIdentifiers(container: AccessibilityID.Fridge.removeError,
                                           retry: AccessibilityID.Fridge.removeErrorRetry,
                                           dismiss: AccessibilityID.Fridge.removeErrorDismiss))
    }
}
