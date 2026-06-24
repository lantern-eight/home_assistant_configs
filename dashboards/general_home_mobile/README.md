# General Home Mobile Dashboard

A phone-first Home Assistant dashboard with a built-in per-user theme system.
Runs in kiosk mode (no HA header or sidebar) and uses `type: sections` views
with a single-column layout optimized for mobile screens.

The theme system supports 5 visual styles, 8 color palettes, custom
backgrounds, and per-card opacity/blur controls. Each household member gets
their own independent theme preferences, detected automatically via the
device's light/dark mode setting.

**HA version tested:** 2026.6.3
**Dashboard mode:** YAML (`mode: yaml`)
**Global theme:** Material You (unchanged — all theming is dashboard-scoped via
card_mod)

---

## Screenshots

### Dark mode

| Clean | Glass | Glow | Cyber Neon |
|:-:|:-:|:-:|:-:|
| ![Clean](images/style_clean_dark.png) | ![Glass](images/style_glass_dark.png) | ![Glow](images/style_glow_dark.png) | ![Neon](images/style_neon_dark.png) |

### Light mode

| Clean | Glass | Glow |
|:-:|:-:|:-:|
| ![Clean](images/clean_light.png) | ![Glass](images/glass_light.png) | ![Glow](images/glow_light.png) |

---

## Table of Contents

- [Screenshots](#screenshots)
- [Views and Navigation](#views-and-navigation)
- [Required HACS Integrations](#required-hacs-integrations)
- [Setup](#setup)
  - [Dashboard Registration](#1-dashboard-registration)
  - [HACS Cards](#2-hacs-cards)
  - [card_mod Load Order Fix](#3-card_mod-load-order-fix)
  - [Theme Helpers](#4-theme-helpers)
  - [Template Sensors](#5-template-sensors)
  - [Background Image Pipeline](#6-background-image-pipeline)
  - [Conditional Card Helpers](#7-conditional-card-helpers)
  - [REST Sensor (UV Forecast)](#8-rest-sensor-uv-forecast)
  - [Kiosk Mode](#9-kiosk-mode)
- [Theme System](#theme-system)
  - [How Per-User Detection Works](#how-per-user-detection-works)
  - [Three Customization Axes](#three-customization-axes)
  - [Styles](#styles)
  - [Palettes](#palettes)
  - [Backgrounds](#backgrounds)
  - [Card Opacity and Blur](#card-opacity-and-blur)
  - [Appearance Subview](#appearance-subview)
- [Architecture](#architecture)
  - [Why Card-Level, Not View-Level](#why-card-level-not-view-level)
  - [Per-Property Sensors, Not One Big CSS Sensor](#per-property-sensors-not-one-big-css-sensor)
  - [YAML Anchors and Card Tiering](#yaml-anchors-and-card-tiering)
  - [Background Overlay Card](#background-overlay-card)
  - [Duplicate Picker Sections](#duplicate-picker-sections)
- [Deployment](#deployment)
- [Gotchas](#gotchas)
- [File Inventory](#file-inventory)

---

## Views and Navigation

The dashboard has 6 views. The bottom navbar (Material Design 3 style via
`navbar-card`) shows 5 tabs: Home, Rooms, Climate, Security, and More. Rooms
and More open as bubble-card popups rather than navigating to separate views.

| View | Path | Type | Access |
|------|------|------|--------|
| **Home** | `/general-home/home` | Main view | Navbar tab |
| **Climate** | `/general-home/climate` | Subview | Navbar tab |
| **Security** | `/general-home/security` | Subview | Navbar tab |
| **All Alerts** | `/general-home/all-alerts` | Subview | More popup |
| **Appearance** | `/general-home/appearance` | Subview | More popup |
| **Automations** | `/general-home/automations` | Subview | More popup |

**Home view contents** (top to bottom):
- Background overlay card (invisible, paints the viewport background)
- Clock/weather card (`clock-weather-card`)
- Absolute humidity graph (`mini-graph-card`)
- UV index chart (`apexcharts-card`, conditional — daytime only)
- Air quality indicators (humidity, CO2, chemicals, PM2.5, radon)
- Calendar (`calendar-card-pro`)
- Conditional cards (bedtime door status, UV alerts — priority-managed)
- Bottom navbar

**Rooms popup:** Room cards with light toggles. Uses template switches that
aggregate all lights in an HA area (excluding presence-detection LEDs).

**More popup:** Navigation links to Appearance, All Alerts, Automations,
3D Printer Farm (links to the Cyberdeck dashboard), and core HA UI.

---

## Required HACS Integrations

Install all of these via HACS before setting up the dashboard:

| Integration | Purpose |
|-------------|---------|
| **card-mod** | CSS injection for all theme styling |
| **bubble-card** | Popup cards for Rooms and More |
| **mushroom** | Template cards, entity cards, chips, title cards |
| **stack-in-card** | Card grouping with unified styling |
| **mini-graph-card** | Sparkline graphs (humidity) |
| **apexcharts-card** | UV index chart |
| **clock-weather-card** | Combined clock/weather display |
| **calendar-card-pro** | Calendar view |
| **navbar-card** | Bottom navigation bar |
| **auto-entities** | Dynamic card generation (background picker) |
| **material-you-utilities** | Material You theme support |
| **kiosk-mode** | Hide HA header and sidebar |

---

## Setup

### 1. Dashboard Registration

Add to your `configuration.yaml` under the `lovelace:` block:

```yaml
lovelace:
  mode: storage        # keep your existing mode
  dashboards:
    general-home:
      mode: yaml
      title: Home
      icon: mdi:home
      show_in_sidebar: true
      filename: dashboards/general_home_mobile/dashboard.yaml
```

### 2. HACS Cards

Install all cards listed in [Required HACS Integrations](#required-hacs-integrations).
Most install via HACS as Lovelace resources. Restart HA after installing.

### 3. card_mod Load Order Fix

**This is critical.** Without this, card_mod will intermittently fail to style
cards (the calendar, navbar, and background card are especially affected).

Add to `configuration.yaml`:

```yaml
frontend:
  themes: !include_dir_merge_named themes
  extra_module_url:
    - /hacsfiles/lovelace-card-mod/card-mod.js
```

This loads card_mod during frontend bootstrap, before any cards render. Without
it, card_mod loads as a Lovelace resource in parallel with card rendering, and
any card class that instantiates before card_mod patches it will be permanently
unstyled for that page load.

**Requires an HA restart** (frontend config is read at startup only).

### 4. Theme Helpers

Create these helpers in `configuration.yaml`. You need one set per user.
Replace `<user1>` and `<user2>` with your household members' names. `<user1>`
should be the person who uses dark mode; `<user2>` should be the light mode
user. Not yet figured out a good way to automatically detect the user so for now
it uses the setting of the browser's light/dark mode setting to determine the user.

```yaml
input_select:
  theme_appearance_user:
    name: "Theme Appearance User"
    options:
      - "<user2>"
      - "<user1>"
    initial: "<user2>"
    icon: mdi:account-switch

  theme_style_<user1>:
    name: "Theme Style (<user1>)"
    options: [Clean, Glass, Dark, Glow, Neon]
    initial: Clean
    icon: mdi:palette-swatch-variant
  theme_style_<user2>:
    name: "Theme Style (<user2>)"
    options: [Clean, Glass, Dark, Glow, Neon]
    initial: Clean
    icon: mdi:palette-swatch-variant

  theme_palette_<user1>:
    name: "Theme Palette (<user1>)"
    options: [Indigo, Ocean, Sunset, Forest, Rose, Mono, Cyberdeck, Mint]
    initial: Indigo
    icon: mdi:palette
  theme_palette_<user2>:
    name: "Theme Palette (<user2>)"
    options: [Indigo, Ocean, Sunset, Forest, Rose, Mono, Cyberdeck, Mint]
    initial: Indigo
    icon: mdi:palette

input_text:
  theme_background_<user1>:
    name: "Theme Background (<user1>)"
    initial: "auto"
    max: 255
    icon: mdi:image
  theme_background_<user2>:
    name: "Theme Background (<user2>)"
    initial: "auto"
    max: 255
    icon: mdi:image

input_number:
  theme_card_opacity_<user1>:
    name: "Card Opacity (<user1>)"
    min: -1
    max: 100
    step: 5
    initial: -1
    icon: mdi:opacity
    unit_of_measurement: "%"
    mode: slider
  theme_card_opacity_<user2>:
    name: "Card Opacity (<user2>)"
    min: -1
    max: 100
    step: 5
    initial: -1
    icon: mdi:opacity
    unit_of_measurement: "%"
    mode: slider
  theme_card_blur_<user1>:
    name: "Card Blur (<user1>)"
    min: -1
    max: 30
    step: 1
    initial: -1
    icon: mdi:blur
    unit_of_measurement: "px"
    mode: slider
  theme_card_blur_<user2>:
    name: "Card Blur (<user2>)"
    min: -1
    max: 30
    step: 1
    initial: -1
    icon: mdi:blur
    unit_of_measurement: "px"
    mode: slider
```

> **Note on `initial:`** — helpers defined with `initial:` reset to that value
> on every HA restart. If you want theme preferences to persist across
> restarts, **remove the `initial:` lines** (HA will restore the last-set
> value instead).

### 5. Template Sensors

Two sensor files need to be placed in your HA template sensors directory:

| Repo file | Deploy to |
|-----------|-----------|
| `sensors.yaml` | `template_sensors/general_home_sensors.yaml` |
| `theme_sensors.yaml` | `template_sensors/theme_sensors.yaml` |

Your `configuration.yaml` should include:
```yaml
template: !include_dir_merge_list template_sensors
```

After placing the files, run `template/reload` (Developer Tools > YAML >
Template Entities) or restart HA.

**Important:** You must find-and-replace the placeholder user names in
`theme_sensors.yaml` with your actual HA user names. The dark-mode user's
helpers are read by the `theme_dark_*` sensors; the light-mode user's helpers
are read by the `theme_light_*` sensors. Search for
`input_select.theme_style_` and `input_select.theme_palette_` to find all the
references.

### 6. Background Image Pipeline

To enable custom background images on the Appearance page:

**a) Create the folder structure on your HA server:**
```
/config/www/themes/backgrounds/          # drop full-size images here
/config/www/themes/backgrounds/thumbs/   # auto-generated thumbnails
```

**b) Add a command_line sensor** to detect available backgrounds:
```yaml
command_line:
  - sensor:
      name: theme backgrounds
      command: "python3 /config/scripts/list_theme_backgrounds.py"
      scan_interval: 30
      value_template: "{{ value_json.count | int(0) }}"
      json_attributes:
        - count
        - file_list
```

**c) Add a shell command** for thumbnail generation:
```yaml
shell_command:
  generate_theme_thumbnails: "python3 /config/scripts/generate_theme_thumbnails.py"
```

**d) Add an automation** to regenerate thumbnails when files change:
```yaml
automation:
  - id: theme_generate_background_thumbnails
    alias: "Theme: Generate background thumbnails"
    trigger:
      - platform: state
        entity_id: sensor.theme_backgrounds
    action:
      - service: shell_command.generate_theme_thumbnails
```

**e) Deploy the Python scripts** from this repo:
- `scripts/list_theme_backgrounds.py` → `/config/scripts/`
- `scripts/generate_theme_thumbnails.py` → `/config/scripts/`

The thumbnail script requires Pillow (`pip install Pillow`). It generates
~300px wide JPEG thumbnails and cleans up orphaned thumbnails when source
images are deleted.

HA serves everything under `/config/www/` at `/local/`:
- Full image: `/local/themes/backgrounds/mountain.jpg`
- Thumbnail: `/local/themes/backgrounds/thumbs/mountain.jpg`

### 7. Conditional Card Helpers

The Home view has conditional cards that show/hide based on time of day and
sensor values. A priority-managed template sensor controls which cards are
visible (max 5 at a time).

```yaml
input_boolean:
  cond_bedtime_doors:
    name: "Conditional: Bedtime Doors"
    icon: mdi:door-open
  cond_uv_index:
    name: "Conditional: UV Index"
    icon: mdi:weather-sunny-alert
```

Create automations to toggle these at appropriate times (e.g., bedtime doors
ON at 7:30 PM, OFF at 7:00 AM; UV index ON at 7:00 AM, OFF at 5:00 PM). See
`ha_config_additions.yaml` for example automations.

### 8. REST Sensor (UV Forecast)

The UV index chart uses an Open-Meteo REST sensor:

```yaml
rest:
  - resource: !secret openmeteo_uv_url
    scan_interval: 86400
    sensor:
      - name: "OpenMeteo Hourly UV Forecast"
        unique_id: openmeteo_hourly_uv_forecast
        value_template: "{{ value_json.hourly.uv_index | max | round(1) }}"
        unit_of_measurement: "UV index"
        icon: mdi:sun-wireless
        json_attributes_path: "$.hourly"
        json_attributes:
          - time
          - uv_index
```

In `secrets.yaml`:
```yaml
openmeteo_uv_url: "https://api.open-meteo.com/v1/forecast?latitude=YOUR_LAT&longitude=YOUR_LON&hourly=uv_index&timezone=YOUR_TZ&forecast_days=1"
```

Do not use `start_hour`/`end_hour` parameters — Open-Meteo returns HTTP 400.
The chart itself limits display to 7 AM–7 PM.

### 9. Kiosk Mode

The dashboard uses kiosk-mode to hide the HA header and sidebar:

```yaml
kiosk_mode:
  hide_header: true
  hide_sidebar: true
```

This is set at the top of `dashboard.yaml`. To access the full HA UI, use the
More popup > "Home Assistant" link, which navigates to `/lovelace/0`.

---

## Theme System

### How Per-User Detection Works

The theme system uses CSS `@media (prefers-color-scheme: dark/light)` to
detect which user is viewing the dashboard. This works because one household
member always uses dark mode and the other always uses light mode.

Every card's `card_mod` style block outputs **both** users' CSS, each wrapped
in the appropriate `@media` query. The browser applies whichever matches:

```css
@media (prefers-color-scheme: dark) {
  ha-card {
    /* dark-mode user's style + palette */
    --primary-color: #6a74d3;
    background: rgba(30,30,30,0.95) !important;
    /* ... */
  }
}
@media (prefers-color-scheme: light) {
  ha-card {
    /* light-mode user's style + palette */
    --primary-color: #6a74d3;
    background: rgba(255,255,255,0.95) !important;
    /* ... */
  }
}
```

The Appearance subview has a manual user toggle so you can edit either user's
preferences from any device — this is an editing control only, not a detection
mechanism.

> **Limitation:** This approach supports exactly two users. If you need more,
> you'd need a different detection mechanism (e.g., browser_mod user
> identification).

### Three Customization Axes

The theme has three independent axes that can be mixed and matched:

1. **Style** — the structural feel (card surfaces, borders, blur, corners)
2. **Palette** — the color tokens (primary, accent, state colors, glow colors)
3. **Background** — what's behind the cards (auto, none, solid color, image)

Changing one axis does not affect the others. The exception is `Auto`
background, which dynamically reflects the current style and palette.

### Styles

| Style | Card Look | Corners | Font | Dark Mode | Light Mode |
|-------|-----------|---------|------|-----------|------------|
| **Clean** | Opaque, flat, no borders | 18px | System | Dark surface, no effects | White surface, no effects |
| **Glass** | Translucent with `backdrop-filter` blur | 18px | System | Frosted dark glass | Frosted light glass |
| **Dark** | Fully opaque, subtle border + shadow | 18px | System | Near-black OLED-friendly | Crisp white with definition |
| **Glow** | Semi-translucent, palette-tinted border | 18px | System | Vivid gradient blobs bleed through | Soft watercolor wash |
| **Neon** | Dark HUD regardless of system theme | **4px** | **Share Tech Mono** | Neon borders, monospace | Same (always dark) |

**Per-style defaults:**

| Style | Card Opacity | Blur | Border |
|-------|-------------|------|--------|
| Clean | 95% | 0px | None |
| Glass | 18% | 12px | Hairline |
| Dark | 100% | 0px | 1px subtle |
| Glow | 75–80% | 2px | Palette-tinted |
| Neon | 70% | 0px | 1px neon primary + glow |

**Neon is intentionally different.** It breaks the "system font / 18px radius"
rules that the other four styles follow. It uses `Share Tech Mono` (loaded via
Google Fonts), 4px sharp corners, and keeps its dark HUD aesthetic even in
light mode. Neon + the Cyberdeck palette recreates the full FARM_CTL/cyberdeck
look.

### Palettes

8 palettes, each defining primary, accent, state colors, and glow blob colors:

| Palette | Primary | Accent | Vibe |
|---------|---------|--------|------|
| **Indigo** (default) | `#6a74d3` | `#6a74d3` | Muted purple-blue |
| **Ocean** | `#0077b6` | `#00b4d8` | Cool ocean blues |
| **Sunset** | `#e07040` | `#d4a03c` | Warm orange/amber |
| **Forest** | `#2d6a4f` | `#74a67a` | Deep earthy greens |
| **Rose** | `#c9607a` | `#a86090` | Pink/mauve |
| **Mono** | `#7a7a8a` | `#9a9aaa` | Neutral gray |
| **Cyberdeck** | `#00e5ff` | `#e91e8c` | Neon cyan/magenta |
| **Mint** | `#7ec8a0` | `#a8a0d6` | Soft green/lavender |

Each palette also defines `--state-on-color`, `--state-off-color`,
`--success-color`, `--warning-color`, `--error-color`, `--info-color`, and
three `--glow-color-N` values for the Glow style's radial gradient blobs.

### Backgrounds

The background is **independent from the style** — it's stored as a single
string value per user (`input_text.theme_background_<user>`) that can be one
of four types, distinguished by pattern:

| Value | What it paints |
|-------|---------------|
| `auto` | Style-flavored, palette-colored default (see below) |
| `none` | Nothing — HA's stock background shows through |
| `#rrggbb` | Solid color fill |
| `filename.jpg` | Image from `/config/www/themes/backgrounds/` |

**What `Auto` paints per style:**

| Style | Auto Background |
|-------|----------------|
| Clean | Subtle palette-tinted surface |
| Glass | Saturated palette wash (clearly visible behind frosted cards) |
| Dark | Near-black with minimal tint |
| Glow | Vibrant palette radial-gradient blobs |
| Neon | Near-black HUD surface (`#07070d`) |

`Auto` is the factory default and the "smart" option — it re-renders live as
you change style or palette. Solid colors and images are sticky and persist
across style/palette changes.

### Card Opacity and Blur

Two per-user sliders on the Appearance page let you override the style's
default card opacity and blur:

- **Opacity** controls the card background alpha (0–100%)
- **Blur** controls `backdrop-filter` blur in pixels (0–30px). Only visible
  when opacity is below 100%.

Both sliders default to **"follow style default"** (sentinel value `-1`). When
you drag a slider, it switches to a manual override that persists across style
changes. A "Default" chip next to each slider resets it back to following the
current style's default.

### Appearance Subview

![Appearance page](images/appearance_page_dark.png)

Accessed from More popup > Appearance. Layout:

1. **User toggle** — two chips to switch which user's preferences you're editing
2. **Style picker** — 5 tiles with visual previews (Clean, Glass, Dark, Glow, Neon)
3. **Palette picker** — 8 tiles with 4-dot color swatches
4. **Background picker:**
   - Auto / None toggle
   - Curated color swatches (8 colors)
   - Palette-derived color swatches (4 shades from the active palette)
   - Custom hex input
   - Image thumbnails (from the backgrounds folder)
5. **Card effects** — opacity and blur sliders with "Default" reset chips

---

## Architecture

### Why Card-Level, Not View-Level

Palette CSS variables at the **view level** via `card_mod`. This does not work
on `type: sections` views in HA 2026.6.

The `card-mod` element created for a sections view **never receives the `hass`
object**. card_mod needs `hass` to evaluate Jinja2 templates like
`{{ states('sensor.theme_dark_primary') }}`. Without it, the entire style
string renders to an empty string. All six views in this dashboard use
`type: sections`, so the entire view-level theming layer was a silent no-op.

**Fix:** All Jinja2-driven theming moved to **card-level** `card_mod`. Card-level
card_mod on any card (including markdown, stack-in-card, mushroom, etc.) does
receive `hass` and evaluates Jinja2 correctly.

The view-level anchor (`&theme_view_style`) is kept as an empty string no-op
so existing references don't break.

### Per-Property Sensors, Not One Big CSS Sensor

Putting the entire CSS block in a single template sensor doesn't work because
**HA sensor states are capped at 255 characters**. A full `@media` CSS block with
all palette colors, borders, shadows, etc. far exceeds that limit, causing the 
ensor to go `unavailable`.

**Fix:** The theme uses **many small per-property sensors**, each outputting a
single CSS value well under 255 characters:

```
sensor.theme_dark_primary        → "#6a74d3"
sensor.theme_dark_card_background → "rgba(30,30,30,0.95)"
sensor.theme_dark_card_border    → "1px solid rgba(255,255,255,0.06)"
sensor.theme_dark_card_blur      → "12"
...
```

YAML anchors in `dashboard.yaml` assemble the CSS structure and interpolate
these sensor values. This gives you granular re-rendering (changing just the
palette only updates the color sensors, not the entire CSS) and keeps each
sensor's state safely under the 255-char limit.

> If you ever need a long string from a sensor, put it in an **attribute**
> (attributes aren't 255-capped) and read it via `state_attr()`.

### YAML Anchors and Card Tiering

Not every card gets the full theme treatment. The dashboard defines five YAML
anchors at the top of `dashboard.yaml`:

| Anchor | Tier | Purpose | Used on |
|--------|------|---------|---------|
| `&theme_card_style` | Tier 1 | Full themed treatment — palette colors, style surfaces, blur | Content cards (weather, graphs, calendar, entity cards, etc.) |
| `&theme_chrome_style` | Tier 2 | Restrained treatment — tinted background, reduced blur (40% of content) | Navbar, bubble-card popup shells |
| `&theme_exempt_style` | Tier 3 | Strips all styling — transparent background, no border/shadow | Headings, chips, title cards, glance cards |
| `&theme_card_transparent` | — | Transparent background, no border | Wrapper cards (stack-in-card used for grouping) |
| `&theme_bg_card` | — | Background overlay card definition | First card of each view |

Each card gets `card_mod: style: *theme_card_style` (or the appropriate
anchor) and inherits the full CSS block. Cards that need additional custom CSS
(margins, conditional borders, etc.) concatenate it after the anchor
reference.

**Adding a new card:** Give it `card_mod: style: *theme_card_style` for content
cards, or `*theme_exempt_style` if it should be transparent (headings,
decorative elements). If it's inside a themed `stack-in-card`, it may not need
its own `card_mod` at all.

### Background Overlay Card

Because the background can't be set at the view level (see above), it's
painted by a **hidden markdown card** inserted as the first card of each
view's first section. Its `card_mod` makes it:

- `:host` → `position: fixed; height: 0` (no grid space consumed)
- `ha-card` → `position: fixed; inset: 0; z-index: -1` (full viewport, behind
  everything)
- `ha-card ha-markdown` → `display: none` (hide the empty markdown body)

The card's `ha-card` becomes a full-viewport layer that paints the palette
background color and (for the Glow style) the radial-gradient blob overlay.

There is one `*theme_bg_card` per view (6 total). They must remain as the
first card in each view.

### Duplicate Picker Sections

The Appearance subview has **two complete copies** of every picker section
(Style tiles, Palette tiles, Background options) — one per user, wrapped in
`conditional` cards that toggle on `input_select.theme_appearance_user`.

This duplication exists because:

1. HA does not support Jinja2 templating inside `tap_action` service call
   `entity_id` fields — you can't write
   `entity_id: input_select.theme_style_{{ current_user }}`
2. The tile previews use different hardcoded colors per user (dark-mode user
   tiles show dark surface previews; light-mode user tiles show light surface
   previews)

The result is ~350 lines of near-duplicate YAML. If you add a new style or
palette option, you must add the corresponding tile in **both** user blocks.

---

## Deployment

### Sync Script

The repo includes a sync script that deploys files to HA via SMB and reloads
the relevant services:

```bash
# Deploy dashboard + sensors + scripts, reload templates
uv run python scripts/general_home_dashboard_sync.py

# Deploy + restart HA (needed for configuration.yaml / frontend changes)
uv run python scripts/general_home_dashboard_sync.py -r
```

The script syncs: `dashboard.yaml`, `sensors.yaml`, `theme_sensors.yaml`, and
the two theme Python scripts. It then runs `template/reload` and
`command_line/reload`. The script uses its own `smbclient` connection,
independent of any Finder mount.

### Force-Refreshing the Dashboard

HA caches the Lovelace YAML config. After deploying a dashboard change, you
need to force a fresh read. Run this in the browser console (or via a
JavaScript tool):

```js
const ha = document.querySelector('home-assistant');
ha.hass.callWS({ type: 'lovelace/config', url_path: 'general-home', force: true });
```

Then reload the page.

### Validating Config Before Restart

```bash
curl -s -X POST "http://YOUR_HA:8123/api/config/core/check_config" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Gotchas

### After Any HA Restart

1. **SMB share drops.** If you mount `/config` via Finder, you'll need to
   remount after every restart. The sync script uses its own SMB connection and
   is unaffected.

2. **Template sensors get stuck at `unknown`.** They won't show even the
   Indigo fallback until you run `template/reload` (Developer Tools > YAML >
   Template Entities, or `POST /api/services/template/reload`). Always reload
   templates after a restart.

3. **`initial:` helpers reset.** If your `input_select`/`input_number` helpers
   have `initial:` set, they reset to that value on restart. Remove `initial:`
   lines to persist the last-set value across restarts.

### card_mod Timing

card_mod works by monkey-patching the `hass` setter on card element classes.
If a card class instantiates **before** card_mod loads, that card will never
be styled. The `extra_module_url` fix (see [Setup](#3-card_mod-load-order-fix))
addresses this, but if you ever see unstyled cards, the load order is the
first thing to check.

**Do not try to fix this with delays.** card_mod does not retroactively style
cards it missed. The fix is load order, not patience.

### Sensor State 255-Char Limit

HA template sensor states are capped at 255 characters. Any sensor state that
exceeds this goes `unavailable`. This is why the theme uses per-property
sensors instead of a single CSS-block sensor. If you add a new sensor, keep
its output under 255 characters.

### Entity ID vs. Unique ID

HA derives entity IDs from the sensor's friendly **name**, not its `unique_id`.
A sensor with `unique_id: theme_dark_lovelace_bg` but
`name: "Theme Dark Lovelace Background"` gets entity ID
`sensor.theme_dark_lovelace_background`. The dashboard references the entity
ID form (derived from the name). Don't assume the unique_id matches.

### Verifying card_mod Applied

To check if card_mod actually applied to a card, open the browser console and
walk the shadow DOM: `home-assistant` > `home-assistant-main` >
`ha-panel-lovelace` > `hui-root` > `#view hui-view` > `hui-sections-view` >
`hui-grid-section[]`. Find a card's `ha-card` element and run:

```js
getComputedStyle(haCard).getPropertyValue('--primary-color')
```

If it returns the palette color (e.g., `#6a74d3`), card_mod applied. If it
returns `#009ac7` (Material You default), it didn't. If it returns `unknown`,
card_mod applied but the sensors weren't ready (run `template/reload`).

### Neon Font Loading

The Neon style loads `Share Tech Mono` via a Google Fonts `@import` in the
card_mod CSS. This means the first render after a fresh page load may briefly
show the system font before the web font loads. The `@import` is
conditionally included only when either user has Neon selected, so it doesn't
slow down other styles.

### Light-Mode Glow Blending

The Glow style uses `mix-blend-mode: screen` in dark mode (lightens the glow
over the dark base) and `mix-blend-mode: multiply` in light mode (darkens the
pastel glow into the light base for a watercolor-wash effect). The light-mode
overlay opacity is set to 0.85 (vs 1.0 for dark mode) to keep the wash
subtle. If glow colors look too faint or too strong, adjust the alpha values
in `theme_sensors.yaml` for the `glow_1`/`glow_2`/`glow_3` sensors.

### APIs That Don't Work in 2026.6

- `POST /api/services/lovelace/reload` → 400
- `POST /api/lovelace/reload` → 404
- `POST /api/error_log`, `/api/error/all` → 404

Use the WebSocket `lovelace/config` call with `force: true` to reload YAML
dashboards. Use `POST /api/config/core/check_config` to validate config.

---

## File Inventory

### Repo Files

| File | Purpose |
|------|---------|
| `dashboard.yaml` | All views, theme YAML anchors, and card definitions (~2850 lines) |
| `theme_sensors.yaml` | Per-property template sensors for dark and light users (~435 lines) |
| `sensors.yaml` | Non-theme template sensors (conditional card manager, room light switches) |
| `ha_config_additions.yaml` | Documents all required HA helpers, sensors, automations, and config |
| `README.md` | This file |

### Scripts (in repo `scripts/` directory)

| Script | Purpose |
|--------|---------|
| `general_home_dashboard_sync.py` | SMB deploy + service reload |
| `generate_theme_thumbnails.py` | Creates ~300px JPEG thumbnails for the background picker |
| `list_theme_backgrounds.py` | Lists background images as JSON for the command_line sensor |

### Server Files (`/config/`)

| Path | Purpose |
|------|---------|
| `configuration.yaml` | Must include `frontend.extra_module_url` for card_mod |
| `template_sensors/theme_sensors.yaml` | Deployed copy of theme sensors |
| `template_sensors/general_home_sensors.yaml` | Deployed copy of general sensors |
| `www/themes/backgrounds/` | User-uploaded background images |
| `www/themes/backgrounds/thumbs/` | Auto-generated thumbnails |
| `scripts/generate_theme_thumbnails.py` | Deployed copy |
| `scripts/list_theme_backgrounds.py` | Deployed copy |

### Key Entities

**Helpers (per user):**
- `input_select.theme_style_<user>` — Clean / Glass / Dark / Glow / Neon
- `input_select.theme_palette_<user>` — Indigo / Ocean / Sunset / Forest / Rose / Mono / Cyberdeck / Mint
- `input_text.theme_background_<user>` — auto / none / #hex / filename
- `input_number.theme_card_opacity_<user>` — -1 (follow default) to 100
- `input_number.theme_card_blur_<user>` — -1 (follow default) to 30

**Shared:**
- `input_select.theme_appearance_user` — which user the Appearance page edits

**Sensors (one set for dark, one for light):**
`theme_{dark,light}_{primary, accent, state_on, state_off, success, warning,
error, info, glow_1, glow_2, glow_3, glow_active, lovelace_background,
card_background, card_border, card_shadow, card_opacity, card_blur,
card_radius, card_font}`
