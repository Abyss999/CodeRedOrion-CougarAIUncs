import SwiftUI

/// A form field: a visible label above the control, an inline error below it. The label is also the
/// control's accessibility label; when there is an error it is spoken as the control's hint and announced
/// once when it appears. The error carries an icon and text, so colour is never the only cue.
struct FormField<Content: View>: View {
    let label: String
    var error: String?
    /// Prefix for identifiers: the error uses `<identifier>.error`.
    var identifier: String
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(label)
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.inkSecondary)
                .accessibilityHidden(true)
            content()
                .accessibilityLabel(label)
                .accessibilityHint(error.map { "Error: \($0)" } ?? "")
                .accessibilityIdentifier(identifier)
            if let error {
                Label(error, systemImage: "exclamationmark.circle.fill")
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.urgentInk)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(error)
                    .accessibilityIdentifier(identifier + ".error")
            }
        }
        .onChange(of: error) { _, new in
            if let new { AccessibilityNotification.Announcement("\(label): \(new)").post() }
        }
    }
}

/// `FormField` around a bordered text field (or secure field) in the app's input style.
struct FormTextField: View {
    let label: String
    @Binding var text: String
    var error: String?
    var prompt = ""
    var identifier: String
    var isSecure = false
    var keyboard: UIKeyboardType = .default
    var contentType: UITextContentType?
    var capitalization: TextInputAutocapitalization = .sentences
    @FocusState private var focused: Bool

    var body: some View {
        FormField(label: label, error: error, identifier: identifier) {
            Group {
                if isSecure {
                    SecureField(prompt, text: $text)
                } else {
                    TextField(prompt, text: $text)
                        .keyboardType(keyboard)
                        .textInputAutocapitalization(capitalization)
                        .autocorrectionDisabled(keyboard == .emailAddress)
                }
            }
            .textContentType(contentType)
            .focused($focused)
            .font(Theme.Fonts.body)
            .foregroundStyle(Theme.Colors.ink)
            .padding(.horizontal, Theme.Spacing.sm)
            .frame(minHeight: Theme.Size.minTouch)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                    .strokeBorder(borderColor, lineWidth: error != nil || focused ? Theme.Stroke.selected : Theme.Stroke.hairline)
            }
        }
    }

    private var borderColor: Color {
        error != nil ? Theme.Colors.urgentInk : (focused ? Theme.Colors.forest : Theme.Colors.border)
    }
}
