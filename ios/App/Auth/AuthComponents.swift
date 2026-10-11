import SwiftUI

/// The BiteDown app mark: a lime leaf on a forest rounded square (Launch / Landing artboards).
struct AuthBrandMark: View {
    var size: CGFloat = 80

    var body: some View {
        RoundedRectangle(cornerRadius: size * 0.275, style: .continuous)
            .fill(Theme.Colors.forest)
            .frame(width: size, height: size)
            .overlay {
                LeafGlyph()
                    .stroke(Theme.Colors.lime, style: StrokeStyle(lineWidth: 2 * (size * 0.55 / 24), lineCap: .round, lineJoin: .round))
                    .frame(width: size * 0.55, height: size * 0.55)
            }
            .accessibilityElement()
            .accessibilityLabel("BiteDown")
            .accessibilityAddTraits(.isImage)
    }
}

/// The leaf from the artboards (24 pt grid: `M5 19c8 0 14-6 14-14C11 5 5 11 5 19z` plus the vein).
struct LeafGlyph: Shape {
    func path(in rect: CGRect) -> Path {
        let s = rect.width / 24
        func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * s, y: rect.minY + y * s) }
        var path = Path()
        path.move(to: p(5, 19))
        path.addCurve(to: p(19, 5), control1: p(13, 19), control2: p(19, 13))
        path.addCurve(to: p(5, 19), control1: p(11, 5), control2: p(5, 11))
        path.closeSubpath()
        path.move(to: p(5, 19))
        path.addLine(to: p(12, 12))
        return path
    }
}

/// Full-width 56 pt button. `loading` swaps the title for a progress indicator and blocks taps.
struct AuthButton: View {
    enum Kind { case primary, secondary }
    let title: String
    var kind: Kind = .primary
    var loading = false
    var identifier: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                Text(title).font(Theme.Fonts.button).opacity(loading ? 0 : 1)
                if loading { ProgressView().tint(Theme.Colors.onForest) }
            }
            .foregroundStyle(Theme.Colors.onForest)
            .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
            .background(kind == .primary ? Theme.Colors.forest : Theme.Colors.forestMid,
                        in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
            .contentShape(RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        }
        .buttonStyle(.plain)
        .disabled(loading)
        .accessibilityLabel(loading ? "\(title), working" : title)
        .accessibilityIdentifier(identifier)
    }
}

/// "or" / "or continue with" divider between the email form and the Google button.
struct AuthDivider: View {
    var title = "or"

    var body: some View {
        HStack(spacing: Theme.Spacing.sm) {
            Rectangle().fill(Theme.Colors.border).frame(height: Theme.Stroke.hairline)
            Text(title).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted).fixedSize()
            Rectangle().fill(Theme.Colors.border).frame(height: Theme.Stroke.hairline)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
        .accessibilityHidden(true)
    }
}

/// Yellow inline card (session ended, Google problems). Icon plus text, announced when it appears.
struct AuthNoticeCard: View {
    let text: String
    var identifier: String
    var prominent = false

    var body: some View {
        HStack(alignment: .top, spacing: prominent ? Theme.Spacing.sm : Theme.Spacing.s + 2) {
            Image(systemName: "info.circle")
                .font(.system(size: prominent ? 22 : 20, weight: .semibold))
                .accessibilityHidden(true)
            Text(text)
                .font(prominent ? Theme.Fonts.rowTitle : Theme.Fonts.callout.weight(.medium))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .foregroundStyle(Theme.Colors.useSoonInk)
        .padding(.horizontal, prominent ? Theme.Spacing.m : Theme.Spacing.sm + 2)
        .padding(.vertical, prominent ? Theme.Spacing.sm + 2 : Theme.Spacing.sm)
        .background(Theme.Colors.useSoonBg, in: RoundedRectangle(cornerRadius: prominent ? Theme.Radius.card : Theme.Radius.control, style: .continuous))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(text)
        .accessibilityIdentifier(identifier)
        .onAppear { AccessibilityNotification.Announcement(text).post() }
    }
}

/// Password field with a show/hide toggle (44 pt), label above and an inline error or helper below.
/// The identifier sits on the text field itself; the error uses `<identifier>.error`.
struct AuthPasswordField: View {
    let label: String
    @Binding var text: String
    var error: String?
    var helper: String?
    var identifier: String
    var toggleIdentifier: String
    var contentType: UITextContentType = .password
    var onSubmit: () -> Void = {}
    @State private var revealed = false
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs + 2) {
            Text(label)
                .font(Theme.Fonts.badge)
                .foregroundStyle(Theme.Colors.inkSecondary)
                .accessibilityHidden(true)
            HStack(spacing: 0) {
                Group {
                    if revealed {
                        TextField("", text: $text)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    } else {
                        SecureField("", text: $text)
                    }
                }
                .textContentType(contentType)
                .focused($focused)
                .submitLabel(.go)
                .onSubmit(onSubmit)
                .font(Theme.Fonts.body)
                .foregroundStyle(Theme.Colors.ink)
                .frame(minHeight: Theme.Size.minTouch)
                .accessibilityLabel(label)
                .accessibilityHint(error.map { "Error: \($0)" } ?? helper ?? "")
                .accessibilityIdentifier(identifier)

                Button { revealed.toggle() } label: {
                    Image(systemName: revealed ? "eye.slash" : "eye")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Theme.Colors.muted)
                        .frame(width: Theme.Size.minTouch, height: Theme.Size.minTouch)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(revealed ? "Hide password" : "Show password")
                .accessibilityIdentifier(toggleIdentifier)
            }
            .padding(.leading, Theme.Spacing.sm + 2)
            .padding(.trailing, Theme.Spacing.xs + 2)
            .frame(minHeight: Theme.Size.minTouch + 6)
            .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                    .strokeBorder(borderColor, lineWidth: error != nil || focused ? Theme.Stroke.selected : Theme.Stroke.hairline)
            }
            if let error {
                Label(error, systemImage: "exclamationmark.circle.fill")
                    .font(Theme.Fonts.meta.weight(.medium))
                    .foregroundStyle(Theme.Colors.urgentInk)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(error)
                    .accessibilityIdentifier(identifier + ".error")
            } else if let helper {
                Text(helper)
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.muted)
                    .accessibilityHidden(true)
            }
        }
        .onChange(of: error) { _, new in
            if let new { AccessibilityNotification.Announcement("\(label): \(new)").post() }
        }
    }

    private var borderColor: Color {
        error != nil ? Theme.Colors.urgentInk : (focused ? Theme.Colors.forest : Theme.Colors.border)
    }
}

/// A form-level error line (network trouble, anything not tied to one field).
struct AuthFormError: View {
    let text: String
    var identifier: String

    var body: some View {
        Label(text, systemImage: "exclamationmark.circle.fill")
            .font(Theme.Fonts.meta.weight(.medium))
            .foregroundStyle(Theme.Colors.urgentInk)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(text)
            .accessibilityIdentifier(identifier)
            .onAppear { AccessibilityNotification.Announcement(text).post() }
    }
}

/// Large screen title + subtitle used by SignUp / LogIn.
struct AuthHeader: View {
    let title: String
    let subtitle: String

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
            Text(title).font(Theme.Fonts.screenTitle).foregroundStyle(Theme.Colors.ink)
                .accessibilityAddTraits(.isHeader)
            Text(subtitle).font(Theme.Fonts.body).foregroundStyle(Theme.Colors.muted)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
