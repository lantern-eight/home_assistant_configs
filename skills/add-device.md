# Add Device Checklist

Walk through interactively with the user. Start from the **device
name or device ID** — devices often expose multiple entities, so
query the HA API to discover all of them before deciding what to
wire in. Ask: **what is the intent for this device?** The answer
drives which integration points matter.

## 1. Intent

Before touching any files, understand the device's purpose:
- What does it monitor or control?
- Is it informational, alerting, or both?
- Does it belong to an existing domain (lighting, security,
  climate, printing) or is it something new?
- Will it need configurable thresholds or user-facing settings?

## 2. Universal (every device)

- **Registry metadata** — `registry_metadata.yaml` (gitignored).
  Add labels and optionally a category under `entities:`. Read the
  file to see existing labels/categories. Create new labels if no
  existing one fits.
- **PII redaction** — if the entity ID or friendly name contains
  personal info, add the string to `config.yaml` → `redact_entities`.

## 3. Integration points

Not every device belongs everywhere — the intent decides. Each
section below is self-contained and optional.

### General HA packages (`packages/`)

For house-wide config: helpers, utility meters, automations,
template sensors. See root `agents.md` → "General HA packages".

- `input_number` / `input_boolean` / `input_text` helpers for
  user-configurable thresholds or state
- `thermal_comfort` entries (if temp + humidity pair)
- `utility_meter` entries
- Phone notification automations
- Package changes require `--restart`

### General Home Mobile dashboard

Read `dashboards/general_home_mobile/README.md` and `agents.md`
for full architecture, patterns, and how-to guides. Key places
a device can appear:

- **Notification bar** — glanceable status dot in the header.
  Severity: red (urgent), amber (warning), blue (info), green
  (normal). Red items are promoted to standalone chips. Add to
  `sensor.dashboard_notifications` in `sensors.yaml`.
- **Conditional card** — richer display (chart, gauge, entity
  list) that appears below the weather card on the Home view.
  Gated by a schedule or input_boolean. See agents.md →
  "Adding a conditional card".
- **Sub-views** — Security, Climate, or other existing views
  where the device fits contextually.
- **New framework** — if the device introduces a whole new
  domain, it may need new helpers, new template sensors, and a
  new conditional card pattern.

### Cyberdeck (3D printer farm) dashboard

Only for printer-related devices. See
`dashboards/cyberdeck/` for patterns.

### Existing automations and routines

Check whether the device should integrate with:
- Bedtime routine (lights off, door monitoring)
- After-bedtime door alerts (new doors, new lights)
- Morning routine (wake-up lights, schedules)
- Other time-based or event-based flows

### Lighting

Room lights are auto-discovered via `room_lights.jinja` (HA area
assignment). Utility lights get the `Utility Light` label to
exclude them from counts and switches.

## 4. Deploy

```bash
uv run python scripts/ha_sync.py            # default full sync
uv run python scripts/ha_sync.py --restart  # if packages changed
```
