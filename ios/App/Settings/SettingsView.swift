import SwiftUI

/// Device-stored preferences beyond Units (which lives in `UnitSystem`).
enum SettingsKeys {
    static let defaultStorage = "default_storage"
    static let currency = "currency"
    static let currencies = ["USD", "EUR", "GBP", "CAD", "MXN", "INR"]
}

extension AccessibilityID.Settings {
    static let back = "settings.back"
    static let profile = "settings.profile"
    static let name = "settings.name"
    static let email = "settings.email"
    static let units = "settings.units"
    static let defaultStorage = "settings.storage"
    static let currency = "settings.currency"
    static let signOut = "settings.signout"
    static let deleteAccount = "settings.delete"
    static let deleteConfirm = "settings.delete.confirm"
    static let error = "settings.error"
    static let serverField = "settings.server.field"
    static let serverSave = "settings.server.save"
    static let serverReset = "settings.server.reset"
    static let serverError = "settings.server.error"
    static let version = "settings.version"
}

/// Profile and settings (artboard `Settings`). Present with `SettingsView()`, or
/// `SettingsView(focusServerAddress: true)` from ServerError's "Change".
struct SettingsView: View {
    var focusServerAddress = false

    @Environment(AppEnvironment.self) private var env
    @Environment(\.dismiss) private var dismiss
    @AppStorage(UnitSystem.storageKey) private var units: UnitSystem = .us
    @AppStorage(SettingsKeys.defaultStorage) private var defaultStorage: Storage = .fridge
    @AppStorage(SettingsKeys.currency) private var currency = "USD"

    @State private var me: Me?
    @State private var profileFailed = false
    @State private var confirmDelete = false
    @State private var deleting = false
    @State private var actionError: String?
    @State private var serverText = ""
    @State private var serverError: String?
    @State private var serverInUse = ""
    @FocusState private var serverFocused: Bool

    private var user: User? { me?.user ?? env.auth.user }

    private var versionText: String {
        let v = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        return "BiteDown \(v)"
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Spacing.m) {
                    header
                    profileCard
                    if let actionError {
                        BannerView(style: .error, message: actionError, dismiss: { self.actionError = nil }, identifiers: BannerIdentifiers(container: AccessibilityID.Settings.error), horizontalInset: 0)
                    }
                    preferences
                    account
                    #if DEBUG
                    debug.id("debug")
                    #endif
                    Text(versionText)
                        .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                        .frame(maxWidth: .infinity)
                        .padding(.top, Theme.Spacing.m)
                        .accessibilityIdentifier(AccessibilityID.Settings.version)
                }
                .padding(.horizontal, Theme.Spacing.gutter)
                .padding(.bottom, Theme.Spacing.xl)
            }
            .onAppear {
                if focusServerAddress {
                    DispatchQueue.main.async {
                        proxy.scrollTo("debug", anchor: .center)
                        serverFocused = true
                    }
                }
            }
        }
        .background(Theme.Colors.ground.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .accessibilityIdentifier(AccessibilityID.Settings.screen)
        .task { await loadProfile() }
        .onAppear(perform: refreshServer)
        .confirmationDialog("Delete your account?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete account", role: .destructive) { Task { await deleteAccount() } }
                .accessibilityIdentifier(AccessibilityID.Settings.deleteConfirm)
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes your food, friends and groups. It can't be undone.")
        }
    }

    // MARK: Sections

    private var header: some View {
        HStack(spacing: 10) {
            Button { dismiss() } label: {
                Image(systemName: "chevron.left")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(Theme.Colors.surface))
                    .overlay(Circle().strokeBorder(Theme.Colors.border, lineWidth: 1))
            }
            .accessibilityLabel("Back")
            .accessibilityIdentifier(AccessibilityID.Settings.back)
            Text("Profile").font(Theme.Fonts.screenTitle).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 0)
        }
        .padding(.top, Theme.Spacing.s)
    }

    private var profileCard: some View {
        HStack(spacing: 14) {
            Text(initials)
                .font(Theme.Fonts.cardHeading)
                .foregroundStyle(Theme.Colors.lime)
                .frame(width: 52, height: 52)
                .background(Circle().fill(Theme.Colors.forest))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                if let user {
                    Text(user.displayName).font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                        .accessibilityIdentifier(AccessibilityID.Settings.name)
                    Text(subtitle(user)).font(Theme.Fonts.callout).foregroundStyle(Theme.Colors.muted)
                        .accessibilityIdentifier(AccessibilityID.Settings.email)
                } else if profileFailed {
                    Text("Couldn't load your profile").font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.ink)
                    Button("Try again") { Task { await loadProfile() } }
                        .font(Theme.Fonts.callout).frame(minHeight: 44)
                } else {
                    RoundedRectangle(cornerRadius: 4).fill(Theme.Colors.track).frame(width: 140, height: 16)
                    RoundedRectangle(cornerRadius: 4).fill(Theme.Colors.track).frame(width: 180, height: 12)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Theme.Spacing.m).padding(.vertical, 14)
        .background(RoundedRectangle(cornerRadius: Theme.Radius.card).fill(Theme.Colors.surface))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(AccessibilityID.Settings.profile)
    }

    private var preferences: some View {
        section("Preferences") {
            VStack(spacing: 0) {
                prefRow("Units", id: AccessibilityID.Settings.units, value: units.displayName) {
                    Picker("Units", selection: $units) {
                        ForEach(UnitSystem.allCases) { Text($0.displayName).tag($0) }
                    }
                }
                divider
                prefRow("Default storage", id: AccessibilityID.Settings.defaultStorage, value: defaultStorage.rawValue.capitalized) {
                    Picker("Default storage", selection: $defaultStorage) {
                        ForEach(Storage.allCases, id: \.self) { Text($0.rawValue.capitalized).tag($0) }
                    }
                }
                divider
                prefRow("Currency", id: AccessibilityID.Settings.currency, value: currency) {
                    Picker("Currency", selection: $currency) {
                        ForEach(SettingsKeys.currencies, id: \.self) { Text($0).tag($0) }
                    }
                }
            }
            .card()
        }
    }

    private var account: some View {
        section("Account") {
            VStack(spacing: 0) {
                Button { env.auth.signOut() } label: {
                    rowLabel("Sign out", color: Theme.Colors.forest)
                }
                .accessibilityIdentifier(AccessibilityID.Settings.signOut)
                divider
                Button { confirmDelete = true } label: {
                    HStack {
                        rowLabel(deleting ? "Deleting…" : "Delete account…", color: Theme.Colors.urgentInk)
                        if deleting { ProgressView() }
                    }
                }
                .disabled(deleting)
                .accessibilityIdentifier(AccessibilityID.Settings.deleteAccount)
            }
            .card()
            Text("Deleting your account removes your food, friends and groups. Your past impact stays in totals anonymously.")
                .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
        }
    }

    #if DEBUG
    private var debug: some View {
        section("Debug") {
            VStack(alignment: .leading, spacing: Theme.Spacing.s) {
                Text("Server address").font(Theme.Fonts.body).foregroundStyle(Theme.Colors.ink)
                TextField("https://example.trycloudflare.com", text: $serverText)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.URL)
                    .focused($serverFocused)
                    .submitLabel(.done)
                    .onSubmit(saveServer)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .frame(minHeight: 44)
                    .background(RoundedRectangle(cornerRadius: Theme.Radius.input).fill(Theme.Colors.ground))
                    .overlay(RoundedRectangle(cornerRadius: Theme.Radius.input).strokeBorder(Theme.Colors.border, lineWidth: 1))
                    .accessibilityIdentifier(AccessibilityID.Settings.serverField)
                if let serverError {
                    Label(serverError, systemImage: "exclamationmark.triangle.fill")
                        .font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.urgentInk)
                        .accessibilityIdentifier(AccessibilityID.Settings.serverError)
                }
                Text("In use: \(serverInUse)").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                HStack {
                    Button("Save", action: saveServer)
                        .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.forest)
                        .frame(minWidth: 44, minHeight: 44)
                        .accessibilityIdentifier(AccessibilityID.Settings.serverSave)
                    Spacer()
                    Button("Reset to default") { env.baseURL.resetOverride(); serverError = nil; refreshServer() }
                        .font(Theme.Fonts.rowTitle).foregroundStyle(Theme.Colors.urgentInk)
                        .frame(minHeight: 44)
                        .accessibilityIdentifier(AccessibilityID.Settings.serverReset)
                }
            }
            .padding(Theme.Spacing.m)
            .frame(maxWidth: .infinity, alignment: .leading)
            .card()
        }
    }
    #endif

    // MARK: Pieces

    private var divider: some View {
        Rectangle().fill(Theme.Colors.hairline).frame(height: 1)
    }

    private func section<C: View>(_ title: String, @ViewBuilder _ content: () -> C) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(Theme.Fonts.groupHeader).textCase(.uppercase)
                .tracking(Theme.Tracking.groupHeader)
                .foregroundStyle(Theme.Colors.muted)
                .accessibilityAddTraits(.isHeader)
            content()
        }
    }

    private func rowLabel(_ text: String, color: Color) -> some View {
        Text(text).font(Theme.Fonts.rowTitle).foregroundStyle(color)
            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .padding(.horizontal, Theme.Spacing.m)
            .contentShape(Rectangle())
    }

    /// A row whose trailing value is a menu Picker.
    private func prefRow<P: View>(_ label: String, id: String, value: String, @ViewBuilder picker: () -> P) -> some View {
        HStack {
            Text(label).font(Theme.Fonts.body).foregroundStyle(Theme.Colors.ink)
            Spacer(minLength: Theme.Spacing.sm)
            picker().pickerStyle(.menu).labelsHidden().tint(Theme.Colors.muted)
        }
        .padding(.horizontal, Theme.Spacing.m)
        .frame(minHeight: 52)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(id)
    }

    private var initials: String {
        let name = user?.displayName ?? ""
        let letters = name.split(separator: " ").prefix(2).compactMap(\.first)
        return letters.isEmpty ? "?" : String(letters).uppercased()
    }

    private func subtitle(_ user: User) -> String {
        if me?.providers?.contains("google") == true, me?.hasPassword == false {
            return "\(user.email) · signed in with Google"
        }
        return user.email
    }

    // MARK: Actions

    private func loadProfile() async {
        profileFailed = false
        do { me = try await env.api.me() } catch { if user == nil { profileFailed = true } }
    }

    private func deleteAccount() async {
        deleting = true; actionError = nil
        defer { deleting = false }
        do {
            try await env.api.deleteAccount()
            env.auth.signOut()
        } catch {
            actionError = "Couldn't delete your account. Check your connection and try again."
        }
    }

    private func refreshServer() {
        serverInUse = env.baseURL.current.absoluteString
        serverText = env.baseURL.overrideURL?.absoluteString ?? ""
    }

    private func saveServer() {
        if env.baseURL.setOverride(serverText) { serverError = nil; refreshServer() }
        else {
            serverError = "Enter a valid http:// or https:// URL."
            AccessibilityNotification.Announcement("Error: enter a valid http or https URL.").post()
        }
    }
}

private extension View {
    func card() -> some View {
        background(RoundedRectangle(cornerRadius: Theme.Radius.card).fill(Theme.Colors.surface))
    }
}

#Preview {
    SettingsView().environment(AppEnvironment.preview())
}
