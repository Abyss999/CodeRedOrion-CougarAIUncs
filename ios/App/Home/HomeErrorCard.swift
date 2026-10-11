import SwiftUI

/// ServerError's "Use these first" card: "Couldn't load your food", Try again, and the server row
/// ("Using <host>" + Change, which opens Settings › Debug "Server address" once Settings exists).
struct HomeErrorCard: View {
    let host: String
    let retry: () -> Void
    let onChangeServer: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(spacing: 0) {
            VStack(spacing: Theme.Spacing.s) {
                Image(systemName: "icloud.slash")
                    .font(.title2)
                    .foregroundStyle(Theme.Colors.forest)
                    .frame(width: 52, height: 52)
                    .background(Theme.Colors.limeTint, in: Circle())
                    .accessibilityHidden(true)
                Text("Couldn't load your food")
                    .font(Theme.Fonts.cardHeading)
                    .foregroundStyle(Theme.Colors.ink)
                    .multilineTextAlignment(.center)
                    .accessibilityAddTraits(.isHeader)
                Button(action: retry) {
                    Text("Try again")
                        .font(Theme.Fonts.rowTitle)
                        .foregroundStyle(Theme.Colors.forest)
                        .padding(.horizontal, Theme.Spacing.m)
                        .frame(minHeight: Theme.Size.minTouch)
                        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous)
                            .strokeBorder(Theme.Colors.border, lineWidth: 1))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.top, Theme.Spacing.xs)
                .accessibilityIdentifier(AccessibilityID.State.retry("home"))
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, Theme.Spacing.gutter)
            .padding(.top, Theme.Spacing.l + Theme.Spacing.xs)
            .padding(.bottom, Theme.Spacing.l - Theme.Spacing.xxs)

            Divider().overlay(Theme.Colors.hairline)
            serverRow
        }
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.State.error("home"))
    }

    @ViewBuilder private var serverRow: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.xs))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        layout {
            HStack(spacing: Theme.Spacing.s) {
                Image(systemName: "server.rack")
                    .font(.footnote)
                    .foregroundStyle(Theme.Colors.muted)
                    .accessibilityHidden(true)
                Text("Using \(host)")
                    .font(Theme.Fonts.callout)
                    .foregroundStyle(Theme.Colors.muted)
                    .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 1)
                    .truncationMode(.middle)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Button(action: onChangeServer) {
                Text("Change")
                    .font(Theme.Fonts.rowTitle)
                    .foregroundStyle(Theme.Colors.forest)
                    .padding(.horizontal, Theme.Spacing.s)
                    .frame(minWidth: Theme.Size.minTouch, minHeight: Theme.Size.minTouch)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Change server address")
            .accessibilityIdentifier(AccessibilityID.Home.serverChange)
        }
        .padding(.leading, Theme.Spacing.m)
        .padding(.trailing, Theme.Spacing.s)
        .padding(.vertical, Theme.Spacing.xs)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Home.server)
    }
}
