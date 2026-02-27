# home_assistant_configs

Home Assistant configuration backup, dashboard management, and tooling. Runs on an
[HA Green](https://www.home-assistant.io/green/) with configs shared over SMB.

## Table of Contents

- [Setup](#setup)
- [Backup](#backup)
- [Dashboards](#dashboards)
  - [MD3 Mobile Dashboard](#md3-mobile-dashboard)
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
long-lived access token for the HA REST API. Both `config.yaml` and
`entity_map.yaml` are gitignored.

| Key | Purpose |
|---|---|
| `smb_server` | IP of the HA instance (SMB share) |
| `smb_share` | SMB share name (usually `config`) |
| `smb_path` | Optional sub-path within the share |
| `smb_user` / `smb_password` | SMB credentials |
| `redact_names` | Names to redact from backup files |
| `token` | HA long-lived access token (for API calls) |

## Backup

Pull the full HA configuration over SMB, then redact names and shorten hex IDs
for safe version control. An entity map is saved so redaction can be reversed.

```bash
# Backup (default)
uv run python home_assistant_backup.py

# Restore redacted files to original values
uv run python home_assistant_backup.py -r

# Debug mode
uv run python home_assistant_backup.py -d
```

The backup lands in `home_assistant_backup/`. A parallel
`home_assistant_backup_comments/` directory preserves comment-annotated versions
of automations (HA strips comments on save).

## Dashboards

### MD3 Mobile Dashboard

A [Material Design 3 dashboard](https://github.com/ElementZoom/Material-Design-3-Dynamic-Mobile-Dashboard)
by ElementZoom, brought in as a **git subtree** so upstream updates can be
pulled without losing local customizations.

The dashboard is served by HA in YAML mode. The relevant entry in `configuration.yaml`:

This was going to be implemented, but decided against it for now. Leaving this section
here for reference as it's a good dashboard, maybe in the future.

### Uploading to Home Assistant

`dashboard_upload.py` pushes `dashboard.yaml` to the HA config share over SMB
using the same credentials as the backup script.

```bash
# Upload and trigger lovelace reload
uv run python dashboard_upload.py

# Upload without reload
uv run python dashboard_upload.py -n

# Debug mode
uv run python dashboard_upload.py -d
```

After uploading, HA detects the file change and shows a "Refresh" prompt in the
dashboard UI. On a phone, pull down to refresh.


### HACS Dependencies

The MD3 dashboard requires ~30 HACS frontend components. All are currently
installed. See the upstream
[README](dashboards/Material-Design-3-Dynamic-Mobile-Dashboard/README.md) for
the full list. Key ones:

Bubble Card, Button Card, Streamline Card, Mushroom, Material You Theme, Material
You Utilities, Material Symbols, Navbar Card, Simple Swipe Card, Simple Tabs,
Stack In Card, Vertical Stack In Card, Card Mod, Auto Entities, ApexCharts, Mini
Graph Card, Timer Bar Card, Calendar Card Pro, Kiosk Mode, Layout Card, Config
Template Card, Paper Buttons Row, My Cards Bundle, Mediocre Media Player Cards,
WebRTC Camera, Lunar Phase Card, Weather Forecast Extended.

## Entity Discovery

`ha_entity_discovery.py` queries the HA REST API to pull all entities and areas,
then writes the results to `ha_entities.json` (gitignored) and prints a
summary grouped by area and domain.

```bash
uv run python ha_entity_discovery.py

# Debug mode
uv run python ha_entity_discovery.py -d
```

This avoids repeated large API calls filling up context when working on dashboard
customization. The output file serves as a local reference for available entity
IDs, friendly names, and states.

## Tests

```bash
uv run pytest tests/ -v
```

- `test_redaction.py` -- name redaction, pronoun neutralization, ID shortening
- `test_process_backup_files.py` -- end-to-end backup file processing
- `test_restore.py` -- entity map round-trip restore
- `test_ignore_patterns.py` -- file/directory ignore rules
- `test_config.py` -- config loading from YAML and environment

## Project Structure

```
.
├── config.example.yaml              # Template for config.yaml (gitignored)
├── pyproject.toml                   # Python project config (uv/pip)
├── utils.py                         # Shared logging (JSON + colored TTY output)
│
├── home_assistant_backup.py         # Pull HA config over SMB, redact, shorten IDs
├── ha_entity_discovery.py           # Query HA API for entities/areas -> JSON
├── dashboard_customize.py           # Bulk entity/room substitution for dashboard
├── dashboard_upload.py              # Push dashboard.yaml to HA over SMB
│
├── dashboards/                      # Dashboards live here
│
├── home_assistant_backup/           # Backup of HA config (redacted)
│   ├── configuration.yaml
│   ├── automations.yaml
│   ├── custom__sensors.yaml
│   ├── blueprints/
│   ├── dashboards/
│   ├── themes/
│   └── www/community/               # HACS frontend components (gitignored)
│
├── home_assistant_backup_comments/  # Comment-preserved automation copies
│
└── tests/
    ├── test_redaction.py
    ├── test_process_backup_files.py
    ├── test_restore.py
    ├── test_ignore_patterns.py
    └── test_config.py
```
