import SwiftUI
import Observation

/// Form state and server-error mapping for Log in. Errors are inline, per field (docs/API.md codes).
@MainActor
@Observable
final class LogInModel {
    var email: String
    var password = ""
    var emailError: String?
    var passwordError: String?
    var formError: String?
    var submitting = false
    /// Bumps on a rejected password so the field shakes (MOTION.md).
    var shakeCount = 0

    init(email: String = "") { self.email = email }

    func submit(api: APIClient) async {
        guard !submitting else { return }
        emailError = nil; passwordError = nil; formError = nil
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        if !Self.looksLikeEmail(trimmed) { emailError = "Enter the email you signed up with." }
        if password.isEmpty { passwordError = "Enter your password." }
        guard emailError == nil, passwordError == nil else { Haptics.error(); return }
        submitting = true
        defer { submitting = false }
        do {
            _ = try await api.login(email: trimmed, password: password)
            Haptics.success()
        } catch is CancellationError {
            return
        } catch {
            apply(error)
        }
    }

    func apply(_ error: Error) {
        Haptics.error()
        // Never reveal whether an email has an account: every non-network failure is the same message.
        if let api = error as? APIError, api.isNetwork {
            formError = api.localizedDescription
        } else {
            passwordError = "That email and password don't match. Try again."
            shakeCount += 1
        }
    }

    static func looksLikeEmail(_ s: String) -> Bool {
        let parts = s.split(separator: "@", omittingEmptySubsequences: false)
        return parts.count == 2 && !parts[0].isEmpty && parts[1].contains(".") && !s.contains(" ")
    }
}

/// Form state and server-error mapping for Sign up.
@MainActor
@Observable
final class SignUpModel {
    var name = ""
    var email = ""
    var password = ""
    var nameError: String?
    var emailError: String?
    var passwordError: String?
    var formError: String?
    var submitting = false
    var shakeCount = 0

    static let minimumPasswordLength = 8

    func submit(api: APIClient) async {
        guard !submitting else { return }
        nameError = nil; emailError = nil; passwordError = nil; formError = nil
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedName.isEmpty { nameError = "Add your name." }
        if !LogInModel.looksLikeEmail(trimmedEmail) { emailError = "Enter a valid email address." }
        if password.count < Self.minimumPasswordLength { passwordError = "Use at least 8 characters." }
        guard nameError == nil, emailError == nil, passwordError == nil else { Haptics.error(); return }
        submitting = true
        defer { submitting = false }
        do {
            _ = try await api.signup(email: trimmedEmail, password: password, displayName: trimmedName)
            Haptics.success()
        } catch is CancellationError {
            return
        } catch {
            apply(error)
        }
    }

    func apply(_ error: Error) {
        Haptics.error()
        let api = error as? APIError
        switch api?.code {
        case "email_taken":
            emailError = "That email is already registered. Log in instead."
        case "validation_error":
            let message = api?.localizedDescription ?? "Check the details and try again."
            if message.localizedCaseInsensitiveContains("password") { passwordError = message; shakeCount += 1 }
            else if message.localizedCaseInsensitiveContains("email") { emailError = message }
            else if message.localizedCaseInsensitiveContains("name") { nameError = message }
            else { formError = message }
        default:
            formError = api?.localizedDescription ?? "Something went wrong. Try again."
        }
    }
}

struct LogInView: View {
    @Environment(AppEnvironment.self) private var env
    var onSignUp: () -> Void
    @State private var model: LogInModel
    @State private var googleProblem: GoogleSignInProblem?

    init(prefillEmail: String? = nil, problem: GoogleSignInProblem? = nil, onSignUp: @escaping () -> Void) {
        self.onSignUp = onSignUp
        _model = State(initialValue: LogInModel(email: prefillEmail ?? ""))
        _googleProblem = State(initialValue: problem)
    }

    var body: some View {
        AuthScroll(identifier: AccessibilityID.Auth.logIn) {
            AuthHeader(title: "Welcome back", subtitle: "Your fridge missed you.")
            VStack(spacing: Theme.Spacing.sm + 2) {
                FormTextField(label: "Email", text: $model.email, error: model.emailError,
                              identifier: AccessibilityID.Auth.logInEmail,
                              keyboard: .emailAddress, contentType: .username, capitalization: .never)
                AuthPasswordField(label: "Password", text: $model.password, error: model.passwordError,
                                  identifier: AccessibilityID.Auth.logInPassword,
                                  toggleIdentifier: AccessibilityID.Auth.passwordToggle("login"),
                                  contentType: .password, onSubmit: submit)
                    .shake(trigger: model.shakeCount)
                if let formError = model.formError {
                    AuthFormError(text: formError, identifier: AccessibilityID.Auth.logInError)
                }
                AuthButton(title: "Log in", loading: model.submitting, identifier: AccessibilityID.Auth.logInSubmit, action: submit)
                    .padding(.top, Theme.Spacing.xs)
            }
            if GoogleSignInAvailability.isShown(env) {
                AuthDivider()
                GoogleSignInSection(problem: $googleProblem)
            }
            Spacer(minLength: Theme.Spacing.m)
            HStack(spacing: Theme.Spacing.xs) {
                Text("New here?").foregroundStyle(Theme.Colors.muted)
                Button("Create an account", action: onSignUp)
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(minHeight: Theme.Size.minTouch)
                    .accessibilityIdentifier(AccessibilityID.Auth.logInToSignUp)
            }
            .font(Theme.Fonts.callout)
            .frame(maxWidth: .infinity)
        }
    }

    private func submit() { Task { await model.submit(api: env.api) } }
}

struct SignUpView: View {
    @Environment(AppEnvironment.self) private var env
    var onLogIn: () -> Void
    @State private var model = SignUpModel()
    @State private var googleProblem: GoogleSignInProblem?

    var body: some View {
        AuthScroll(identifier: AccessibilityID.Auth.signUp) {
            AuthHeader(title: "Create your account", subtitle: "Start tracking what's in your fridge.")
            VStack(spacing: Theme.Spacing.sm + 2) {
                FormTextField(label: "Name", text: $model.name, error: model.nameError,
                              identifier: AccessibilityID.Auth.signUpName,
                              contentType: .name, capitalization: .words)
                FormTextField(label: "Email", text: $model.email, error: model.emailError,
                              identifier: AccessibilityID.Auth.signUpEmail,
                              keyboard: .emailAddress, contentType: .emailAddress, capitalization: .never)
                AuthPasswordField(label: "Password", text: $model.password, error: model.passwordError,
                                  helper: "At least 8 characters.",
                                  identifier: AccessibilityID.Auth.signUpPassword,
                                  toggleIdentifier: AccessibilityID.Auth.passwordToggle("signup"),
                                  contentType: passwordContentType, onSubmit: submit)
                    .shake(trigger: model.shakeCount)
                if let formError = model.formError {
                    AuthFormError(text: formError, identifier: AccessibilityID.Auth.signUpError)
                }
                AuthButton(title: "Create account", loading: model.submitting, identifier: AccessibilityID.Auth.signUpSubmit, action: submit)
                    .padding(.top, Theme.Spacing.xs)
            }
            if GoogleSignInAvailability.isShown(env) {
                AuthDivider()
                GoogleSignInSection(problem: $googleProblem)
                    .onChange(of: googleProblem) { _, new in
                        if let email = new?.email, model.email.isEmpty { model.email = email }
                    }
            }
            Spacer(minLength: Theme.Spacing.m)
            HStack(spacing: Theme.Spacing.xs) {
                Text("Already have an account?").foregroundStyle(Theme.Colors.muted)
                Button("Log in", action: onLogIn)
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(minHeight: Theme.Size.minTouch)
                    .accessibilityIdentifier(AccessibilityID.Auth.signUpToLogIn)
            }
            .font(Theme.Fonts.callout)
            .frame(maxWidth: .infinity)
        }
    }

    /// `.newPassword` offers iOS's Strong Password sheet, which swallows the first tap and typed input under
    /// UI automation. Mock (UI-test) launches use the plain password type; real launches keep `.newPassword`.
    private var passwordContentType: UITextContentType { env.launch.useMockAPI ? .password : .newPassword }

    private func submit() { Task { await model.submit(api: env.api) } }
}

/// Scrolling form page on the ground colour (keeps AX5 and the keyboard usable).
struct AuthScroll<Content: View>: View {
    let identifier: String
    @ViewBuilder var content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Spacing.l - 6) {
                content()
            }
            .padding(.horizontal, Theme.Spacing.l)
            .padding(.top, Theme.Spacing.s)
            .padding(.bottom, Theme.Spacing.l)
            .frame(maxWidth: .infinity)
        }
        .scrollBounceBehavior(.basedOnSize)
        .scrollDismissesKeyboard(.interactively)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(identifier)
    }
}
