import SwiftUI

/// FriendAdded artboard: the success screen after a scan or deep link. A 200 from the API means the
/// two of you were already friends, so the copy changes.
struct FriendAddedView: View {
    let result: FriendAddResult
    var scanAnother: (() -> Void)?
    let done: () -> Void

    private var initials: String {
        result.friend.displayName.split(separator: " ").prefix(2).compactMap { $0.first }.map(String.init).joined().uppercased()
    }
    private var message: String {
        result.alreadyFriends
            ? "You're already friends with \(result.friend.displayName)"
            : "You're now friends with \(result.friend.displayName)"
    }

    var body: some View {
        VStack(spacing: Theme.Spacing.l) {
            Spacer(minLength: Theme.Spacing.xl)
            Text(initials)
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.forest)
                .frame(width: Theme.Size.successAvatar, height: Theme.Size.successAvatar)
                .background(Theme.Colors.lime, in: Circle())
                .overlay(alignment: .bottomTrailing) {
                    Image(systemName: "checkmark.circle.fill")
                        .font(.title2)
                        .foregroundStyle(Theme.Colors.forest, Theme.Colors.surface)
                }
                .accessibilityHidden(true)
            Text(message)
                .font(Theme.Fonts.sheetTitle)
                .foregroundStyle(Theme.Colors.ink)
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier(AccessibilityID.FriendAdded.message)
            Spacer(minLength: Theme.Spacing.xl)
            VStack(spacing: Theme.Spacing.s) {
                Button(action: done) {
                    Text("Done")
                        .font(Theme.Fonts.button)
                        .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                        .foregroundStyle(Theme.Colors.onForest)
                        .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.optionTile, style: .continuous))
                }
                .accessibilityIdentifier(AccessibilityID.FriendAdded.done)
                if let scanAnother {
                    Button(action: scanAnother) {
                        Text("Scan another code")
                            .font(Theme.Fonts.button)
                            .foregroundStyle(Theme.Colors.forest)
                            .frame(maxWidth: .infinity, minHeight: Theme.Size.minTouch)
                    }
                    .accessibilityIdentifier(AccessibilityID.FriendAdded.scanAnother)
                }
            }
        }
        .padding(.horizontal, Theme.Spacing.gutter)
        .padding(.bottom, Theme.Spacing.l)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Theme.Colors.ground.ignoresSafeArea())
        .accessibilityIdentifier(AccessibilityID.FriendAdded.screen)
        .onAppear { AccessibilityNotification.Announcement(message).post() }
    }
}
