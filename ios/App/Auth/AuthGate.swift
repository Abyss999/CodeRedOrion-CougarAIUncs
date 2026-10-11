import SwiftUI

/// The app's auth gate. On launch it checks the session with `GET /auth/me`:
/// valid -> the tabs; none or 401 -> Landing / SessionExpired; server down -> an error with retry.
/// Afterwards it follows `AuthStore`: a global 401 anywhere (the API client calls `expireSession()`)
/// flips `isSignedIn`, and this root shows SessionExpired. No screen handles 401 itself.
struct AuthGate: View {
    @Environment(AppEnvironment.self) private var env
    @State private var phase: Phase = .checking

    private enum Phase: Equatable {
        case checking
        case failed(Failure)
        case ready
    }

    private struct Failure: Equatable {
        let message: String
        let offline: Bool
    }

    var body: some View {
        ZStack {
            Theme.Colors.ground.ignoresSafeArea()
            switch phase {
            case .checking:
                LaunchView().motionTransition(.opacity)
            case .failed(let failure):
                LaunchErrorView(failure: (failure.message, failure.offline)) { Task { await check() } }
                    .motionTransition(.opacity)
            case .ready:
                if env.auth.isSignedIn {
                    RootTabView().motionTransition(.opacity)
                } else {
                    AuthFlow(expired: env.auth.sessionExpired).motionTransition(.opacity)
                }
            }
        }
        .motionAnimation(Theme.Motion.quick, value: phase)
        .motionAnimation(Theme.Motion.quick, value: env.auth.isSignedIn)
        .task { await check() }
    }

    private func check() async {
        phase = .checking
        do {
            _ = try await env.api.me()
            phase = .ready
        } catch let error as APIError where error == .unauthorized {
            phase = .ready  // the client already cleared the token; Landing (or SessionExpired) shows
        } catch is CancellationError {
            return
        } catch {
            let api = error as? APIError
            phase = .failed(Failure(message: error.localizedDescription, offline: api?.isNetwork ?? false))
        }
    }
}

/// Row 23: the app mark and a native activity indicator while the stored sign-in is checked.
struct LaunchView: View {
    var body: some View {
        VStack(spacing: Theme.Spacing.l + 4) {
            AuthBrandMark()
            ProgressView()
                .controlSize(.large)
                .tint(Theme.Colors.muted)
                .accessibilityLabel("Loading")
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Auth.launch)
    }
}

/// The launch check couldn't reach the server: the mark, the error and a retry button.
struct LaunchErrorView: View {
    let failure: (message: String, offline: Bool)
    let retry: () -> Void

    var body: some View {
        VStack(spacing: Theme.Spacing.m) {
            AuthBrandMark().padding(.top, Theme.Spacing.xl)
            ErrorStateView(screen: "auth.launch",
                           error: failure.offline ? APIError.network(failure.message) : APIError.invalidRequest(failure.message),
                           retry: retry)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
