# Agent instructions

## Home Assistant config backup and automations

Relevant when working under `home_assistant_backup/**` or `home_assistant_backup_comments/**`.

### Where to edit

**Only make changes in `home_assistant_backup_comments/`.** HA strips YAML comments on save, so this directory is the comment-preserved source of truth. Do not edit `home_assistant_backup/` directly — it is overwritten on every SMB pull.

### Syncing from Home Assistant

```bash
# Pull from HA + redact (default)
uv run python home_assistant_backup.py

# Pull only, no redaction
uv run python home_assistant_backup.py -b

# Redact only, no pull
uv run python home_assistant_backup.py -s

# Reverse redaction before pushing to HA
uv run python home_assistant_backup.py -r
```

Do not push to HA unless the user explicitly asks.

### Redaction: names and IDs

`config.yaml` and `entity_map.yaml` are gitignored. They drive the sanitize pass differently:

| | **Custom names** (`entity_map.names`) | **Device/entity IDs** (`entity_map.ids`) |
|---|---|---|
| **What triggers redaction** | Names listed in `config.yaml` → `redact_names` | Any 32-char hex string found in a file |
| **Role of `entity_map.yaml`** | Reuse `<entity_N>` placeholders across runs; restore with `-r` | Record `abc...def` ↔ full ID mapping; restore with `-r` |
| **Configured in `config.yaml`?** | Yes — add each name to `redact_names` | No — IDs are auto-discovered |

**Adding an ID**: no config step. If a full 32-char hex ID appears in a comments file, sanitize shortens it to `first3...last3` and saves the mapping in `entity_map.ids`. Pre-populating `entity_map.ids` does not shorten anything — the full ID must be present in the file when sanitize runs.

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
- **Open in browser:** `http://homeassistant.local:8123/cyber-deck/farm-ctl` (view path `farm-ctl` matches `dashboards/cyberdeck/dashboard.yaml` → `views[].path`).
