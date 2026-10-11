import Foundation

/// Static "What to look for" copy per food group (ItemDetail artboard). Signs, not a safety guarantee.
enum WhatToLookFor {
    static let disclaimer = "These are signs, not a safety guarantee."

    static func signs(for group: FoodGroup) -> [String] {
        switch group {
        case .protein: ["Slimy or sticky surface", "Sour or sulfur smell", "Grey, green or dull colour"]
        case .veggies: ["Slimy or dark wet leaves", "Sour or off smell", "Yellowing across the bag"]
        case .fruit: ["Mould, especially around the stem", "Leaking, mushy or collapsed spots", "Fermented or sour smell"]
        case .dairy: ["Sour smell or taste", "Lumps, separation or thick texture", "Mould on the surface"]
        case .grains: ["Fuzzy or coloured mould spots", "Stale, musty smell", "Hard, dry or damp texture"]
        case .pantry: ["Bulging, rusted or dented cans", "Stale, rancid or musty smell", "Moisture, clumps or bugs"]
        case .leftovers: ["Sour or off smell", "Slimy texture or visible mould", "More than 3 to 4 days in the fridge"]
        case .frozen: ["Heavy ice crystals or freezer burn", "Thawed and refrozen look", "Off smell after thawing"]
        case .other: ["Off or sour smell", "Mould or unusual texture", "Colour that looks wrong"]
        }
    }
}
