# Agent instructions

## General

- Prefer 88-character line length for prose and code in this repo.

## Home Assistant

- **Hard restarts take ~5 minutes.** After triggering an HA restart
  (e.g. `sync.py -r`), don't actively poll — use `Bash` with
  `run_in_background` to wait. The web server comes up early, but
  integrations keep loading after that. Check the `state` field from
  `/api/config` — it reads `STARTING` until all integrations are
  loaded, then switches to `RUNNING`:
  ```bash
  TOKEN=$(python3 -c "import yaml; print(yaml.safe_load(open('config.yaml'))['token'])")
  until curl -s "http://<ip>:8123/api/config" \
    -H "Authorization: Bearer $TOKEN" 2>/dev/null \
    | grep -q '"state":"RUNNING"'; do sleep 5; done
  ```
  A plain health-ping (`/api/` returning 200/401) is NOT enough — it
  fires when the web server starts, before integrations finish loading.
  You'll be notified when the background command completes.

## General HA packages (`packages/`)

`packages/` at the repo root holds general-purpose HA config — house-wide
sensors, utility meters, helpers — that is not specific to one dashboard.
When adding a sensor that isn't inherently dashboard-specific, define it here, not in a
dashboard's package file.

- General config goes in `packages/general.yaml`, one commented section
  per concern. A large coherent domain can graduate to its own file —
  `!include_dir_named` picks up any new yaml file automatically.
- Every `*.yaml` file in `packages/` is synced to HA's `packages/`
  directory by `scripts/general_home_dashboard_sync.py`, which restores
  `<entity_N>` placeholders from `entity_map.yaml` on push.
- HA's `configuration.yaml` loads the whole directory via
  `packages: !include_dir_named packages` — each file becomes a package
  keyed by its filename. New files need no configuration.yaml edit.
- Package changes require an HA restart (`sync.py -r`); they can't
  hot-reload.

## Home Assistant config backup

Relevant when working under `home_assistant_backup/**` or `dashboards/**`.

### Where to edit

Do not edit `home_assistant_backup/` directly — it is overwritten on every SMB
pull. Config managed in code lives in `packages/` and `dashboards/`.

### Syncing from Home Assistant

```bash
# Pull from HA + redact (default)
uv run python scripts/home_assistant_backup.py

# Pull only, no redaction
uv run python scripts/home_assistant_backup.py -b

# Redact only, no pull
uv run python scripts/home_assistant_backup.py -s

# Reverse redaction before pushing to HA
uv run python scripts/home_assistant_backup.py -r
```

Do not push to HA unless the user explicitly asks.

### Redaction: names and IDs

`config.yaml` and `entity_map.yaml` are gitignored. They drive the sanitize pass differently:

| | **Custom strings** (`entity_map.entities`) | **Device/entity IDs** (`entity_map.ids`) |
|---|---|---|
| **What triggers redaction** | Strings listed in `config.yaml` → `redact_entities` | Any 32-char hex string or hyphenated UUID in a file |
| **Role of `entity_map.yaml`** | Reuse `<entity_N>` placeholders across runs; restore with `-r` | Record `abc...def` ↔ full ID mapping; restore with `-r` |
| **Configured in `config.yaml`?** | Yes — add each string to `redact_entities` | No — IDs are auto-discovered |

**Adding an ID**: no config step. If a full 32-char hex ID or hyphenated UUID appears in a file, sanitize shortens it to `first3...last3` and saves the mapping in `entity_map.ids`. Pre-populating `entity_map.ids` does not shorten anything — the full ID must be present in the file when sanitize runs.

## Cyberdeck printer farm dashboard

Relevant when working under `dashboards/cyberdeck/**` (sync and development workflow for the Cyberdeck printer farm dashboard).

The Cyberdeck dashboard lives in `dashboards/cyberdeck/` with two files:

| Local file | HA destination |
|---|---|
| `dashboard.yaml` | `dashboards/cyberdeck/dashboard.yaml` |
| `theme.yaml` | `themes/cyberdeck/cyberdeck.yaml` |

The Cyberdeck's template sensors live in `packages/printer_farm_3d.yaml`,
deployed by `general_home_dashboard_sync.py` (not `cyberdeck_sync.py`).

### Syncing to Home Assistant

After editing a Cyberdeck dashboard or theme file, run:

```bash
uv run python scripts/cyberdeck_sync.py
```

This uploads both files to HA via SMB and reloads themes. The dashboard YAML is re-read by HA on the next page visit — no restart needed for dashboard-only changes.

If you changed `configuration.yaml`, a restart is required:

```bash
uv run python scripts/cyberdeck_sync.py -r
```

### Key constraints

- Button-card JS templates: the identifier `html` is reserved by lit-html. Never use `let html`, `const html`, or `var html` in `[[[...]]]` blocks.
- Entity IDs: CC1 uses `*.centauri_carbon_*`, CC2 uses `*.centauri_carbon_2_*`.
- Theme variables: custom tokens are prefixed `--cyberdeck-` (e.g. `var(--cyberdeck-cyan)`).
- The dashboard is registered in HA's `configuration.yaml` under `lovelace.dashboards.cyber-deck` (hyphen required in URL path).
- **Open in browser:** `http://homeassistant.local:8123/cyber-deck/farm-ctl` (view path `farm-ctl` matches `dashboards/cyberdeck/dashboard.yaml` → `views[].path`).
