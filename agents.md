# Agent instructions

## General

- Prefer 88-character line length for prose and code in this repo.

## Home Assistant

- **Sync scripts** Use `uv run python scripts/<sync_script>.py` to deploy.
- **`Errno 65: No route to host` is a macOS permission problem, not an
  unreachable host.** See "macOS Local Network Permission" in the root
  `README.md` for the diagnosis and the fix. Two traps: Apple-signed binaries
  keep working while the project virtualenv's Python does not, so it looks like
  a dependency fault; and the default gateway is exempt, so reaching the router
  proves nothing.
- **Run tests with `uv run python -m pytest`,** not the bare `pytest` console
  script — that can resolve against a system Python and fail every import,
  which reads as missing dependencies.
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
  directory by `scripts/ha_sync.py`, which restores `<entity_N>`
  placeholders from `entity_map.yaml` on push.
- HA's `configuration.yaml` loads the whole directory via
  `packages: !include_dir_named packages` — each file becomes a package
  keyed by its filename. New files need no configuration.yaml edit.
- Package changes require an HA restart (`sync.py -r`); they can't
  hot-reload.

## Registry metadata (categories & labels)

Every automation, helper, script, and sensor needs labels (and usually
a category) in `registry_metadata.yaml`. Two files exist:

- **Root `registry_metadata.yaml`** — general-purpose, for entities
  from `packages/*.yaml`.
- **Dashboard `registry_metadata.yaml`** — dashboard-specific, for
  helpers from `general_home_mobile.yaml` and dashboard-scoped
  automation groupings.

**Labels** are cross-cutting tags (an entity can have many):
`Lighting`, `Security`, `Scheduled`, `Notification`. Dashboard labels
are prefixed (`gm-`, `automation-`, `vacuum-`).

**Categories** are single-assignment per domain, used for Settings UI
grouping: `Bedtime`, `Morning Routine`, etc. Each has a `scope:` (automation,
script, helpers).

When adding an entity: read the existing file to find matching
labels/categories. Every automation gets a category + labels in the
root file, plus an `automation-*` label in the dashboard file. Helpers
get at least one label; dashboard helpers also get a category. Existing
labels/categories can be used and new ones created as needed.

Applied with `ha_sync.py -c` or as part of a full sync.

## Home Assistant config backup

Relevant when working under `home_assistant_backup/**` or `dashboards/**`.

### Where to edit

Do not edit `home_assistant_backup/` directly — it is overwritten on every SMB
pull. Config managed in code lives in `packages/` and `dashboards/`.

### Syncing

```bash
# Full sync: push + metadata + reload + pull + redact (default)
uv run python scripts/ha_sync.py

# Full sync with HA restart instead of reload
uv run python scripts/ha_sync.py --restart

# Redact entities in local files only (no push/pull)
uv run python scripts/ha_sync.py --redact

# Undo redaction
uv run python scripts/ha_sync.py -u

# Apply categories + labels only
uv run python scripts/ha_sync.py -c
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

## New Device Integration

When a new device or entity has been added to Home Assistant, follow
the checklist in `skills/new-device.md`. It covers every integration
point across the codebase — registry metadata, labels, notifications,
conditional cards, dashboard views, packages, and redaction. Walk
through it interactively with the user.

## Cyberdeck printer farm dashboard

Relevant when working under `dashboards/cyberdeck/**` (sync and development workflow for the Cyberdeck printer farm dashboard).

The Cyberdeck dashboard lives in `dashboards/cyberdeck/` with two files:

| Local file | HA destination |
|---|---|
| `dashboard.yaml` | `dashboards/cyberdeck/dashboard.yaml` |
| `theme.yaml` | `themes/cyberdeck/cyberdeck.yaml` |

The Cyberdeck's template sensors live in `packages/printer_farm_3d.yaml`,
deployed by `ha_sync.py` along with all other files.

### Syncing to Home Assistant

After editing any dashboard, theme, or package file, run:

```bash
uv run python scripts/ha_sync.py
```

This uploads all files (dashboards + packages + scripts)
to HA via SMB and reloads services. The dashboard YAML is re-read by
HA on the next page visit — no restart needed for dashboard-only changes.

If you changed `configuration.yaml` or packages, a restart is required:

```bash
uv run python scripts/ha_sync.py --restart
```
