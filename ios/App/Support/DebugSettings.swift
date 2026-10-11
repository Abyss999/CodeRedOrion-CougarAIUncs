import SwiftUI

/// Small version label. In DEBUG a long press opens the settings sheet where the API base URL
/// can be pasted (e.g. a fresh Cloudflare tunnel URL). In Release it's a plain label.
struct VersionLabel: View {
    @Environment(AppEnvironment.self) private var env
    @State private var showDebug = false

    private var text: String {
        let v = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        let b = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"
        return "v\(v) (\(b))"
    }

    var body: some View {
        let label = Text(text)
            .font(Theme.Fonts.meta)
            .foregroundStyle(Theme.Colors.muted)
            .accessibilityIdentifier(AccessibilityID.Debug.versionLabel)
        #if DEBUG
        label
            .contentShape(Rectangle())
            .onLongPressGesture(minimumDuration: 0.8) { showDebug = true }
            .accessibilityAddTraits(.isButton)
            .accessibilityHint("Long press for debug settings")
            .sheet(isPresented: $showDebug) { DebugSettingsSheet(baseURL: env.baseURL) }
        #else
        label
        #endif
    }
}

#if DEBUG
struct DebugSettingsSheet: View {
    let baseURL: BaseURLProvider
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var error: String?
    @State private var current = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("API base URL") {
                    TextField("https://example.trycloudflare.com", text: $text)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                        .accessibilityIdentifier(AccessibilityID.Debug.baseURLField)
                    if let error {
                        Text(error).foregroundStyle(Theme.Colors.urgentInk)
                            .accessibilityIdentifier(AccessibilityID.Debug.baseURLError)
                    }
                    Text("In use: \(current)").font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                        .accessibilityIdentifier(AccessibilityID.Debug.baseURLCurrent)
                }
                Section {
                    Button("Save") { save() }.accessibilityIdentifier(AccessibilityID.Debug.baseURLSave)
                    Button("Reset to default", role: .destructive) {
                        baseURL.resetOverride(); error = nil; refresh()
                    }.accessibilityIdentifier(AccessibilityID.Debug.baseURLReset)
                } footer: {
                    Text("Overrides the Info.plist API_BASE_URL until reset. Must be http(s).")
                }
            }
            .navigationTitle("Debug settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .accessibilityIdentifier(AccessibilityID.Debug.settingsSheet)
        .onAppear(perform: refresh)
    }

    private func refresh() {
        current = baseURL.current.absoluteString
        text = baseURL.overrideURL?.absoluteString ?? ""
    }

    private func save() {
        if baseURL.setOverride(text) { error = nil; refresh() }
        else { error = "Enter a valid http:// or https:// URL." }
    }
}
#endif
