# Design tokens in Qt

Overmark's own chrome (toolbar pill and handle, cheat-sheet, settings window, recording chip, tray menu, tray icon) follows the fleet design system: `design.md` (light) and `design.dark.md` (dark). The system is written for web apps (CSS custom properties, PWA shell, bottom-tab nav), so this file records how it maps onto a Qt desktop app. The ink palette, stroke widths and outlines are not chrome and are not covered here: they are tuned to survive video compression.

`src/overmark/theme.py` is the one token module. No other chrome module holds a colour literal; `tests/test_design_tokens.py` fails if one appears, if light and dark ever define different token sets, if a glyph the UI uses stops rendering, or if the tray icon loses its brand tile or its keep-awake badge.

## Why the fleet design checks don't run here

- The design-sync lint reads CSS custom properties and vendored web components. Overmark has no CSS, so the lint reports every token as missing; that says nothing about drift. In its place, the values in `theme.LIGHT` and `theme.DARK` were compared one by one with the hex tokens in both spec files, and they match.
- The design review drives a running web app in a browser. A Qt window can't be loaded that way. Surfaces were checked by eye from local renders of each one in light and dark.

## Colours

`theme.LIGHT` and `theme.DARK` use the spec's token names with `_` for `-`. The spec's `color-mix()` tints become rgba at the same percentage (16% is alpha 41, 24% is 61, 28% is 71).

| Spec token | Qt use |
|---|---|
| `card` | toolbar pill, cheat-sheet, recording chip, settings groups, tooltips |
| `border` | the hairline round the pill, cheat-sheet and chip; ghost-button border |
| `border-muted` | menu separator; dark control fill |
| `canvas-subtle` | light control fill; tray-menu surface (row-menu); disabled button |
| `settings_canvas` | the settings window's page: light is 8% `fg` over `card`, dark is `canvas` (as the vendored settings-group does) |
| `fg` / `fg-muted` | text and secondary text; icon glyph on hover / at rest |
| `accent` | focus ring, selected-swatch ring |
| `accent-fill` + `accent-fg` | Save button, the Draw toggle while drawing |
| `accent-soft` + `accent-text` (+ `accent-border-soft`) | selected tool, selected settings tab, menu hover, combo selection |
| `accent-border-strong` | the primary button's hairline |
| `control-border` | input boundaries, swatch rim, scrollbar handle |
| `danger` / `danger-text` | the recording dot / the settings error line |

## Type, spacing, shapes

| Spec | Qt |
|---|---|
| `body-sm`, `label` (14px, 400 / 600) | default text, button and tab labels, the chip |
| `body` (16px / 700) | settings group label (`settings-group.label*`) |
| `heading-md` (20px / 700) | cheat-sheet title |
| `spacing` xs 4 / sm 8 / md 16 / lg 24, gutter 12 | `SPACE_*`, `GUTTER` |
| `rounded` sm 8 / md 12 / lg 16, settings group 20 | `RADIUS_*` |
| `control.height` 36 | inputs, buttons, the recording chip |
| `hit-target.min` 44 | every toolbar control and swatch |

The font is Segoe UI, Windows' `system-ui` face.

## Icons

Lucide, 24×24 on a 2px stroke. `src/overmark/_vendored/icons/icons-sprite.html` is the sprite from project-scaffolding's icon component, vendored byte-for-byte and pinned in `.fleet.toml` `[vendored]`. Only the sprite is vendored: the component's JS helper is web-only, and its README names upstream accounts, which this public repo keeps out. `glyphs.py` reads its sprite; `icons.py` renders a glyph to a `QIcon` whose modes carry the icon-button states (rest `fg-muted`, hover `fg`, checked `accent-text`), so the button itself stays unpainted. Three drawing-tool glyphs the shared sprite lacks (`highlighter`, `arrow-up-right`, `type`) live in `glyphs.EXTRA` until the sprite carries them. Sizes follow `icons.size`: 16 inline (tray menu, Browse), 18 title (settings tabs), 20 for the toolbar's standalone controls.

## Tray icon

The fleet brand tile (project-scaffolding `brand_gen`): the Lucide `pencil` master stroked `#F0F0F0` at 2.6px on a `#0A0A0A` square with 12% padding. It is the same in either theme, so the identity never flips. Overmark renders it at runtime rather than loading a generated `.ico`, because it carries live state: keep-awake armed adds a dark-theme `success` badge in the bottom-right corner, ringed in the tile colour.

## Where Overmark differs from the web contract

- **Theme follows Windows.** The web contract asks for an in-app light/dark toggle; Overmark follows the system scheme and restyles live when it changes. A desktop overlay has no main view to host the toggle.
- **No bottom nav, page header or text-size setting.** These are PWA-shell contracts; Overmark's surfaces are a toolbar, a tray and one dialog.
- **The settings window stays a dialog** with Save and Cancel, using the settings-group look (sunk page, borderless 20px groups, label above). The spec's full-page, save-as-you-change Settings is a web pattern.
- **Native widgets where Qt draws them**: checkbox indicators, spin-box arrows and the tray menu's outer corners (Qt can't round a native popup's frame).
