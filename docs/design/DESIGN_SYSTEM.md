# Design system

**Draft from the brief — replaced by the Design agent's values once screens are approved.**
`ios/App/Theme.swift` mirrors this file; change both together. Views never use ad-hoc values.

## Color
| Token | Role | Draft value |
|---|---|---|
| `primaryLight` | Main surface accent — light green-yellow | `#DBED9E` |
| `primaryDeep` | Contrast, buttons, active tab — deep green | `#29663A` |
| `onPrimaryDeep` | Text/icons on `primaryDeep` | `#FFFFFF` |
| `saved` | "Used / donated" in charts and badges | TBD |
| `wasted` | "Thrown out" in charts and badges | TBD |
| `warning` | Expiring soon | TBD |

## Type scale
TBD by the Design agent (SF Pro / system font; map to SwiftUI text styles so Dynamic Type works).

## Spacing & radius
Spacing: 4 · 8 · 16 · 24 · 32. Radius: card 16, button 12.

## Components
Item row (swipe-to-remove), removal sheet, add-options sheet, expiry badge, Food Pantry widget,
sticky-note request card, impact stat tile, weekly trend chart, primary/secondary buttons.
