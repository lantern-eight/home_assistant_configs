# Agent instructions

## Cyberdeck printer farm dashboard

Relevant when working under `dashboards/cyberdeck/**` (sync and development workflow for the Cyberdeck printer farm dashboard).

The Cyberdeck dashboard lives in `dashboards/cyberdeck/` with three files:

| Local file | HA destination |
|---|---|
| `dashboard.yaml` | `dashboards/cyberdeck/dashboard.yaml` |
| `theme.yaml` | `themes/cyberdeck/cyberdeck.yaml` |
| `sensors.yaml` | `template_sensors/printer_farm_sensors.yaml` |

### Syncing to Home Assistant

After editing any Cyberdeck file, run:

```bash
uv run python cyberdeck_sync.py
```

This uploads all three files to HA via SMB and reloads themes. The dashboard YAML is re-read by HA on the next page visit — no restart needed for dashboard-only changes.

If you changed `sensors.yaml` (template sensors) or `configuration.yaml`, a restart is required:

```bash
uv run python cyberdeck_sync.py -r
```

### Key constraints

- Button-card JS templates: the identifier `html` is reserved by lit-html. Never use `let html`, `const html`, or `var html` in `[[[...]]]` blocks.
- Entity IDs: CC1 uses `*.centauri_carbon_*`, CC2 uses `*.centauri_carbon_2_*`.
- Theme variables: custom tokens are prefixed `--cyberdeck-` (e.g. `var(--cyberdeck-cyan)`).
- The dashboard is registered in HA's `configuration.yaml` under `lovelace.dashboards.cyber-deck` (hyphen required in URL path).
