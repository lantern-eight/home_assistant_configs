# AI Agent Context — General Home Mobile Dashboard

This file provides context for AI coding agents working on this dashboard.
Read this before making changes. See `README.md` in this dashboard's directory for full
documentation.

## What This Is

A phone-first Home Assistant YAML dashboard with a per-account theme system.
Uses `type: sections` views, kiosk mode, and `card_mod` for all CSS theming.
5 styles x 8 palettes x light/dark/system mode x independent backgrounds,
selected per HA account.

## Identity Model

All per-user behavior keys off the logged-in account:

- **card_mod styles** receive a `user` variable (the account's display name;
  display names are set to match usernames). The theme macros take it as an
  argument: `theme_css(user, 'card')`. Any session that is neither account
  resolves to the primary account's theme (wall tablets, guests).
- **Card visibility** uses native `condition: user` with account ids. The ids
  are 32-hex values and flow through `entity_map.yaml`'s `ids` section like
  every other hex id — never hardcode a raw id in tracked YAML.
- **Only card_mod `style:` templates get `user`.** auto-entities filters,
  mushroom `secondary:`/`icon_color:` templates, and markdown content do NOT —
  in those contexts pass the account name as a literal argument (fine, since
  such cards sit inside per-account visibility blocks).
- The usernames themselves are redacted in tracked files as `<entity_n>` and the
  sync script's restore pass expands them on upload.

To add a per-account feature: create one helper per account (username
suffix). Prefer routing tap_actions through a script that resolves
`context.user_id` (see `script.theme_select` in `general_home_mobile.yaml`
for the pattern). Fall back to per-account `condition: user` blocks only
when the tile needs `more-info` with a static entity (see Common Mistakes).

## Architecture Constraints

These are hard constraints discovered through debugging — not preferences.

### card_mod must be card-level, not view-level

`type: sections` views in HA 2026.6 never pass the `hass` object to
view-level `card_mod`. All Jinja2 templates silently render to empty strings.
All theming lives in card-level `card_mod` blocks. The view-level anchor
(`&theme_view_style`) is a no-op kept so references don't break.

### Sensor states are capped at 255 characters

Any template sensor state exceeding 255 chars goes `unavailable`. Keep
sensor states short; if you need a long value, put it in a sensor
**attribute** (not capped) and read it via `state_attr()`. The theme system
is not subject to this cap — its CSS is rendered directly by card_mod
templates importing `general_home_theme.jinja`, and card_mod template
output has no length limit.

### card_mod load order matters

card_mod must load via `frontend.extra_module_url` in `configuration.yaml`,
not just as a Lovelace resource. Without this, cards that instantiate before
card_mod patches them are permanently unstyled for that page load. There is no
retry or delay-based fix.

### Entity IDs derive from sensor name, not unique_id

A sensor with `unique_id: foo_bar` but `name: "Foo Bar Something"` gets
entity ID `sensor.foo_bar_something`. The dashboard references the
name-derived entity ID. Don't assume the unique_id matches.

## File Roles

| File | What it does |
|------|-------------|
| `dashboard.yaml` | All views, YAML anchor definitions, `button_card_templates`, `streamline_templates`, card definitions |
| `general_home_theme.jinja` | Theme macro library: every palette/style value + the CSS-emitting macros (deployed to `custom_templates/`) |
| `sensors.yaml` | Non-theme sensors (conditional card manager, notification aggregator, room light switches) |
| `general_home_mobile.yaml` | HA package: helpers, REST sensor, command_line, shell_command, automations (deployed to `packages/`) |
| `registry_metadata.yaml` | Category and label definitions for helpers and automations (applied via sync script `-c`) |
| `card_order.js` | Sorts conditional cards by a sensor-driven priority so higher-severity items render first (deployed to `www/`, loaded via `extra_module_url`). Same cache-busting rule as `popup_history_fix.js` |
| `popup_history_fix.js` | Strips bubble-card popup hashes from browser history on navigation (deployed to `www/`, loaded via `extra_module_url`). Editing it is not enough to ship a change — bump the `?v=` on its `configuration.yaml` entry, or browsers keep the copy they cached for 31 days |
| `ha_config_additions.yaml` | Remaining HA config that can't go in a package (dashboard registration, secrets, frontend module) |
| `README.md` | Full public-facing documentation |

General-purpose sensors the dashboard merely consumes, do NOT belong in this
directory — they live in repo-root `packages/` and are synced to HA's
`packages/` directory by the same sync script. See the root `agents.md`.

## YAML Anchor System

Eight anchors defined at the top of `dashboard.yaml` control card theming:

| Anchor | Purpose |
|--------|---------|
| `&theme_card_style` | Full themed treatment — use on content cards |
| `&theme_chip_style` | Theme chrome without background/border — for severity-colored chips |
| `&theme_chrome_style` | Restrained treatment — use on navbar, popup shells |
| `&theme_exempt_style` | Strips all styling — use on headings, chips, titles |
| `&theme_exempt_sub_style` | Same as exempt but with smaller font — use on sub-section headings |
| `&theme_card_transparent` | Transparent, no border — use on wrapper cards |
| `&theme_button_style` | Strips only the themed shadow/blur — use on `button-card`, whose own `styles: card:` an `!important` rule would otherwise erase |
| `&theme_bg_card` | Background overlay — must be first card in every view |

To theme a new card: `card_mod: style: *theme_card_style`

## Reusing a Card Body

An anchor reuses a card verbatim. When two cards are the same shape but differ
in a few values, define the body once under the top-level
`streamline_templates:` key and instantiate it with
`type: custom:streamline-card` + `variables:`

For logic rather than shape, use `button_card_templates` inheritance: an
entry there can name its own `template:`, and button-card resolves the chain
recursively and deep-merges it.

The vacuum cards are an example of these.

The template anchors are thin wrappers — each imports
`general_home_theme.jinja` and calls `theme_css(user, kind)` (or
`view_background_css(user)` for `&theme_bg_card`). All values and CSS
structure live in the macro library; edit there, not in the anchors.

## Conditional Display System

Information is shown conditionally in two tiers — pick the one that fits
the detail level:

**Notification items** (header bar) — small, glanceable: a count, a
label, maybe a progress bar. Dots in the header expand into a list.
Use for things like counts, vacuum running, lights on.

**Conditional cards** — information-rich content that needs more space:
charts, entity lists, multi-sensor readouts.

Both tiers are visible on the Conditionals page
(`/general-home/conditionals`) as a combined view — **always shown,
even when inactive**. The Home view only shows active items; the
Conditionals page shows everything the system tracks so you can see
the full picture at a glance.

Every notification item in the `items` attribute has an `active` flag.
The Home view JS filters to `i.active`; the Conditionals page shows
all items unfiltered. Inactive items use `green` severity and show
their idle state (e.g. "0 Lightning Strikes", "Downstairs Vacuum").
One item list, two views — no duplication.

### Adding a notification item

1. Add the entity check to `sensor.dashboard_notifications` in
   `sensors.yaml` (both `state` and `items` attribute — they evaluate
   independently).
2. Assign severity: red (urgent/promoted), amber (warning), blue (info),
   green (normal)
3. If promoted: also add a `type: conditional` chip card in
   `dashboard.yaml` using `*theme_chip_style`
4. If it has progress: include `progress` (0-100) and optional
   `time_remaining` in the item dict

No card, no input_boolean — notification items appear in the header
automatically when their entity state is active.

5. The item must always be present in `items` with an `active` flag
   (true when triggered, false when idle). The Home view JS filters
   to active items; the Conditionals page shows everything. Use the
   item's severity when active, `green` when idle.

### Adding a conditional card

1. For **time-based** windows: add a `schedule.cond_<id>` in
   `general_home_mobile.yaml` with the active time range.
   For **state-based** triggers: use `input_boolean.cond_<id>` +
   on/off automations instead.
2. Add the card entry to `sensor.dashboard_conditional_visible` in
   `sensors.yaml` (state template)
3. Add the conditional card in the Home view of `dashboard.yaml`, gated
   on the schedule or input_boolean
4. Alias the card's anchor on the Conditionals page in `dashboard.yaml`
   (the card body is defined once on the Home view with a `&cond_card_*`
   anchor; Conditionals uses `*cond_card_*` — no copy needed)

### Severity colors

| Color | Hex | Meaning |
|-------|-----|---------|
| Red | `#ef6461` | Urgent/critical — doors open, security |
| Amber | `#e8a840` | Warning/attention — vacuum running |
| Blue | `#6b9fff` | Informational — lights on |
| Green | `#3ecf8e` | Normal/running — printer, HVAC, power |

### Key entities

- `sensor.dashboard_notifications` — aggregation sensor (state = count, attrs = items list)
- `input_boolean.notification_expanded_<username>` — per-user expand/collapse toggle
- `input_boolean.weather_expanded` — expand/collapse toggle for the weather card (shared, not per-user)
- `&theme_chip_style` — YAML anchor for promoted chip cards (theme chrome without bg/border)

## Entity Naming

Per-account helpers are suffixed with the account's username:
- `input_select.theme_mode_<username>` — Light / Dark / System
- `input_select.theme_style_<username>`
- `input_select.theme_palette_<username>`
- `input_text.theme_background_<username>`
- `input_number.theme_card_opacity_<username>` (-1 = follow style default)
- `input_number.theme_card_blur_<username>` (-1 = follow style default)

All theme values resolve through the macros in `general_home_theme.jinja`:
`theme_css(user, kind)` for card_mod blocks,
`view_background_css(user)` for the background card, and
`theme_value(account, prop)` for single values in non-card_mod templates.

## Deploy and Test Workflow

```bash
# Full sync: push all files, apply metadata, reload services, pull + redact
uv run python scripts/ha_sync.py

# Apply registry metadata only (labels + categories)
uv run python scripts/ha_sync.py -c

# Full sync + HA restart (for configuration.yaml / frontend changes)
uv run python scripts/ha_sync.py --restart
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

2. **Don't add theme values anywhere but the macro library.** Every
   palette/style value lives in the tables in `general_home_theme.jinja`
   — no duplicating them into sensors, anchors, or card styles. (For
   non-theme sensors, remember the 255-char state cap.)

3. **Don't template `entity_id` in `tap_action`.** HA doesn't support
   Jinja2 in tap_action fields. The Appearance page works around this by
   routing tap_actions through scripts (`script.theme_select`,
   `script.theme_set_background`, `script.theme_reset_customization`)
   that resolve `context.user_id` at runtime to target the correct
   per-user helper. Selection outlines use card_mod Jinja (which does
   get `user`). Sections that need `more-info` with a static entity
   (Opacity/Blur sliders, Custom color card, Palette shades) still use
   per-user `condition: user` blocks.

4. **Don't remove or reorder the background overlay card.** It must be the
   first card in each view's first section. It uses `position: fixed` with
   `z-index: -1` to paint the viewport background.

5. **Decide whether a helper should survive a restart, and say so with
   `initial:`.** A helper with `initial:` resets on every HA restart; one
   without it restores its last value. Neither is a safe default — pick by
   what the helper holds. State the user set (a room selection, a
   preference) should restore. State belonging to a running script must
   not: a script run cannot survive a restart, so a restored "sequence
   running" flag leaves a card driven by nothing, and any guard that reads
   the flag then gets an incorrect state.

6. **Don't use these HA API endpoints** (broken in 2026.6):
   - `POST /api/services/lovelace/reload` -> 400
   - `POST /api/lovelace/reload` -> 404

   Use the WebSocket `lovelace/config` call with `force: true` instead.

7. **Don't put a `phu:` icon anywhere Lovelace isn't the thing drawing it.**
   `custom-brand-icons` registers as `phu:` (not `cbi:`) and loads as a
   Lovelace resource, so it only exists inside the frontend. Card `icon:`
   keys, view icons and `<ha-icon>` in a button-card template are fine.
   Entity registry icons (helpers, template sensors in `packages/`),
   `notify` payloads and anything the companion app draws natively must
   stay on `mdi:` — they render blank otherwise. The vacuums use
   `phu:` on the Lovelace side and `mdi:` on the helpers for exactly this
   reason.

8. **Don't name a local after one of button-card's injected parameters.**
   Every `[[[ ... ]]]` template is compiled as a function taking `states`,
   `entity`, `user`, `hass`, `variables`, `html` and `helpers`. A
   `const entity = ...` inside one is a redeclaration, so the template
   throws at compile time — the field renders blank and the only sign is a
   console error.

9. **Don't mutate a memoised variable.** button-card evaluates each
   `variables:` entry once and hands the same object to every reader, so
   an in-place `.sort()` or `.splice()` on one holding an array reorders
   what the other cards on that entity see. Copy first.

## Style-Specific Notes

- **Neon intentionally breaks shared conventions.** It uses `Share Tech Mono`
  (Google Fonts), 4px radius (not 18px), and stays dark even in light mode.
  Don't "fix" these to match other styles.

- **Glow uses different blend modes per mode.** Dark: `screen` blend at
  opacity 1.0. Light: `multiply` blend at 0.85. Adjust glow alphas in the
  `palette_by_mode` table in `general_home_theme.jinja` if glow looks wrong.

- **Dark style in light mode shows white cards.** This is by design — "Dark"
  describes its dark-mode appearance. In light mode it renders as crisp
  white with subtle definition. (Style names and mode names are independent
  axes; "Dark" here is a style.)

## Privacy

Household names or personal information may appear in some entity IDs, HA account
usernames plus their 32-hex user ids are treated the same way: all of them
are redacted in tracked files (`<entity_N>` placeholders and short-form id
keys from `entity_map.yaml`). The backup sync script handles redaction
automatically; it must be run before committing (`-s` sanitize) and the
deploy scripts restore real values in memory on upload. Never write a raw
username, person name, or user id into tracked YAML, docs, or commits.
