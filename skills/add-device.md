# Add Device Checklist

Walk through interactively with the user. Grep the codebase for
entities with the same domain to find where similar devices are
already wired in — follow those patterns.

## Every device

- **Registry metadata** — `registry_metadata.yaml` (gitignored).
  Add labels and optionally a category under `entities:`. Read the
  file to see existing labels/categories.
- **PII redaction** — if the entity ID or friendly name contains
  personal info, add the string to `config.yaml` → `redact_entities`.
- **Notifications** — If the user would like it in the general home
  dashboard, `dashboards/general_home_mobile/sensors.yaml`. Find where
  and how it may fit in there.
  Likely will include a trigger + notification item to the
  `Dashboard Notifications` sensor. Severity: red (urgent),
  amber (warning), blue (info), green (normal). Items are always
  present with an `active` flag. If `promoted: true`, add a conditional
  chip on the Home view. If it is more information dense it could benefit
  from a full card. See `dashboards/general_home_mobile/agents.md` →
  "Adding a conditional card".

## By device type

**Light** — room lights are auto-discovered via `room_lights.jinja`
(area assignment in HA). Non-room lights (LEDs, indicators) get the
`Utility Light` label to exclude them from light counts and room
switches.

**Door / entry sensor** — add to the Security view in
`dashboard.yaml`. Notification: red when open, green when closed.

**Climate (temp + humidity)** — if both sensors exist, add a
`thermal_comfort` entry in `packages/general.yaml`.

**Power / energy** — Consider adding a `utility_meter` in
`packages/general.yaml`.

## Deploy

```bash
uv run python scripts/ha_sync.py            # default full sync
uv run python scripts/ha_sync.py --restart  # if packages changed
```
