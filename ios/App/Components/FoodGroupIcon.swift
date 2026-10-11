import SwiftUI

extension FoodGroup {
    enum Glyph {
        case asset(String)
        case symbol(String)
    }

    /// Custom template assets (Assets.xcassets) where SF Symbols has no match; SF Symbols otherwise.
    var glyph: Glyph {
        switch self {
        case .protein: .asset("FoodGroupProtein")
        case .veggies: .symbol("carrot")
        case .fruit: .asset("FoodGroupFruit")
        case .dairy: .asset("FoodGroupDairy")
        case .grains: .asset("FoodGroupGrains")
        case .pantry: .asset("FoodGroupPantry")
        case .leftovers: .symbol("takeoutbag.and.cup.and.straw")
        case .frozen: .symbol("snowflake")
        case .other: .symbol("circle.grid.2x2")
        }
    }

    var palette: Theme.FoodGroup.Palette {
        switch self {
        case .protein: Theme.FoodGroup.protein
        case .veggies: Theme.FoodGroup.veggies
        case .fruit: Theme.FoodGroup.fruit
        case .dairy: Theme.FoodGroup.dairy
        case .grains: Theme.FoodGroup.grains
        case .pantry: Theme.FoodGroup.pantry
        case .leftovers: Theme.FoodGroup.leftovers
        case .frozen: Theme.FoodGroup.frozen
        case .other: Theme.FoodGroup.other
        }
    }
}

/// The bare glyph in the group's stroke colour (used in the Fridge group header, 16 pt).
struct FoodGroupGlyph: View {
    let group: FoodGroup
    var size: CGFloat = 22

    var body: some View {
        Group {
            switch group.glyph {
            case .asset(let name): Image(name).renderingMode(.template).resizable().scaledToFit()
            case .symbol(let name): Image(systemName: name).resizable().scaledToFit()
            }
        }
        .frame(width: size, height: size)
        .foregroundStyle(group.palette.stroke)
        .accessibilityHidden(true)   // the group name always appears beside the icon
    }
}

/// 40 pt rounded tile in the group's colours with the glyph on it (ItemRow avatar).
struct FoodGroupIcon: View {
    let group: FoodGroup
    var tile: CGFloat = Theme.Size.avatar

    var body: some View {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
            .fill(group.palette.tile)
            .frame(width: tile, height: tile)
            .overlay { FoodGroupGlyph(group: group, size: tile * 0.55) }
            .accessibilityHidden(true)
    }
}
