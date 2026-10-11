import SwiftUI

enum AuthRoute: Hashable {
    case signUp
    case logIn(prefillEmail: String?, problem: GoogleSignInProblem?)
}

/// The signed-out experience: Landing (or the session-expired variant) with Sign up and Log in pushed on top.
struct AuthFlow: View {
    /// A global 401 ended the session (shows SessionExpired instead of Landing).
    let expired: Bool
    @State private var path: [AuthRoute] = []

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                if expired {
                    SessionExpiredView(openLogIn: { path.append(.logIn(prefillEmail: nil, problem: $0)) },
                                       prefill: { path.append(.logIn(prefillEmail: $0.email, problem: $0)) })
                } else {
                    LandingView(openSignUp: { path.append(.signUp) },
                                openLogIn: { path.append(.logIn(prefillEmail: nil, problem: nil)) },
                                openLogInAfterGoogle: { path.append(.logIn(prefillEmail: $0.email, problem: $0)) })
                }
            }
            .navigationDestination(for: AuthRoute.self) { route in
                switch route {
                case .signUp:
                    SignUpView(onLogIn: { replaceTop(with: .logIn(prefillEmail: nil, problem: nil)) })
                case let .logIn(email, problem):
                    LogInView(prefillEmail: email, problem: problem,
                              onSignUp: { replaceTop(with: .signUp) })
                }
            }
        }
        .tint(Theme.Colors.forest)
        .accessibilityIdentifier(AccessibilityID.Auth.screen)
    }

    private func replaceTop(with route: AuthRoute) {
        if !path.isEmpty { path.removeLast() }
        path.append(route)
    }
}

private struct LandingPoint: Identifiable {
    let id: String
    let symbol: String
    let title: String
}

/// Row 1: the sign-in entry. Mark, tagline, three value titles, then the buttons (Google last).
struct LandingView: View {
    @Environment(AppEnvironment.self) private var env
    var openSignUp: () -> Void
    var openLogIn: () -> Void
    var openLogInAfterGoogle: (GoogleSignInProblem) -> Void
    @State private var googleProblem: GoogleSignInProblem?

    private let points = [
        LandingPoint(id: "snap", symbol: "camera", title: "Snap your fridge or pantry"),
        LandingPoint(id: "cook", symbol: "frying.pan", title: "Cook what expires first"),
        LandingPoint(id: "save", symbol: "leaf", title: "See the food and money you save"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l - 2) {
                AuthBrandMark().frame(maxWidth: .infinity)
                Text("Use what you have. Share what you spare.")
                    .font(Theme.Fonts.signInHeadline)
                    .foregroundStyle(Theme.Colors.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                pointsCard
                VStack(spacing: Theme.Spacing.sm) {
                    AuthButton(title: "Sign up", identifier: AccessibilityID.Auth.landingSignUp, action: openSignUp)
                    AuthButton(title: "Log in", kind: .secondary, identifier: AccessibilityID.Auth.landingLogIn, action: openLogIn)
                    if GoogleSignInAvailability.isShown(env) {
                        AuthDivider(title: "or continue with")
                        GoogleSignInSection(problem: $googleProblem)
                    }
                    Text("By continuing you agree to the Terms and Privacy Policy.")
                        .font(Theme.Fonts.meta)
                        .foregroundStyle(Theme.Colors.muted)
                        .multilineTextAlignment(.center)
                        .padding(.top, Theme.Spacing.s)
                }
                .padding(.top, Theme.Spacing.s)
            }
            .padding(.horizontal, Theme.Spacing.l)
            .padding(.vertical, Theme.Spacing.l)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .onChange(of: googleProblem) { _, new in
            // The error card lives on Log in (GoogleSignInError), with the Google email prefilled.
            if let new, new.kind == .existsWithPassword { openLogInAfterGoogle(new); googleProblem = nil }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Auth.landing)
    }

    private var pointsCard: some View {
        VStack(spacing: Theme.Spacing.sm) {
            ForEach(points) { p in
                HStack(spacing: Theme.Spacing.tileInner) {
                    Image(systemName: p.symbol)
                        .font(.system(size: 20, weight: .semibold))
                        .foregroundStyle(Theme.Colors.forest)
                        .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                        .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
                        .accessibilityHidden(true)
                    Text(p.title).font(Theme.Fonts.button).foregroundStyle(Theme.Colors.ink)
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .padding(.horizontal, Theme.Spacing.m)
        .padding(.vertical, Theme.Spacing.sm + 2)
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
    }
}

/// Row 24: Landing after a global 401. A non-modal banner, then Log in and Google.
struct SessionExpiredView: View {
    @Environment(AppEnvironment.self) private var env
    var openLogIn: (GoogleSignInProblem?) -> Void
    var prefill: (GoogleSignInProblem) -> Void
    @State private var googleProblem: GoogleSignInProblem?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l - 2) {
                AuthNoticeCard(text: "You were signed out. Log in again to pick up where you left off.",
                               identifier: AccessibilityID.Auth.expiredBanner, prominent: true)
                AuthBrandMark().frame(maxWidth: .infinity).padding(.top, Theme.Spacing.s)
                Text("Log in")
                    .font(Theme.Fonts.signInHeadline)
                    .foregroundStyle(Theme.Colors.ink)
                    .accessibilityAddTraits(.isHeader)
                VStack(spacing: Theme.Spacing.sm) {
                    AuthButton(title: "Log in", identifier: AccessibilityID.Auth.landingLogIn) { openLogIn(nil) }
                    if GoogleSignInAvailability.isShown(env) {
                        AuthDivider(title: "or continue with")
                        GoogleSignInSection(problem: $googleProblem)
                    }
                }
            }
            .padding(.horizontal, Theme.Spacing.l)
            .padding(.vertical, Theme.Spacing.l)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .onChange(of: googleProblem) { _, new in
            if let new, new.kind == .existsWithPassword { prefill(new); googleProblem = nil }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Auth.landing)
    }
}
