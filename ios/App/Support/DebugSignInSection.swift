import SwiftUI

#if DEBUG
/// DEBUG-only quick sign-in for the Debug settings sheet, so the live backend can be used before the
/// Auth screens land. Uses the same `APIClient.login` / `signup`, which store the token in `AuthStore`
/// (memory-only if the Keychain save fails, e.g. unsigned simulator builds); later requests use it.
struct DebugAccountSection: View {
    let api: APIClient
    let auth: AuthStore
    @State private var email = ""
    @State private var password = ""
    @State private var name = ""
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        Section("Account (debug)") {
            Text(auth.user.map { "Signed in as \($0.email)" } ?? "Signed out")
                .font(Theme.Fonts.meta)
                .foregroundStyle(Theme.Colors.muted)
                .accessibilityIdentifier(AccessibilityID.Debug.accountStatus)
            FormTextField(label: "Email", text: $email, prompt: "you@example.com",
                          identifier: AccessibilityID.Debug.accountEmail, keyboard: .emailAddress,
                          contentType: .emailAddress, capitalization: .never)
            FormTextField(label: "Password", text: $password, prompt: "Password",
                          identifier: AccessibilityID.Debug.accountPassword, isSecure: true)
            FormTextField(label: "Display name (sign up only)", text: $name, prompt: "Name",
                          identifier: AccessibilityID.Debug.accountName, capitalization: .words)
            if let error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(Theme.Colors.urgentInk)
                    .accessibilityIdentifier(AccessibilityID.Debug.accountError)
            }
            Button("Sign in") { run { _ = try await api.login(email: trimmedEmail, password: password) } }
                .frame(minHeight: Theme.Size.minTouch)
                .disabled(busy || trimmedEmail.isEmpty || password.isEmpty)
                .accessibilityIdentifier(AccessibilityID.Debug.accountSignIn)
            Button("Create account") {
                run { _ = try await api.signup(email: trimmedEmail, password: password,
                                               displayName: name.isEmpty ? "Debug user" : name) }
            }
            .frame(minHeight: Theme.Size.minTouch)
            .disabled(busy || trimmedEmail.isEmpty || password.isEmpty)
            .accessibilityIdentifier(AccessibilityID.Debug.accountSignUp)
            Button("Sign out", role: .destructive) { auth.signOut(); error = nil }
                .frame(minHeight: Theme.Size.minTouch)
                .disabled(!auth.isSignedIn)
                .accessibilityIdentifier(AccessibilityID.Debug.accountSignOut)
        }
    }

    private var trimmedEmail: String { email.trimmingCharacters(in: .whitespacesAndNewlines) }

    private func run(_ op: @escaping () async throws -> Void) {
        busy = true; error = nil
        Task {
            do { try await op(); password = "" }
            catch { self.error = error.localizedDescription }
            busy = false
        }
    }
}
#endif
