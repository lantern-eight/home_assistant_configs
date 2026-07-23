"""Sync General Home Mobile dashboard and sensors to Home Assistant via SMB.

Also syncs the repo-root packages/ directory — general-purpose HA packages
(utility meters, house-wide helpers) that are not specific to one dashboard.
Every *.yaml there is uploaded to HA's packages/ directory, where
configuration.yaml loads the whole directory via `!include_dir_named`.
"""

import sys
from pathlib import Path

import smbclient
import yaml

from ha_registry import apply_registry_metadata, restore_content
from utils import (
  ENTITY_MAP_PATH,
  LOGGER,
  REPO_ROOT,
  apply_log_level,
  base_arg_parser,
  call_ha_service,
  load_config,
  open_smb_session,
  restart_ha,
)

DASHBOARD_DIR = REPO_ROOT / 'dashboards' / 'general_home_mobile'
PACKAGES_DIR = REPO_ROOT / 'packages'
SCRIPTS_DIR = REPO_ROOT / 'scripts'

FILE_MAP = {
  'dashboard.yaml': 'dashboards/general_home_mobile/dashboard.yaml',
  'sensors.yaml':   'template_sensors/general_home_sensors.yaml',
  'general_home_mobile.yaml': 'packages/general_home_mobile.yaml',
  'general_home_theme.jinja': 'custom_templates/general_home_theme.jinja',
  'popup_history_fix.js': 'www/popup_history_fix.js',
}

SCRIPT_MAP = {
  'ha_scripts/generate_theme_thumbnails.py': 'scripts/generate_theme_thumbnails.py',
  'ha_scripts/list_theme_backgrounds.py': 'scripts/list_theme_backgrounds.py',
}


def _upload_file(smb_root: str, local_path: Path, remote_rel: str,
                 restore: bool, entity_map: dict | None = None) -> bool:
  """Upload one local file to the HA config share, creating remote dirs as needed."""
  smb_rel = remote_rel.replace("/", "\\")
  remote_path = rf'{smb_root}\{smb_rel}'
  remote_dir = remote_path.rsplit('\\', 1)[0]
  smbclient.makedirs(remote_dir, exist_ok=True)

  try:
    with open(local_path, 'r', encoding='utf-8') as src:
      content = src.read()
    if restore:
      content = restore_content(content, entity_map=entity_map)
    with smbclient.open_file(remote_path, mode='w') as dst:
      dst.write(content)
    LOGGER.info('Synced', extra={'local': local_path.name, 'remote': remote_rel})
    return True
  except OSError as e:
    LOGGER.error('Failed to sync', extra={'file': local_path.name, 'error': str(e)})
    return False


def _sync_files(cfg: dict) -> int:
  smb_root = open_smb_session(cfg)

  entity_map = None
  if ENTITY_MAP_PATH.exists():
    with open(ENTITY_MAP_PATH) as f:
      entity_map = yaml.safe_load(f) or {}

  uploaded = 0
  for local_name, remote_rel in FILE_MAP.items():
    local_path = DASHBOARD_DIR / local_name
    if not local_path.exists():
      LOGGER.warning('Local file missing, skipping', extra={'file': str(local_path)})
      continue
    if _upload_file(smb_root, local_path, remote_rel, restore=True, entity_map=entity_map):
      uploaded += 1

  for local_path in sorted(PACKAGES_DIR.glob('*.yaml')):
    if _upload_file(smb_root, local_path, f'packages/{local_path.name}',
                    restore=True, entity_map=entity_map):
      uploaded += 1

  for local_name, remote_rel in SCRIPT_MAP.items():
    local_path = SCRIPTS_DIR / local_name
    if not local_path.exists():
      LOGGER.warning('Local script missing, skipping', extra={'file': str(local_path)})
      continue
    if _upload_file(smb_root, local_path, remote_rel, restore=False):
      uploaded += 1

  smbclient.reset_connection_cache()
  return uploaded


def _reload_services(cfg: dict) -> None:
  token = cfg['token']
  ha_base_url = cfg['ha_base_url']
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping service reloads')
    return
  for service in ('homeassistant/reload_custom_templates', 'template/reload', 'command_line/reload'):
    domain, svc = service.split('/', 1)
    if call_ha_service(token, domain, svc, ha_base_url=ha_base_url):
      LOGGER.info('Reloaded', extra={'service': service})


def _apply_registry_metadata(cfg: dict) -> None:
  """Apply dashboard-specific categories/labels from registry_metadata.yaml."""
  metadata_path = DASHBOARD_DIR / 'registry_metadata.yaml'
  apply_registry_metadata(metadata_path, cfg['token'], ENTITY_MAP_PATH)


def main(argv: list[str] | None = None) -> None:
  """Sync General Home Mobile dashboard to Home Assistant."""
  parser = base_arg_parser(
    'Sync General Home Mobile dashboard to Home Assistant via SMB.'
  )
  parser.add_argument('-r', '--restart', action='store_true',
                      help='Restart HA after sync (required on first deploy or sensor changes)')
  parser.add_argument('-c', '--categories', action='store_true',
                      help='Apply categories and labels from registry_metadata.yaml')
  args = parser.parse_args(argv if argv is not None else sys.argv[1:])
  apply_log_level(args)

  if not DASHBOARD_DIR.exists():
    LOGGER.error('Dashboard directory not found at %s', DASHBOARD_DIR)
    sys.exit(1)

  cfg = load_config()

  LOGGER.info('Syncing General Home Mobile dashboard to HA')
  count = _sync_files(cfg)
  LOGGER.info('Sync complete', extra={'files_synced': count})

  if args.categories:
    _apply_registry_metadata(cfg)

  if args.restart:
    restart_ha(cfg['token'], ha_base_url=cfg['ha_base_url'])
  else:
    _reload_services(cfg)
    LOGGER.info('Dashboard YAML reloads automatically on next page visit')


if __name__ == '__main__':
  main(sys.argv[1:])
