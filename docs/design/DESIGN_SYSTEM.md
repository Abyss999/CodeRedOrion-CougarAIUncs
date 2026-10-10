# Design system

The source of truth for every color, type and spacing value. `ios/App/Theme.swift` mirrors this
file, so change both together. Views never use ad-hoc values. These values come from the screens
in [`screens/`](screens/) and are **awaiting team approval** (see `README.md`).

## Color
| Token | Hex | Use |
|---|---|---|
| `ground` | `#F4F8E8` | App background (pale green-yellow) |
| `surface` | `#FFFFFF` | Lists, cards, sheets' option tiles, tab bar |
| `lime` | `#D9EC8F` | The light green-yellow brand color: highlights, Food Pantry widget, icon on deep green |
| `limeTint` | `#EEF5D6` | Item avatars, "later" expiry badges, info callouts |
| `track` | `#E3EDCB` | Segmented-control track |
| `hairline` | `#E6EDD6` | Row dividers |
| `border` | `#D3E0BF` | Outlined tiles, inputs |
| `forest` | `#1F4D2B` | Primary: buttons, active tab, hero cards |
| `forestMid` | `#3B7046` | Secondary filled button (Log in) |
| `forestChip` | `#2F6B3C` | Icon chip on a forest surface |
| `ink` | `#13261A` | Primary text (never pure black) |
| `inkSecondary` | `#2B3D30` | Body text on tinted surfaces |
| `muted` | `#45584A` | Secondary text (7.1:1 on ground) |
| `tabInactive` | `#5C6E5F` | Inactive tab icons/labels (5.4:1 on white) |
| `onForest` | `#F4F8E8` | Text on forest (9.0:1) |
| `onForestMuted` | `#C9D8BE` | Secondary text on forest (6.5:1) |
| `urgentBg` / `urgentInk` | `#FBE3CF` / `#8A3B0E` | Expires today/tomorrow, spoilage flag (6.3:1) |
| `noteYellow` / `noteLime` | `#FFF6C7` / `#E4F2C4` | Request sticky notes |
| `scrim` | `#4C5A4F` | Behind sheets (mockups show it solid; use ~60% `ink` on device) |
| `chartSaved` | `#277338` | Chart: used + donated |
| `chartWasted` | `#E8A04C` | Chart: thrown out, waste-reason bars |

Every text pair above passes WCAG AA, and the ratios were computed rather than eyeballed. The chart pair passes the
colorblind (protan/deutan/tritan) separation check. `chartWasted` is only 2.1:1 against white, so
chart values are always labeled.

## Type
- **Display: Outfit** (Google Fonts, OFL), weights 500/600. Used for screen titles, section
  headings, big numbers and button labels. Bundle it in the app and register it with
  `.custom("Outfit", size:, relativeTo:)` so Dynamic Type still scales it.
- **Body: SF Pro** (system). Used for everything else.

| Style | Font | Size / weight | SwiftUI `relativeTo` |
|---|---|---|---|
| Hero number | Outfit | 48 / 600, tracking -2% | `.largeTitle` |
| Sign-in headline | Outfit | 44 / 600 | `.largeTitle` |
| Screen title | Outfit | 30 / 600 | `.largeTitle` |
| Sheet title | Outfit | 22-24 / 600 | `.title2` |
| Section heading | Outfit | 20 / 600 | `.title3` |
| Card heading | Outfit | 17 / 600 | `.headline` |
| Button | Outfit | 17 / 600 | `.headline` |
| Row title | SF Pro | 16 / semibold | `.callout` |
| Body | SF Pro | 15-17 / regular | `.body` |
| Meta / caption | SF Pro | 13 / regular | `.footnote` |
| Badge | SF Pro | 13 / semibold | `.footnote` |
| Tab label | SF Pro | 10 / medium (active semibold) | `.caption2` |

## Spacing, radius, size
- **Spacing:** 4 · 8 · 12 · 16 · 20 · 24 · 32. The screen gutter is 20.
- **Radius:** chips and badges 10 · inputs 12 · rows, cards and option tiles 16 · hero cards
  20 · sheets 28 (top corners) · Add button and icon buttons fully round.
- **Touch targets** are at least 44 pt. Primary buttons are 56 pt tall and removal options are
  68 pt.
- **Tab bar:** 84 pt including the home indicator. The raised Add button is 60 pt.

## Components
| Component | Seen in | Notes |
|---|---|---|
| `ItemRow` | Home, Fridge | 40 pt initial avatar (`limeTint`) + name + meta + `ExpiryBadge`; swipe action `Remove` on `forest` |
| `ExpiryBadge` | Home, Fridge | Today / 1 day use `urgent`; 2+ days use `limeTint`/`forest` |
| `SpoilageFlag` | Fridge | Meta line in `urgentInk`: "Photo check: looks spoiled" |
| `StorageSegmented` | Fridge | Fridge / Pantry / Freezer |
| `RemoveSheet` | Remove | 3 outcome tiles. *Used it* is filled forest; the others are outlined |
| `WasteReasonGrid` | Remove | 2×2 one-tap tiles: Expired, Forgot about it, Didn't like it, Other |
| `AddSheet` | Add | Hero tile (fridge photo) + 2×2 tiles (one item, type/say, barcode, receipt) |
| `PantryWidget` | Social | `lime` card, collapsed chips preview, expands in place |
| `RequestNote` | Social | Sticky note: source header, text, who/when, "I have it" |
| `StatTile`, `ImpactHero` | Impact | Hero on forest; tiles on surface |
| `WeeklyChart`, `ReasonBars` | Impact | Swift Charts; colors `chartSaved` / `chartWasted` |
| `TabBar` | all tabs | Home, Recipes, [+], Fridge, Social |

**Icons:** use SF Symbols on iOS, with stroke-style equivalents of the mockup glyphs (`house`,
`frying.pan`, `plus`, `refrigerator`, `person.2`, `camera`, `barcode.viewfinder`, `doc.text`,
`mic`, `checkmark`, `gift`, `trash`, `leaf`). No emoji.
