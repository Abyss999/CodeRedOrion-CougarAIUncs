import SwiftUI
import GoogleSignIn
import GoogleSignInSwift

/// What went wrong with a Google sign-in, in the words the card shows (SCREENS row 31).
struct GoogleSignInProblem: Hashable {
    let message: String
    /// The Google account's email, to prefill the email form (409 `account_exists_use_password`).
    var email: String?
    var kind: Kind

    enum Kind: Hashable { case existsWithPassword, other }

    static func from(_ error: Error, email: String?) -> GoogleSignInProblem {
        guard let api = error as? APIError else {
            return .init(message: "Google sign-in didn't finish. Try again.", email: nil, kind: .other)
        }
        switch api.code {
        case "account_exists_use_password":
            return .init(message: "This email already has a BiteDown password. Log in with your email and password above.",
                         email: email, kind: .existsWithPassword)
        case "identity_conflict":
            return .init(message: "This account is already linked to a different Google account.", email: nil, kind: .other)
        case "email_not_verified":
            return .init(message: "Verify your Google email, then try again.", email: nil, kind: .other)
        case "oauth_not_configured":
            return .init(message: "Google sign-in isn't available right now. Use email instead.", email: nil, kind: .other)
        case "invalid_token":
            return .init(message: "Google sign-in didn't work. Try again.", email: nil, kind: .other)
        default:
            return .init(message: api.isNetwork ? api.localizedDescription : "Google sign-in didn't work. Try again.",
                         email: nil, kind: .other)
        }
    }
}

enum GoogleSignInAvailability {
    /// The Google button shows only when the client id exists. `-UITestGoogle409` forces it on in DEBUG
    /// mock launches so the 409 path can be driven without a real client id.
    @MainActor static func isShown(_ env: AppEnvironment) -> Bool {
        #if DEBUG
        if env.launch.google409 { return true }
        #endif
        return GoogleSignInConfig.googleSignInEnabled
    }
}

/// The official Google button (the SDK's dark style in dark mode) plus the problem card below it.
/// Signing in posts the ID token to `POST /auth/oauth/google`; the API client stores the session,
/// so success needs no handling here (the app root swaps to the tabs).
struct GoogleSignInSection: View {
    @Environment(AppEnvironment.self) private var env
    @Environment(\.colorScheme) private var colorScheme
    @Binding var problem: GoogleSignInProblem?
    @State private var working = false

    var body: some View {
        VStack(spacing: Theme.Spacing.s + 2) {
            ZStack {
                GoogleSignInButton(scheme: colorScheme == .dark ? .dark : .light, style: .wide, state: working ? .disabled : .normal) {
                    Task { await start() }
                }
                .frame(minHeight: Theme.Size.minTouch + 6)
                .accessibilityLabel("Continue with Google")
                .accessibilityIdentifier(AccessibilityID.Auth.google)
                if working { ProgressView().tint(Theme.Colors.muted) }
            }
            if let problem {
                AuthNoticeCard(text: problem.message, identifier: AccessibilityID.Auth.googleAlert)
            }
        }
    }

    private func start() async {
        guard !working else { return }
        working = true
        problem = nil
        defer { working = false }
        var email: String?
        do {
            let idToken: String
            #if DEBUG
            if !GoogleSignInConfig.googleSignInEnabled {
                // Mock launch only (see `GoogleSignInAvailability`): no SDK round trip.
                idToken = "mock-id-token"
                email = MockData.priya.email
            } else {
                guard let result = try await Self.signInWithSDK() else { return }
                (idToken, email) = result
            }
            #else
            guard let result = try await Self.signInWithSDK() else { return }
            (idToken, email) = result
            #endif
            _ = try await env.api.googleSignIn(idToken: idToken)
            Haptics.success()
        } catch is CancellationError {
            return
        } catch let error as NSError where error.domain == kGIDSignInErrorDomain && error.code == GIDSignInError.canceled.rawValue {
            return
        } catch {
            Haptics.error()
            problem = GoogleSignInProblem.from(error, email: email)
        }
    }

    /// The SDK round trip. Nil when there is nothing to present from.
    @MainActor
    private static func signInWithSDK() async throws -> (String, String?)? {
        guard let presenter = topViewController() else { return nil }
        let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenter)
        guard let token = result.user.idToken?.tokenString else { throw APIError.server(status: 401, code: "invalid_token", message: "") }
        return (token, result.user.profile?.email)
    }

    @MainActor
    private static func topViewController() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
        var top = scene?.keyWindow?.rootViewController
        while let presented = top?.presentedViewController { top = presented }
        return top
    }
}
