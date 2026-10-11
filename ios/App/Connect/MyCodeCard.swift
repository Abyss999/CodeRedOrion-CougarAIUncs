import SwiftUI
import Observation

/// Loads `GET /friends/code` and refreshes it when it expires.
@MainActor
@Observable
final class FriendCodeModel {
    private(set) var info: FriendCodeInfo?
    private(set) var error: Error?
    private(set) var isLoading = false
    private let api: APIClient

    init(api: APIClient) { self.api = api }

    func refresh() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            info = try await api.friendCode()
            error = nil
        } catch is CancellationError {
        } catch {
            self.error = error
        }
    }

    /// Sleeps until the current code expires, then fetches a new one. One failure stops the loop (Retry restarts it).
    func keepFresh() async {
        if info == nil { await refresh() }
        while !Task.isCancelled, let info {
            let wait = info.expiresAt.timeIntervalSinceNow
            if wait > 0 { try? await Task.sleep(for: .seconds(wait)) }
            if Task.isCancelled { return }
            await refresh()
            if error != nil { return }
        }
    }
}

/// The "My code" card (Connect artboard): QR in ink on lime, a countdown, Scan and Copy.
struct MyCodeCard: View {
    @State private var model: FriendCodeModel
    let scan: () -> Void
    @State private var copied = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(api: APIClient, scan: @escaping () -> Void) {
        _model = State(initialValue: FriendCodeModel(api: api))
        self.scan = scan
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Spacing.sm) {
            HStack(alignment: .center, spacing: Theme.Spacing.m) {
                qr
                VStack(alignment: .leading, spacing: Theme.Spacing.xs) {
                    Text("My code")
                        .font(Theme.Fonts.cardHeading)
                        .foregroundStyle(Theme.Colors.ink)
                        .accessibilityAddTraits(.isHeader)
                    Text("Refreshes every 10 min")
                        .font(Theme.Fonts.meta)
                        .foregroundStyle(Theme.Colors.inkSecondary)
                    countdown
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            if let error = model.error {
                Text(error.localizedDescription)
                    .font(Theme.Fonts.meta)
                    .foregroundStyle(Theme.Colors.urgentInk)
                Button("Try again") { Task { await model.keepFresh() } }
                    .font(Theme.Fonts.badge)
                    .frame(minHeight: Theme.Size.minTouch)
                    .foregroundStyle(Theme.Colors.forest)
            }
            buttons
        }
        .padding(Theme.Spacing.m)
        .background(Theme.Colors.lime, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(AccessibilityID.Connect.myCode)
        .task { await model.keepFresh() }
    }

    @ViewBuilder private var qr: some View {
        if let info = model.info {
            QRCodeImage(text: info.url, size: Theme.Size.qrCard, label: "Your friend code. A friend can scan it to add you.")
                .accessibilityIdentifier(AccessibilityID.Connect.myCodeQR)
        } else {
            RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous)
                .fill(Theme.Colors.qrGround)
                .overlay { if model.error == nil { ProgressView() } else { Image(systemName: "qrcode") } }
                .frame(width: Theme.Size.qrCard, height: Theme.Size.qrCard)
                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).strokeBorder(Theme.Colors.qrInk.opacity(0.3), lineWidth: Theme.Stroke.hairline) }
                .accessibilityLabel(model.error == nil ? "Loading your code" : "Code unavailable")
        }
    }

    @ViewBuilder private var countdown: some View {
        if let info = model.info {
            TimelineView(.periodic(from: .now, by: 1)) { ctx in
                let remaining = max(0, Int(info.expiresAt.timeIntervalSince(ctx.date).rounded(.up)))
                Label("New code in \(remaining / 60):\(String(format: "%02d", remaining % 60))", systemImage: "timer")
                    .font(Theme.Fonts.badge)
                    .monospacedDigit()
                    .foregroundStyle(Theme.Colors.ink)
                    // Spoken once per minute-ish value is noisy; speak the whole phrase only on demand.
                    .accessibilityLabel("New code in \(remaining / 60) minutes \(remaining % 60) seconds")
                    .accessibilityAddTraits(.updatesFrequently)
            }
            .accessibilityIdentifier(AccessibilityID.Connect.myCodeTimer)
        }
    }

    private var buttons: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        return layout {
            Button(action: scan) {
                Label("Scan a friend's code", systemImage: "qrcode.viewfinder")
                    .font(Theme.Fonts.badge)
                    .foregroundStyle(Theme.Colors.onForest)
                    .frame(maxWidth: .infinity, minHeight: Theme.Size.connectControl)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
            }
            .accessibilityIdentifier(AccessibilityID.Connect.scan)
            Button(action: copy) {
                Label(copied ? "Copied" : "Copy", systemImage: copied ? "checkmark" : "doc.on.doc")
                    .font(Theme.Fonts.badge)
                    .foregroundStyle(Theme.Colors.qrInk)
                    .padding(.horizontal, Theme.Spacing.sm)
                    .frame(minHeight: Theme.Size.connectControl)
                    .frame(maxWidth: dynamicTypeSize.isAccessibilitySize ? .infinity : nil)
                    .overlay { RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous).strokeBorder(Theme.Colors.qrInk, lineWidth: Theme.Stroke.selected) }
            }
            .disabled(model.info == nil)
            .accessibilityLabel("Copy my code")
            .accessibilityIdentifier(AccessibilityID.Connect.myCodeCopy)
        }
    }

    private func copy() {
        guard let info = model.info else { return }
        UIPasteboard.general.string = info.url
        copied = true
        Haptics.success()
        AccessibilityNotification.Announcement("Code copied").post()
        Task {
            try? await Task.sleep(for: .seconds(2))
            copied = false
        }
    }
}
