import SwiftUI

extension Storage {
    var displayName: String {
        switch self {
        case .fridge: "Fridge"
        case .pantry: "Pantry"
        case .freezer: "Freezer"
        }
    }
}

/// Fridge / Pantry / Freezer (`StorageSegmented`, Fridge artboard): a `track` capsule with the
/// selected segment on `surface`. Built by hand so each segment carries its own id
/// (`fridge.storage.<s>`). Stacks vertically at accessibility text sizes.
struct StorageSegmentedControl: View {
    @Binding var selection: Storage
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var layout: AnyLayout {
        dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: Theme.Spacing.xs))
            : AnyLayout(HStackLayout(spacing: Theme.Spacing.xs))
    }

    var body: some View {
        layout {
            ForEach(Storage.allCases, id: \.self) { s in
                segment(s)
            }
        }
        .padding(.horizontal, Theme.Spacing.xs)
        .background(Theme.Colors.track, in: RoundedRectangle(cornerRadius: Theme.Radius.control, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Storage")
        .accessibilityIdentifier(AccessibilityID.Fridge.storage)
    }

    private func segment(_ s: Storage) -> some View {
        let selected = selection == s
        return Button {
            guard selection != s else { return }
            Haptics.selection()
            selection = s
        } label: {
            Text(s.displayName)
                .font(selected ? Theme.Fonts.segmentSelected : Theme.Fonts.segment)
                .foregroundStyle(selected ? Theme.Colors.ink : Theme.Colors.muted)
                .padding(.vertical, Theme.Spacing.xs)
                .frame(maxWidth: .infinity, minHeight: Theme.Size.segment)
                .background {
                    if selected {
                        RoundedRectangle(cornerRadius: Theme.Radius.badge, style: .continuous)
                            .fill(Theme.Colors.surface)
                    }
                }
                // The 36 pt segment sits in the track's 4 pt vertical padding, which is part of the
                // button, so the target is 44 pt tall.
                .padding(.vertical, Theme.Spacing.xs)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .motionAnimation(Theme.Motion.quick, value: selected)
        .accessibilityAddTraits(selected ? [.isSelected] : [])
        .accessibilityIdentifier(AccessibilityID.Fridge.storageOption(s.rawValue))
    }
}
