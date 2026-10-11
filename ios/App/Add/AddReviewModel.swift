import SwiftUI
import Observation

/// One line in an AddText / ReceiptReview / Barcode review. Candidates are not saved until `confirm`.
struct AddReviewRow: Identifiable, Equatable {
    let id = UUID()
    var candidate: Candidate
    /// Receipt only: the line as printed.
    var rawLine: String?
    var price: Double?
    var isOn = true
    var amount: Double
    var unit: String
    var isEditing = false
    /// Receipt only: a non-food line ("Not food", unticked, no badge).
    var isNonFood = false

    init(candidate: Candidate, rawLine: String? = nil, price: Double? = nil, nonFoodDetection: Bool = false) {
        self.candidate = candidate
        self.rawLine = rawLine
        self.price = price
        amount = candidate.quantity ?? 1
        unit = candidate.unit ?? "piece"
        if nonFoodDetection && candidate.foodGroup == .other && candidate.category == .other {
            isNonFood = true
            isOn = false
        }
    }

    /// Text rows show quantity + group in the meta line (the stepper is on the trailing side for these too).
    var content: DetectedRowContent {
        let group = isNonFood ? "Not food" : candidate.foodGroup.displayName
        let badge = isNonFood ? nil
            : DetectedBadge.make(expiry: candidate.predictedExpiry, freshness: candidate.freshness, confidence: candidate.confidence)
        return DetectedRowContent(name: candidate.name, rawLine: rawLine, meta: group, badge: badge, isDimmed: isNonFood)
    }
}

/// State and the confirm step shared by the text and receipt review lists.
@MainActor
@Observable
final class AddReviewModel {
    enum Phase: Equatable { case reviewing, saving, done(added: Int) }

    private(set) var rows: [AddReviewRow]
    private(set) var phase: Phase = .reviewing
    private(set) var addError: String?
    /// `text`, `receipt` or `barcode` (the `source` the server stores).
    let source: String
    let total: Double?
    private let api: APIClient

    init(rows: [AddReviewRow], source: String, total: Double? = nil, api: APIClient) {
        self.rows = rows; self.source = source; self.total = total; self.api = api
    }

    var addCount: Int { rows.filter(\.isOn).count }
    var foodCount: Int { rows.filter { !$0.isNonFood }.count }
    var canConfirm: Bool { phase == .reviewing && addCount > 0 }

    func setOn(_ on: Bool, at i: Int) { rows[i].isOn = on }
    func setAmount(_ v: Double, at i: Int) { rows[i].amount = v }
    func setUnit(_ u: String, at i: Int) { rows[i].unit = u }
    func setEditing(_ e: Bool, at i: Int) { rows[i].isEditing = e }

    func confirm() async {
        guard canConfirm else { return }
        let source = source
        let items: [NewItem] = rows.filter(\.isOn).map { row in
            var n = NewItem(candidate: row.candidate, source: source)
            n.quantity = row.amount
            n.unit = row.unit
            if let price = row.price { n.estPrice = price }
            return n
        }
        phase = .saving
        addError = nil
        do {
            _ = try await api.createItems(items)
        } catch {
            phase = .reviewing
            addError = (error as? LocalizedError)?.errorDescription ?? "Couldn't add those items."
            Haptics.error()
            return
        }
        NotificationCenter.default.post(name: .itemsDidChange, object: nil)
        Haptics.success()
        phase = .done(added: items.count)
    }
}

/// Shared list of review rows (text and receipt). `showsPrice` puts the printed price in the trailing slot
/// (receipt); otherwise the row gets the quantity stepper and inline editor (text).
struct AddReviewList: View {
    @Bindable var model: AddReviewModel
    let showsPrice: Bool
    let idPrefix: String
    @MotionReduced private var reduceMotion
    @State private var shown = false

    var body: some View {
        VStack(spacing: 0) {
            ForEach(Array(model.rows.indices), id: \.self) { i in
                row(i)
                    .opacity(shown || reduceMotion ? 1 : 0)
                    .animation(Theme.Motion.animation(Theme.Motion.staggerItem.delay(Theme.Motion.staggerDelay(index: i)), reduceMotion: reduceMotion), value: shown)
                if i != model.rows.count - 1 { Divider().overlay(Theme.Colors.hairline) }
            }
        }
        .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
        .onAppear { shown = true }
    }

    private func row(_ i: Int) -> some View {
        let r = model.rows[i]
        let ids = DetectedRowIdentifiers(row: "\(idPrefix).row.\(i)", check: "\(idPrefix).row.\(i).check", badge: "\(idPrefix).row.\(i).badge")
        return DetectedItemRow(
            content: r.content,
            isOn: Binding(get: { model.rows[i].isOn }, set: { model.setOn($0, at: i) }),
            ids: ids,
            trailing: {
                if showsPrice {
                    if let price = r.price {
                        Text(price, format: .currency(code: "USD"))
                            .font(Theme.Fonts.rowTitle)
                            .foregroundStyle(r.isNonFood ? Theme.Colors.muted : Theme.Colors.ink)
                            .accessibilityLabel("Price \(price.formatted(.currency(code: "USD")))")
                            .accessibilityIdentifier("\(idPrefix).row.\(i).price")
                    }
                } else {
                    QuantityStepper(
                        name: r.candidate.name,
                        amount: Binding(get: { model.rows[i].amount }, set: { model.setAmount($0, at: i) }),
                        unit: r.unit, isEditing: r.isEditing,
                        onEditAmount: { withMotion(reduceMotion: reduceMotion) { model.setEditing(!model.rows[i].isEditing, at: i) } },
                        ids: ("\(idPrefix).row.\(i).less", "\(idPrefix).row.\(i).more", "\(idPrefix).row.\(i).amount"))
                }
            },
            expansion: {
                if !showsPrice && r.isEditing {
                    QuantityEditor(
                        name: r.candidate.name,
                        amount: Binding(get: { model.rows[i].amount }, set: { model.setAmount($0, at: i) }),
                        unit: Binding(get: { model.rows[i].unit }, set: { model.setUnit($0, at: i) }),
                        ids: ("\(idPrefix).row.\(i).amountfield", "\(idPrefix).row.\(i).unit", "\(idPrefix).row.\(i).done"),
                        onDone: { withMotion(reduceMotion: reduceMotion) { model.setEditing(false, at: i) } })
                        .motionTransition(.opacity.combined(with: .move(edge: .top)))
                }
            })
    }
}

/// The primary "Add N items" footer used under a review list.
struct AddConfirmFooter: View {
    let title: String
    let isSaving: Bool
    let enabled: Bool
    let error: String?
    let confirmID: String
    let errorID: String
    let action: () -> Void

    var body: some View {
        VStack(spacing: Theme.Spacing.s) {
            if let error {
                BannerView(style: .error, message: error, retryTitle: "Try again", retry: action,
                           identifiers: BannerIdentifiers(container: errorID, retry: errorID + ".retry"), horizontalInset: 0)
            }
            Button(action: action) {
                Group {
                    if isSaving { ProgressView().tint(Theme.Colors.onForest) } else { Text(title) }
                }
                .font(Theme.Fonts.button)
                .foregroundStyle(Theme.Colors.onForest)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.primaryButton)
                .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous))
                .contentShape(Rectangle())
            }
            .disabled(!enabled)
            .opacity(enabled || isSaving ? 1 : 0.45)
            .accessibilityLabel(isSaving ? "Adding" : title)
            .accessibilityIdentifier(confirmID)
        }
        .padding(.horizontal, Theme.Spacing.gutter).padding(.top, Theme.Spacing.sm).padding(.bottom, Theme.Spacing.m)
        .background(Theme.Colors.ground)
        .overlay(alignment: .top) { Divider().overlay(Theme.Colors.hairline) }
    }
}

func addItemsTitle(_ n: Int) -> String { n == 1 ? "Add 1 item" : "Add \(n) items" }
