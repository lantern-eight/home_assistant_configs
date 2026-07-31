# home_assistant_configs

Home Assistant configuration backup, dashboard management, and tooling. Runs on an
[HA Green](https://www.home-assistant.io/green/) with configs shared over SMB.

## Table of Contents

- [Setup](#setup)
- [Sync](#sync)
- [General HA Packages](#general-ha-packages)
- [Dashboards](#dashboards)
  - [General Home Mobile](#general-home-mobile)
  - [Cyberdeck (3D Printer Farm)](#cyberdeck-3d-printer-farm)
  - [Uploading to Home Assistant](#uploading-to-home-assistant)
- [Entity Discovery](#entity-discovery)
- [Tests](#tests)
- [Project Structure](#project-structure)

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Copy the example config and fill in real values
cp config.example.yaml config.yaml
```

`config.yaml` contains SMB credentials for connecting to the HA config share and a
long-lived access token for the HA REST API. `config.yaml`, `entity_map.yaml`, and
`registry_metadata.yaml` files (root and per-dashboard) are all gitignored
local config — copy from their `.example` counterparts and fill in real values.

| Key | Purpose |
|---|---|
| `smb_server` | IP of the HA instance (SMB share) |
| `smb_share` | SMB share name (usually `config`) |
| `smb_path` | Optional sub-path within the share |
| `smb_user` / `smb_password` | SMB credentials |
| `redact_entities` | Strings to redact from backup files |
| `token` | HA long-lived access token (for API calls) |
| `ha_base_url` | HA base URL (optional, defaults to `http://homeassistant.local:8123`) |

## Sync

One script handles everything: push files to HA via SMB, apply categories &
labels, reload services, pull backup files, and redact sensitive info. Most
config lives in repo-managed packages and dashboards, so only files that HA
owns (like `configuration.yaml`) need pulling back.

```bash
# Full sync (default, with no flags)
uv run python scripts/ha_sync.py

# Full sync + HA restart (for package/configuration.yaml changes)
uv run python scripts/ha_sync.py --restart

# Redact entities in local files only (no push/pull)
uv run python scripts/ha_sync.py --redact

# Undo redaction
uv run python scripts/ha_sync.py -u

# Apply categories & labels
uv run python scripts/ha_sync.py -c

# Debug logging
uv run python scripts/ha_sync.py -d

# Help
uv run python scripts/ha_sync.py -h
```

| Flag | Long form | Purpose |
|---|---|---|
| | `--redact` | Redact PII in local files only (no push/pull) |
| `-u` | `--unredact` | Undo redaction using `entity_map.yaml` |
| `-c` | `--categories` | Apply registry metadata only |
| | `--restart` | Restart HA after push (instead of reloading) |
| `-d` | `--debug` | Set log level to `DEBUG` |
| `-l` | `--log-level` | Set log level explicitly |
| `-h` | `--help` | Show usage |

The `--redact`, `-u`, and `-c` flags are mutually exclusive. With none of
them set, the script runs a full sync (push + metadata + reload + pull +
redact).

Pulled backup files land in `home_assistant_backup/`. To back up additional
files, add their paths (relative to the HA config root) to the
`BACKUP_FILES` list in `scripts/ha_sync.py`.

## General HA Packages

`packages/` at the repo root holds general-purpose HA config — house-wide
sensors, utility meters, helpers — that is not specific to one dashboard.
Dashboards consume these entities. General config goes in `packages/general.yaml`,
one commented section per concern. A large coherent domain can graduate to its
own file. Every yaml file in `packages/` is uploaded to HA's `packages/` directory
by `scripts/ha_sync.py`, and HA loads the whole directory via
`packages: !include_dir_named packages` — new files need no `configuration.yaml` edit,
they'll be auto-picked up. Package changes require an HA restart.

### Source of Truth vs. HA Backup Folder

The backup script only pulls files listed in `BACKUP_FILES` (currently just
`configuration.yaml`). Packages, dashboards, and other repo-managed config are
authored here and pushed to HA — they are the source of truth and don't need
pulling back.

Package files live at the repo root (`packages/`). HA only reads them, never
rewrites them, so comments persist. The flow is the opposite direction from
backups: packages are authored in the repo and pushed to HA.

## Dashboards

### General Home Mobile

Phone-first dashboard for everyday household use. Uses `type: sections` views
in kiosk mode with a per-user theme system (5 styles, 8 palettes, custom
backgrounds). See the full
[README](dashboards/general_home_mobile/README.md) for setup, architecture,
and screenshots.

```bash
# Deploy to HA (syncs all dashboards, packages, and scripts)
uv run python scripts/ha_sync.py
```

### Cyberdeck (3D Printer Farm)

Dashboard for monitoring and controlling 3D printers.

### Uploading to Home Assistant

`scripts/ha_sync.py` pushes all dashboard files, packages, and scripts to
the HA config share over SMB and reloads the relevant services. See the
per-dashboard READMEs for details.

## Entity Discovery

`scripts/ha_entity_discovery.py` queries the HA REST API to pull all entities and areas,
then writes the results to `ha_entities.json` (gitignored) and prints a
summary grouped by area and domain.

```bash
uv run python scripts/ha_entity_discovery.py

# Debug mode
uv run python scripts/ha_entity_discovery.py -d
```

This avoids repeated large API calls filling up context when working on dashboard
customization. The output file serves as a local reference for available entity
IDs, friendly names, and states.

## Tests

```bash
uv run pytest tests/ -v
```

- `test_redaction.py` — name redaction, pronoun neutralization, ID shortening
- `test_process_backup_files.py` — end-to-end backup file processing
- `test_restore.py` — entity map round-trip restore
- `test_conventions.py` — FILE_MAP existence, PII scan, doc/map agreement
- `test_config.py` — config loading from YAML and environment

## Project Structure

```
.
├── config.example.yaml              # Template for config.yaml (gitignored)
├── pyproject.toml                   # Python project config (uv/pip)
├── conftest.py                      # Adds scripts/ to Python path for tests
│
├── scripts/                         # Local Python tooling (runs on your machine)
│   ├── utils.py                     # Shared infra (config, SMB, entity map restore, registry metadata sync, argparse)
│   ├── ha_sync.py                   # Sync: push, metadata, reload, pull, redact
│   ├── ha_entity_discovery.py       # Query HA API for entities/areas -> JSON
│   └── ha_scripts/                  # Scripts deployed to and run on HA
│       ├── generate_theme_thumbnails.py
│       └── list_theme_backgrounds.py
│
├── dashboards/                      # Dashboards live here
│   ├── cyberdeck/                   # 3D printer farm dashboard
│   └── general_home_mobile/         # Mobile-first general home dashboard
│
├── packages/                        # General HA packages (house-wide sensors,
│   └── general.yaml                 #   utility meters) — not dashboard-specific
│
├── home_assistant_backup/           # Backup of HA config (redacted, process list only)
│   └── configuration.yaml
│
└── tests/
    ├── test_redaction.py
    ├── test_process_backup_files.py
    ├── test_restore.py
    ├── test_conventions.py
    └── test_config.py
```
