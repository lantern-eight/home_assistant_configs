# AI Agent Context — General Home Mobile Dashboard

This file provides context for AI coding agents working on this dashboard.
Read this before making changes. See `README.md` in this dashboard's directory for full
documentation.

## What This Is

A phone-first Home Assistant YAML dashboard with a per-user theme system.
Uses `type: sections` views, kiosk mode, and `card_mod` for all CSS theming.
5 styles x 8 palettes x independent backgrounds, detected per-user via
`@media (prefers-color-scheme)`.

## Architecture Constraints

These are hard constraints discovered through debugging — not preferences.

### card_mod must be card-level, not view-level

`type: sections` views in HA 2026.6 never pass the `hass` object to
view-level `card_mod`. All Jinja2 templates silently render to empty strings.
All theming lives in card-level `card_mod` blocks. The view-level anchor
(`&theme_view_style`) is a no-op kept so references don't break.

### Sensor states are capped at 255 characters

Any template sensor state exceeding 255 chars goes `unavailable`. A full CSS
block with palette colors, borders, shadows, etc. far exceeds this. The theme
uses many small per-property sensors, each outputting a single CSS value:

```
sensor.theme_dark_primary         -> "#6a74d3"
sensor.theme_dark_card_background -> "rgba(30,30,30,0.95)"
sensor.theme_dark_card_border     -> "1px solid rgba(255,255,255,0.06)"
```

If you need a long value, put it in a sensor **attribute** (not capped) and
read it via `state_attr()`.

### card_mod load order matters

card_mod must load via `frontend.extra_module_url` in `configuration.yaml`,
not just as a Lovelace resource. Without this, cards that instantiate before
card_mod patches them are permanently unstyled for that page load. There is no
retry or delay-based fix.

### Entity IDs derive from sensor name, not unique_id

A sensor with `unique_id: theme_dark_lovelace_bg` but
`name: "Theme Dark Lovelace Background"` gets entity ID
`sensor.theme_dark_lovelace_background`. The dashboard references the
name-derived entity ID. Don't assume the unique_id matches.

## File Roles

| File | What it does |
|------|-------------|
| `dashboard.yaml` | All views, YAML anchor definitions, card definitions (~2850 lines) |
| `theme_sensors.yaml` | Per-property template sensors for dark/light users (~435 lines) |
| `sensors.yaml` | Non-theme sensors (conditional card manager, notification aggregator, room light switches) |
| `general_home_mobile.yaml` | HA package: helpers, REST sensor, command_line, shell_command, automations (deployed to `packages/`) |
| `registry_metadata.yaml` | Category and label definitions for helpers (applied via sync script `-c`) |
| `popup_history_fix.js` | Strips bubble-card popup hashes from browser history on navigation (deployed to `www/`, loaded via `extra_module_url`) |
| `ha_config_additions.yaml` | Remaining HA config that can't go in a package (dashboard registration, secrets, frontend module) |
| `README.md` | Full public-facing documentation |

## YAML Anchor System

Six anchors defined at the top of `dashboard.yaml` control card theming:

| Anchor | Purpose |
|--------|---------|
| `&theme_card_style` | Full themed treatment — use on content cards |
| `&theme_chip_style` | Theme chrome without background/border — for severity-colored chips |
| `&theme_chrome_style` | Restrained treatment — use on navbar, popup shells |
| `&theme_exempt_style` | Strips all styling — use on headings, chips, titles |
| `&theme_card_transparent` | Transparent, no border — use on wrapper cards |
| `&theme_bg_card` | Background overlay — must be first card in every view |

To theme a new card: `card_mod: style: *theme_card_style`

## Notification System

A two-tier status bar above the weather card. `sensor.dashboard_notifications`
aggregates all items; its `items` attribute drives the dot counter and expanded
list via button-card JS templates.

### Adding a new notification item

1. Add the entity check to `sensor.dashboard_notifications` in `sensors.yaml`
   (both `state` and `items` attribute — they evaluate independently)
2. Assign severity: red (urgent/promoted), amber (warning), blue (info),
   green (normal)
3. If promoted: also add a `type: conditional` chip card in `dashboard.yaml`
   using `*theme_chip_style`
4. If it has progress: include `progress` (0-100) and optional
   `time_remaining` in the item dict

### Severity colors

| Color | Hex | Meaning |
|-------|-----|---------|
| Red | `#ef6461` | Urgent/critical — doors open, security |
| Amber | `#e8a840` | Warning/attention — vacuum running |
| Blue | `#6b9fff` | Informational — lights on |
| Green | `#3ecf8e` | Normal/running — printer, HVAC, power |

### Key entities

- `sensor.dashboard_notifications` — aggregation sensor (state = count, attrs = items list)
- `input_boolean.notification_expanded` — expand/collapse toggle
- `&theme_chip_style` — YAML anchor for promoted chip cards (theme chrome without bg/border)

## Entity Naming

Per-user helpers follow this pattern:
- `input_select.theme_style_<user>`
- `input_select.theme_palette_<user>`
- `input_text.theme_background_<user>`
- `input_number.theme_card_opacity_<user>` (-1 = follow style default)
- `input_number.theme_card_blur_<user>` (-1 = follow style default)

Shared: `input_select.theme_appearance_user` (which user the Appearance
page edits).

Per-property sensors: `sensor.theme_{dark,light}_{property}`
Properties: primary, accent, state_on, state_off, success, warning, error,
info, glow_1, glow_2, glow_3, glow_active, lovelace_background,
card_background, card_border, card_shadow, card_opacity, card_blur,
card_radius, card_font.

## Deploy and Test Workflow

```bash
# Deploy dashboard + sensors + scripts, reload templates
uv run python scripts/general_home_dashboard_sync.py

# Deploy + apply categories and labels to helpers
uv run python scripts/general_home_dashboard_sync.py -c

# Deploy + full HA restart (for configuration.yaml / frontend changes)
uv run python scripts/general_home_dashboard_sync.py -r
```

After deploying sensor changes: run `template/reload` (Developer Tools >
YAML > Template Entities).

After deploying dashboard.yaml changes: force-refresh Lovelace in the
browser console:
```js
document.querySelector('home-assistant').hass.callWS({
  type: 'lovelace/config', url_path: 'general-home', force: true
});
```
Then reload the page.

## Common Mistakes to Avoid

1. **Don't put theming at the view level.** It silently fails on sections
   views. Use card-level `card_mod` only.

2. **Don't build one big CSS sensor.** It will exceed 255 chars and go
   `unavailable`. One sensor per CSS property.

3. **Don't template `entity_id` in `tap_action`.** HA doesn't support
   Jinja2 in tap_action entity_id fields. This is why the Appearance page
   has duplicate picker sections per user (~350 lines of near-duplicate
   YAML). If you add a style or palette, add the tile in both user blocks.

4. **Don't remove or reorder the background overlay card.** It must be the
   first card in each view's first section. It uses `position: fixed` with
   `z-index: -1` to paint the viewport background.

5. **Don't use `initial:` on helpers if you want persistence.** Helpers
   with `initial:` reset on every HA restart. Remove it to keep the
   last-set value.

6. **Don't use these HA API endpoints** (broken in 2026.6):
   - `POST /api/services/lovelace/reload` -> 400
   - `POST /api/lovelace/reload` -> 404

   Use the WebSocket `lovelace/config` call with `force: true` instead.

## Style-Specific Notes

- **Neon intentionally breaks shared conventions.** It uses `Share Tech Mono`
  (Google Fonts), 4px radius (not 18px), and stays dark even in light mode.
  Don't "fix" these to match other styles.

- **Glow uses different blend modes per scheme.** Dark mode: `screen` blend
  at opacity 1.0. Light mode: `multiply` blend at opacity 0.85. Adjust
  glow alpha values in `theme_sensors.yaml` if glow looks wrong.

- **Dark style in light mode shows white cards.** This is by design — "Dark"
  describes its dark-mode appearance. In light mode it renders as crisp
  white with subtle definition.

## Privacy

Real household names appear in entity IDs. In documentation, commits, and public-facing
content, the backup sync script handles redaction automatically, it must be run before
committing, `-s sanitize`, restore real values before pushing to Home Assistant,
`-r restore`.
