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
| `scrim` | `#4C5A4F` | Behind sheets. The mockups show it solid; on device it is `ink` at 60% (light) or black at 60% (dark). See the dark table |
| `chartSaved` | `#277338` | Chart: used + donated |
| `chartWasted` | `#E8A04C` | Chart: thrown out, waste-reason bars |

### Dark mode
Every token above is **adaptive**. `Theme.swift` resolves each one per trait collection, so a view
never branches on color scheme. In dark mode the brand flips: **the lime family is the action
color**, and forest becomes the deep ground. That's why the `forest` token is light lime in dark,
and its `onForest` text turns dark.

| Token | Light | Dark |
|---|---|---|
| `ground` | `#F4F8E8` | `#0F1A12` |
| `surface` | `#FFFFFF` | `#18261B` |
| `lime` | `#D9EC8F` | `#D9EC8F` |
| `limeTint` | `#EEF5D6` | `#24361F` |
| `track` | `#E3EDCB` | `#223024` |
| `hairline` | `#E6EDD6` | `#2A3A2D` |
| `border` | `#D3E0BF` | `#34483A` |
| `forest` (primary action, active tab) | `#1F4D2B` | `#B9D871` |
| `forestMid` | `#3B7046` | `#8FB45A` |
| `forestChip` | `#2F6B3C` | `#2C4A26` |
| `ink` | `#13261A` | `#E8F0DA` |
| `inkSecondary` | `#2B3D30` | `#C9D6BC` |
| `muted` | `#45584A` | `#9DB09F` |
| `tabInactive` | `#5C6E5F` | `#8FA391` |
| `onForest` | `#F4F8E8` | `#13261A` |
| `onForestMuted` | `#C9D8BE` | `#2F4A2A` |
| `urgentBg` / `urgentInk` | `#FBE3CF` / `#8A3B0E` | `#4A2614` / `#FFB98A` |
| `noteYellow` / `noteLime` | `#FFF6C7` / `#E4F2C4` | `#3A3720` / `#2A3A1F` |
| `chartSaved` / `chartWasted` | `#277338` / `#E8A04C` | `#24783D` / `#C6802F` |
| `useSoonBg` / `useSoonInk` | `#FFF1B8` / `#6B5000` | `#3A3112` / `#FFD970` |
| `scrim` (behind sheets) | `#13261A` at 60% | `#000000` at 60% |

The dark scrim is black, not dark `ink`: a light-ink scrim would *brighten* the content behind a
sheet in dark mode. This is the one place pure black is allowed.

Dark contrast was computed, not eyeballed. Ink on ground is 15.2:1. Muted on surface is 6.9:1.
Tab-inactive on surface is 5.9:1. Forest on surface is 9.9:1. onForest on forest is 9.9:1. Urgent
is 8.0:1. The lowest pair is muted on a yellow note, at 5.2:1. The dark chart pair passes every
colorblind validator check against a dark surface: lightness band 0.48-0.67, protan ΔE 9.2, and
3:1 against the surface.

### Tab bar on iOS 26 (Liquid Glass): decided 2026-10-10
**The owner chose the native glass tab bar.** Use the system `TabView`, which renders as the
floating glass bar, with `Theme.Colors.forest` as its tint (adaptive). There are five tabs, in
this order: Home, Recipes, **Add**, Fridge, Social. **Add is a regular tab item** with a filled
circle-plus symbol (`plus.circle.fill`). Selecting it presents the Add sheet and leaves the
selected tab unchanged. **No raised custom button.** The mockups show the bar as a floating pill
with a tinted selection capsule, which approximates the system rendering. Build it with the real
`TabView`, not a recreation.

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
- **Radius:** chips and badges 10 · inputs 12 · controls 14 (secondary and Google buttons, inline
  controls, as drawn on the artboards) · rows and cards 16 · large option tiles 18 (Add sheet,
  barcode result, recipe cards) · hero cards 20 · sheets 28 (top corners) · Add button and icon
  buttons fully round. `Theme.Radius` mirrors this list.
- **Touch targets** are at least 44 pt. Primary buttons are 56 pt tall and removal options are
  68 pt.
- **Tab bar:** the system glass `TabView`. Add is a tab, so there's no custom size.

## Motion
Tokens `Theme.Motion.quick / standard / emphasized`, plus a 40 ms stagger capped at 6 items (MOTION.md), and shimmer for skeletons. Per-screen behaviour, haptics and the Reduce Motion fallbacks are in [`MOTION.md`](MOTION.md).

## Components
| Component | Seen in | Notes |
|---|---|---|
| `ItemRow` | Home, Fridge | 40 pt **food-group icon** tile in the group's colours (see Food-group colours) + name + meta + `ExpiryBadge`; swipe action `Remove` on `forest` |
| `FoodGroupSection` | Fridge | The Fridge list is **grouped by food group** (Protein, Veggies, Fruit, Dairy, Grains, Pantry, Leftovers, Frozen, Other). The header has the group icon, name and count, and rows within a group are sorted by expiry. Storage (Fridge / Pantry / Freezer) stays the segmented control above |
| `QuantityStepper` | Photo review | `limeTint` pill: − / value with unit / +. 40 pt tall, with a 44 pt hit target via `contentShape`. The value shows the unit ("1.4 lb", "1 bag", "12") |
| `MacroStrip` | Recipes hero | Four equal cells (kcal, protein, carbs, fat) **per serving**, labelled as estimates in the recipe detail. Rows show "kcal · protein" in their meta line |
| `GoogleSignInButton` | Sign in, Sign up, Log in | The official Google button, 50 pt. See `README.md` › Sign-in. There is no Apple button |
| `FormField` | Sign up, Log in | Label above (14 / semibold), a 50 pt field with a `border` hairline, focus ring 2 pt `forest`, error ring 2 pt `urgentInk` with an icon and message below (`role=alert`) |
| `ValuePoints` | Sign in | A card of three icon + title + one-line rows between the headline and the buttons |
| `ExpiryBadge` | Home, Fridge | Today / 1 day use `urgent`; 2+ days use `limeTint`/`forest` |
| `SpoilageFlag` | Fridge | Meta line in `urgentInk`: "Photo check: looks spoiled" |
| `StorageSegmented` | Fridge | Fridge / Pantry / Freezer |
| `RemoveSheet` | Remove | 3 outcome tiles. *Used it* is filled forest; the others are outlined |
| `WasteReasonGrid` | Remove | 2×2 one-tap tiles: Expired, Forgot about it, Didn't like it, Other |
| `AddSheet` | Add | Hero tile (fridge photo) + 2×2 tiles (one item, type/say, barcode, receipt) |
| `PantryWidget` | Social | `lime` card, collapsed chips preview, expands in place |
| `RequestNote` | Social | Sticky note: source header, text, who/when, "I have it" |
| `DetectedItemRow` | Photo review | Checkbox (44 pt row) + name + category/storage or a warning meta line + `ExpiryBadge` |
| `FilterChip` | Recipes | 36 pt pill. Selected uses `forest`/`onForest`; unselected is outlined |
| `RecipeHero`, `RecipeRow` | Recipes, Home | Hero on `forest` with expiring-item chips (`forestChip`); rows with a "Uses N" badge |
| `UseSoonBadge` | Fridge, Photo review | Shown when `freshness == semi_fresh` (ripe or starting to turn). Pill with `useSoonBg`/`useSoonInk`: 6.7:1 light, 9.5:1 dark. Text is "Use soon". It's distinct from the expiry badges and from the urgent "Check" (spoiled). In photo review the meta line reads "ripe, use soon" in `useSoonInk` |
| `StatTile`, `ImpactHero` | Impact | Hero on forest; tiles on surface |
| `WeeklyChart`, `ReasonBars` | Impact | Swift Charts; colors `chartSaved` / `chartWasted` |
| `TabBar` | all tabs | Home, Recipes, [+], Fridge, Social |

**Food-group colours** (owner request: icons are colourful, one colour per group). The tile is the
fill behind the icon and the stroke is the icon colour. Every stroke clears the 3:1 non-text
contrast minimum against its tile: light mode 3.98:1 at worst, dark 7.39:1 at worst. The group
name always appears beside the icon, so colour is never the only cue.

| Group | Light stroke / tile | Dark stroke / tile |
|---|---|---|
| Protein | `#B0412E` / `#FBE4DE` | `#FF9E8A` / `#3D1F1A` |
| Veggies | `#2F7A3A` / `#E2F1D8` | `#8FD69A` / `#1C3320` |
| Fruit | `#A8366E` / `#F8E1EC` | `#F59AC6` / `#3A1C2B` |
| Dairy | `#3A5BA0` / `#E2E9F7` | `#9DB7F0` / `#1C2540` |
| Grains | `#8A6414` / `#F5EBCD` | `#E8C46A` / `#33290F` |
| Pantry | `#6A4FA3` / `#ECE5F7` | `#C1AAF0` / `#2A2140` |
| Leftovers | `#1F7A78` / `#DAF0EE` | `#7FD8D3` / `#14302F` |
| Frozen | `#1E7BA8` / `#DCEFF8` | `#86CBEE` / `#122C3A` |
| Other | `#5C6E5F` / `#EAEFE6` | `#B4C2B6` / `#243026` |

In `Theme.swift` these go in `Theme.FoodGroup.<group>.stroke` / `.tile`, both adaptive. They are
**only** for food-group identity. Never reuse them for status, which is the urgent tokens, or for
charts.

**Food-group icons** (stroke style, matching the mockups; use the closest SF Symbol, or ship these as
template assets if SF has no match):

| Group | Mockup glyph | SF Symbol candidate |
|---|---|---|
| Protein | drumstick | `fork.knife` (no drumstick in SF), so ship the mockup glyph as an asset |
| Veggies | carrot | `carrot` |
| Fruit | apple | `apple.logo` must NOT be used (it's a trademark), so ship the mockup glyph as an asset |
| Dairy | milk carton | `waterbottle` is not a match, so ship the mockup glyph as an asset |
| Grains | bread loaf: `M5 11a4 4 0 0 1 1-7h12a4 4 0 0 1 1 7v9H5zM9 11v5M15 11v5` (see `FoodPantry`) | ship as an asset |
| Pantry / Leftovers / Frozen / Other | jar `M8 3h8v3H8zM7 6h10a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zM6 11h12` / box `M4 10h16v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zM3 10h18M9 6l3-3 3 3` / snowflake / circle | an asset / `takeoutbag.and.cup.and.straw` / `snowflake` / `circle.grid.2x2` |

Never emoji.

**Icons:** use SF Symbols on iOS, with stroke-style equivalents of the mockup glyphs (`house`,
`frying.pan`, `plus`, `refrigerator`, `person.2`, `camera`, `barcode.viewfinder`, `doc.text`,
`mic`, `checkmark`, `gift`, `trash`, `leaf`). No emoji.
