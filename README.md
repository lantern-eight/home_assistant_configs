# home_assistant_configs

Home Assistant configuration backup, dashboard management, and tooling. Runs on an
[HA Green](https://www.home-assistant.io/green/) with configs shared over SMB.

## Table of Contents

- [Setup](#setup)
- [Backup](#backup)
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
long-lived access token for the HA REST API. Both `config.yaml` and
`entity_map.yaml` are gitignored.

| Key | Purpose |
|---|---|
| `smb_server` | IP of the HA instance (SMB share) |
| `smb_share` | SMB share name (usually `config`) |
| `smb_path` | Optional sub-path within the share |
| `smb_user` / `smb_password` | SMB credentials |
| `redact_entities` | Strings to redact from backup files |
| `token` | HA long-lived access token (for API calls) |

## Backup

Pull the full HA configuration over SMB, then redact names and shorten hex IDs
for safe version control. An entity map is saved so redaction can be reversed.

```bash
# Backup + sanitize (default, with no flags)
uv run python scripts/home_assistant_backup.py

# SMB pull only, no redaction pass
# - backup
uv run python scripts/home_assistant_backup.py -b

# Redaction pass only, no SMB pull
# (processes home_assistant_backup/, home_assistant_backup_comments/, and dashboards/)
# - sanitize
uv run python scripts/home_assistant_backup.py -s

# Restore redacted files to original values using entity_map.yaml
# - restore
uv run python scripts/home_assistant_backup.py -r

# Debug logging
uv run python scripts/home_assistant_backup.py -d

# Set a specific log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
uv run python scripts/home_assistant_backup.py -l DEBUG

# Help
uv run python scripts/home_assistant_backup.py -h
```

| Flag | Long form | Purpose |
|---|---|---|
| `-b` | `--backup` | SMB pull only (no sanitize) |
| `-s` | `--sanitize` | Redaction pass only (no SMB pull) |
| `-r` | `--restore` | Restore redacted files using `entity_map.yaml` |
| `-d` | `--debug` | Set log level to `DEBUG` |
| `-l` | `--log-level` | Set log level explicitly |
| `-h` | `--help` | Show usage |

The `-b`, `-s`, and `-r` flags are mutually exclusive. With none of them set,
the script runs backup followed by sanitize.

The backup lands in `home_assistant_backup/`. A parallel
`home_assistant_backup_comments/` directory preserves comment-annotated versions
of automations (HA strips comments on save).

## Dashboards

### General Home Mobile

Phone-first dashboard for everyday household use. Uses `type: sections` views
in kiosk mode with a per-user theme system (5 styles, 8 palettes, custom
backgrounds). See the full
[README](dashboards/general_home_mobile/README.md) for setup, architecture,
and screenshots.

```bash
# Deploy to HA
uv run python scripts/general_home_dashboard_sync.py
```

### Cyberdeck (3D Printer Farm)

Dashboard for monitoring and controlling 3D printers. Synced to HA via its
own sync script.

```bash
# Deploy to HA
uv run python scripts/cyberdeck_sync.py
```

### Uploading to Home Assistant

Each dashboard has its own sync script that pushes files to the HA config
share over SMB and reloads the relevant services. See the per-dashboard
READMEs for details.

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
├── conftest.py                      # Adds scripts/ to Python path for tests
│
├── scripts/                         # All Python scripts
│   ├── utils.py                     # Shared logging (JSON + colored TTY output)
│   ├── home_assistant_backup.py     # Pull HA config over SMB, redact, shorten IDs
│   ├── ha_entity_discovery.py       # Query HA API for entities/areas -> JSON
│   ├── dashboard_upload.py          # Push dashboard.yaml to HA over SMB
│   ├── cyberdeck_sync.py            # Sync Cyberdeck dashboard to HA via SMB
│   └── general_home_dashboard_sync.py  # Sync General Home Mobile dashboard to HA
│
├── dashboards/                      # Dashboards live here
│   ├── cyberdeck/                   # 3D printer farm dashboard
│   └── general_home_mobile/         # Mobile-first general home dashboard
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
