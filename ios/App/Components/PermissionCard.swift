import SwiftUI
import UIKit

/// The permissions the app asks for, with the copy shown when access is off.
enum PermissionKind: String, Sendable, CaseIterable {
    case camera, microphone, speech

    var systemImage: String {
        switch self {
        case .camera: "camera.fill"
        case .microphone: "mic.fill"
        case .speech: "waveform"
        }
    }
    var title: String {
        switch self {
        case .camera: "Camera access is off"
        case .microphone: "Microphone access is off"
        case .speech: "Speech recognition is off"
        }
    }
    var message: String {
        switch self {
        case .camera: "BiteDown needs the camera to scan your fridge, food and receipts. You can turn it on in Settings, or add food by typing instead."
        case .microphone: "BiteDown needs the microphone to hear the food you say. You can turn it on in Settings, or type it instead."
        case .speech: "BiteDown needs speech recognition to turn what you say into items. You can turn it on in Settings, or type it instead."
        }
    }
}

/// Explains a denied permission and offers Settings, plus an optional alternative path
/// ("Type it instead"). Shown in place of the camera or mic UI, never as a dead end.
struct PermissionCard: View {
    let kind: PermissionKind
    var alternativeTitle: String?
    var alternative: (() -> Void)?
    /// Defaults to the app's page in Settings.
    var openSettings: () -> Void = {
        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
    }

    var body: some View {
        VStack(spacing: Theme.Spacing.m) {
            Image(systemName: kind.systemImage)
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.forest)
                .frame(width: Theme.Size.avatar, height: Theme.Size.avatar)
                .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.avatar, style: .continuous))
                .accessibilityHidden(true)
            Text(kind.title)
                .font(Theme.Fonts.cardHeading)
                .foregroundStyle(Theme.Colors.ink)
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            Text(kind.message)
                .font(Theme.Fonts.callout)
                .foregroundStyle(Theme.Colors.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            VStack(spacing: Theme.Spacing.xs) {
                Button(action: openSettings) {
                    Text("Open Settings")
                        .font(Theme.Fonts.button)
                        .foregroundStyle(Theme.Colors.onForest)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
                        .contentShape(Rectangle())
                }
                .accessibilityIdentifier(AccessibilityID.Permission.openSettings(kind.rawValue))
                if let alternativeTitle, let alternative {
                    Button(action: alternative) {
                        Text(alternativeTitle)
                            .font(Theme.Fonts.button)
                            .foregroundStyle(Theme.Colors.forest)
                            .frame(maxWidth: .infinity, minHeight: Theme.Size.sheetTextButton)
                            .contentShape(Rectangle())
                    }
                    .accessibilityIdentifier(AccessibilityID.Permission.alternative(kind.rawValue))
                }
            }
        }
        .padding(Theme.Spacing.l)
        .frame(maxWidth: .infinity)
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: Theme.Radius.hero, style: .continuous)
                .strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline)
        }
        .padding(.horizontal, Theme.Spacing.gutter)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Permission.card(kind.rawValue))
    }
}
