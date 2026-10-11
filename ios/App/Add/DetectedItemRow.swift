import SwiftUI

/// What a `DetectedItemRow` shows. PhotoReview, AddText and ReceiptReview each map their own model to this.
struct DetectedRowContent: Equatable {
    var name: String
    /// Receipt only: the line as printed, above the meta line.
    var rawLine: String?
    /// Meta text before the badge: the food group, plus the quantity where there is no stepper.
    var meta: String?
    /// The single status badge: an expiry range, "Use soon" or "Not sure". Nil for non-food lines.
    var badge: ExpiryBadgeModel?
    /// Dimmed, for non-food receipt lines ("Not food", unticked).
    var isDimmed = false

    /// VoiceOver text for the badge. "Not sure" is not an expiry, so it isn't prefixed with "Expires in".
    var badgeSpoken: String? {
        guard let badge else { return nil }
        return badge.text == "Not sure" ? "Not sure about this one" : badge.accessibilityText
    }

    /// VoiceOver text for the row.
    var spoken: String {
        [name, rawLine, meta, badgeSpoken].compactMap { $0 }.joined(separator: ", ")
    }
}

/// Accessibility identifiers for one row instance (each screen passes its own).
struct DetectedRowIdentifiers {
    var row: String
    var check: String
    var badge: String?
}

/// The one row for every add-review list (PhotoReview, AddText, ReceiptReview): a 24 pt checkbox inside a 44 pt
/// tappable area, the name, a meta line with one status badge, then a trailing slot (`QuantityStepper` for photos,
/// a price for receipts) and an optional expansion under the row (the inline quantity editor).
/// At accessibility text sizes the trailing slot stacks under the text.
struct DetectedItemRow<Trailing: View, Expansion: View>: View {
    let content: DetectedRowContent
    @Binding var isOn: Bool
    let ids: DetectedRowIdentifiers
    @ViewBuilder var trailing: () -> Trailing
    @ViewBuilder var expansion: () -> Expansion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            let layout = dynamicTypeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.s))
                : AnyLayout(HStackLayout(alignment: .center, spacing: Theme.Spacing.s))
            layout {
                checkboxButton
                trailingSlot
            }
            expansion()
        }
        .padding(.vertical, Theme.Spacing.s)
        .padding(.leading, Theme.Spacing.m - 2).padding(.trailing, Theme.Spacing.sm - 2)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(ids.row)
    }

    @ViewBuilder private var trailingSlot: some View {
        if Trailing.self != EmptyView.self {
            trailing()
                // Under the text, past the checkbox, at accessibility sizes.
                .padding(.leading, dynamicTypeSize.isAccessibilitySize ? Theme.AddFlow.checkbox + Theme.Spacing.sm : 0)
        }
    }

    private var checkboxButton: some View {
        Button { isOn.toggle(); Haptics.selection() } label: {
            HStack(spacing: Theme.Spacing.sm) {
                Circle()
                    .strokeBorder(isOn ? Theme.Colors.forest : Theme.Colors.muted, lineWidth: Theme.Stroke.selected)
                    .background(Circle().fill(isOn ? Theme.Colors.forest : .clear))
                    .overlay {
                        Image(systemName: "checkmark")
                            .font(.system(size: Theme.AddFlow.checkboxTick, weight: .bold))
                            .foregroundStyle(Theme.Colors.onForest)
                            .opacity(isOn ? 1 : 0)
                    }
                    .frame(width: Theme.AddFlow.checkbox, height: Theme.AddFlow.checkbox)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: Theme.Spacing.xxs) {
                    Text(content.name)
                        .font(Theme.Fonts.rowTitle)
                        .foregroundStyle(content.isDimmed ? Theme.Colors.muted : Theme.Colors.ink)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if let raw = content.rawLine {
                        Text(raw).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    metaLine
                }
            }
            .frame(minHeight: Theme.Size.minTouch)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(content.spoken)
        .accessibilityValue(isOn ? "Selected" : "Not selected")
        .accessibilityAddTraits(.isToggle)
        .accessibilityIdentifier(ids.check)
    }

    @ViewBuilder private var metaLine: some View {
        if content.meta != nil || content.badge != nil {
            let layout = dynamicTypeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.xs))
                : AnyLayout(HStackLayout(spacing: Theme.Spacing.stack))
            layout {
                if let meta = content.meta {
                    Text(meta).font(Theme.Fonts.meta).foregroundStyle(Theme.Colors.muted)
                }
                if let badge = content.badge {
                    ExpiryBadge(model: badge)
                        .accessibilityLabel(content.badgeSpoken ?? badge.accessibilityText)
                        .accessibilityIdentifier(ids.badge ?? ids.row + ".badge")
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

extension DetectedItemRow where Expansion == EmptyView {
    init(content: DetectedRowContent, isOn: Binding<Bool>, ids: DetectedRowIdentifiers,
         @ViewBuilder trailing: @escaping () -> Trailing) {
        self.init(content: content, isOn: isOn, ids: ids, trailing: trailing, expansion: { EmptyView() })
    }
}

extension DetectedItemRow where Trailing == EmptyView, Expansion == EmptyView {
    init(content: DetectedRowContent, isOn: Binding<Bool>, ids: DetectedRowIdentifiers) {
        self.init(content: content, isOn: isOn, ids: ids, trailing: { EmptyView() }, expansion: { EmptyView() })
    }
}

// MARK: - Badges for candidates

enum DetectedBadge {
    /// "Not sure" only when the detector sent a `confidence` under 0.5 (the Gemini fallback sends none);
    /// else "Use soon" for `semi_fresh`; else an estimated expiry range.
    static func make(expiry: Date?, freshness: Freshness?, confidence: Double?, now: Date = Date(),
                     calendar: Calendar = .current) -> ExpiryBadgeModel? {
        if let confidence, confidence < 0.5 { return .init(kind: .notSure) }
        if freshness == .semiFresh { return .init(kind: .useSoon) }
        guard let expiry else { return nil }
        let days = calendar.dateComponents([.day], from: calendar.startOfDay(for: now), to: calendar.startOfDay(for: expiry)).day ?? 0
        switch days {
        case ..<0: return .init(kind: .expired)
        case 0: return .init(kind: .today)
        case 1: return .init(kind: .tomorrow)
        default: return .init(kind: .estimated(days: days))
        }
    }

    /// Estimated ranges, not exact dates: 2–3 days … 3+ weeks.
    static func rangeText(days: Int) -> String {
        switch days {
        case ..<0: "Expired"
        case 0: "Today"
        case 1: "1 day"
        case 2...3: "2–3 days"
        case 4...5: "4–5 days"
        case 6...7: "6–7 days"
        case 8...14: "1–2 weeks"
        case 15...21: "2–3 weeks"
        default: "3+ weeks"
        }
    }
}

// MARK: - Quantity

enum QuantityText {
    static let units = ["piece", "oz", "lb", "g", "kg", "bag", "pack", "tub", "can", "jar", "bottle", "loaf", "dozen"]

    static func number(_ v: Double) -> String {
        let r = (v * 100).rounded() / 100
        if abs(r - r.rounded()) < 1e-9 { return String(Int(r.rounded())) }
        return String(format: abs(r * 10 - (r * 10).rounded()) < 1e-9 ? "%.1f" : "%.2f", r)
    }

    /// "1.4 lb", "1 bag", "12" (pieces show no unit).
    static func display(amount: Double, unit: String) -> String {
        unit == "piece" || unit.isEmpty ? number(amount) : "\(number(amount)) \(unit)"
    }

    /// Spoken form: "1.4 lb" -> "1.4 pounds".
    static func spoken(amount: Double, unit: String) -> String {
        let words = ["oz": "ounces", "lb": "pounds", "g": "grams", "kg": "kilograms", "piece": "pieces"]
        if let w = words[unit] { return "\(number(amount)) \(w)" }
        return display(amount: amount, unit: unit)
    }

    /// Stepper increment for a unit: whole numbers, halves for lb / kg.
    static func step(for unit: String) -> Double {
        switch unit { case "lb", "kg": 0.5; case "g": 50; default: 1 }
    }

    static func parse(_ text: String) -> Double? {
        let t = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        guard let v = Double(t), v > 0, v <= 10_000 else { return nil }
        return v
    }
}

/// `limeTint` pill: − / value / +. Buttons are 44 pt wide and tall (round 3); the value opens the inline editor.
struct QuantityStepper: View {
    let name: String
    @Binding var amount: Double
    let unit: String
    var isEditing: Bool
    var onEditAmount: () -> Void
    let ids: (less: String, more: String, amount: String)

    var body: some View {
        let step = QuantityText.step(for: unit)
        HStack(spacing: 0) {
            Button {
                amount = max(step, amount - step); Haptics.selection()
            } label: {
                Image(systemName: "minus").font(Theme.Fonts.button)
                    .frame(width: Theme.AddFlow.stepperButtonWidth, height: Theme.Size.minTouch)
                    .contentShape(Rectangle())
            }
            .disabled(amount <= step)
            .accessibilityLabel("Less")
            .accessibilityIdentifier(ids.less)

            Button(action: onEditAmount) {
                Text(QuantityText.display(amount: amount, unit: unit))
                    .font(Theme.Fonts.badge)
                    .foregroundStyle(Theme.Colors.ink)
                    .padding(.horizontal, Theme.Spacing.s).padding(.vertical, Theme.Spacing.stack)
                    .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.badge - 2, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: Theme.Radius.badge - 2, style: .continuous)
                            .strokeBorder(isEditing ? Theme.Colors.forest : Theme.Colors.border,
                                          lineWidth: isEditing ? Theme.Stroke.selected : Theme.Stroke.hairline)
                    }
                    .frame(minWidth: Theme.AddFlow.amountMinWidth, minHeight: Theme.Size.minTouch)
                    .contentShape(Rectangle())
                    .numericChange(value: amount)
            }
            .accessibilityLabel("Edit amount: \(QuantityText.spoken(amount: amount, unit: unit))")
            .accessibilityAddTraits(isEditing ? .isSelected : [])
            .accessibilityIdentifier(ids.amount)

            Button {
                amount += step; Haptics.selection()
            } label: {
                Image(systemName: "plus").font(Theme.Fonts.button)
                    .frame(width: Theme.AddFlow.stepperButtonWidth, height: Theme.Size.minTouch)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel("More")
            .accessibilityIdentifier(ids.more)
        }
        .foregroundStyle(Theme.Colors.forest)
        .background(Theme.Colors.limeTint, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Quantity of \(name)")
    }
}

/// The inline editor under a row: amount field, unit menu, Done. Edits are committed live when valid.
struct QuantityEditor: View {
    let name: String
    @Binding var amount: Double
    @Binding var unit: String
    let ids: (field: String, unit: String, done: String)
    var onDone: () -> Void
    @State private var text = ""
    @FocusState private var focused: Bool
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Spacing.s))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.s))
        layout {
            TextField("Amount", text: $text)
                .keyboardType(.decimalPad)
                .focused($focused)
                .font(Theme.Fonts.button)
                .foregroundStyle(Theme.Colors.ink)
                .padding(.horizontal, Theme.Spacing.sm)
                .frame(width: dynamicTypeSize.isAccessibilitySize ? nil : Theme.AddFlow.amountFieldWidth, height: Theme.Size.minTouch)
                .frame(maxWidth: dynamicTypeSize.isAccessibilitySize ? .infinity : nil)
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous).strokeBorder(Theme.Colors.forest, lineWidth: Theme.Stroke.selected) }
                .accessibilityLabel("Amount")
                .accessibilityIdentifier(ids.field)
                .onChange(of: text) { _, new in if let v = QuantityText.parse(new) { amount = v } }

            Menu {
                Picker("Unit", selection: $unit) {
                    ForEach(options, id: \.self) { Text($0).tag($0) }
                }
            } label: {
                HStack(spacing: Theme.Spacing.stack) {
                    Text(unit)
                    Image(systemName: "chevron.down").font(Theme.Fonts.badge)
                }
                .font(Theme.Fonts.button)
                .foregroundStyle(Theme.Colors.forest)
                .padding(.horizontal, Theme.Spacing.sm)
                .frame(minWidth: Theme.AddFlow.unitMenuMinWidth, minHeight: Theme.Size.minTouch)
                .background(Theme.Colors.surface, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                .overlay { RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous).strokeBorder(Theme.Colors.border, lineWidth: Theme.Stroke.hairline) }
                .contentShape(Rectangle())
            }
            .accessibilityLabel("Unit: \(unit)")
            .accessibilityIdentifier(ids.unit)

            if !dynamicTypeSize.isAccessibilitySize { Spacer(minLength: 0) }

            Button { commit(); onDone() } label: {
                Text("Done").font(Theme.Fonts.segmentSelected)
                    .foregroundStyle(Theme.Colors.onForest)
                    .padding(.horizontal, Theme.Spacing.m)
                    .frame(maxWidth: dynamicTypeSize.isAccessibilitySize ? .infinity : nil, minHeight: Theme.Size.minTouch)
                    .background(Theme.Colors.forest, in: RoundedRectangle(cornerRadius: Theme.Radius.input, style: .continuous))
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier(ids.done)
        }
        .padding(.leading, Theme.AddFlow.checkbox + Theme.Spacing.sm).padding(.vertical, Theme.Spacing.xs)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Edit amount for \(name)")
        .onAppear { text = QuantityText.number(amount); focused = true }
    }

    private var options: [String] { QuantityText.units.contains(unit) ? QuantityText.units : [unit] + QuantityText.units }

    private func commit() {
        if let v = QuantityText.parse(text) { amount = v }
    }
}
