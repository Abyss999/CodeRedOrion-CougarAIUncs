import Foundation

/// Google Sign-In configuration, read from Info.plist (`GIDClientID`, filled from `GOOGLE_IOS_CLIENT_ID`
/// in the gitignored `Local.xcconfig`). With no client id the Google button is hidden, so a fresh
/// clone builds and runs without one.
enum GoogleSignInConfig {
    /// The iOS OAuth client id, or nil when unset or still an unexpanded `$(...)` placeholder.
    static func clientID(infoValue: Any? = Bundle.main.object(forInfoDictionaryKey: "GIDClientID")) -> String? {
        guard let raw = (infoValue as? String)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty, !raw.hasPrefix("$(") else { return nil }
        return raw
    }

    static func isEnabled(infoValue: Any? = Bundle.main.object(forInfoDictionaryKey: "GIDClientID")) -> Bool {
        clientID(infoValue: infoValue) != nil
    }

    /// False when `GOOGLE_IOS_CLIENT_ID` is empty. Screens show the Google button only when true.
    static var googleSignInEnabled: Bool { isEnabled() }
}

import GoogleSignIn

extension GoogleSignInConfig {
    /// Hands the OAuth redirect URL to the SDK. Call from `.onOpenURL`. No-op while Google is disabled.
    @discardableResult
    static func handleOpenURL(_ url: URL) -> Bool {
        guard googleSignInEnabled else { return false }
        return GIDSignIn.sharedInstance.handle(url)
    }

    /// Sets the SDK's client id once at launch. No-op while Google is disabled.
    static func configure() {
        guard let id = clientID() else { return }
        GIDSignIn.sharedInstance.configuration = GIDConfiguration(clientID: id)
    }
}
