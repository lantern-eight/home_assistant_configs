"""Sync Cyberdeck dashboard and theme to Home Assistant via SMB."""

import sys
from pathlib import Path

import smbclient
import yaml

from ha_registry import restore_content
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

CYBERDECK_DIR = REPO_ROOT / 'dashboards' / 'cyberdeck'

FILE_MAP = {
  'dashboard.yaml': 'dashboards/cyberdeck/dashboard.yaml',
  'theme.yaml':     'themes/cyberdeck/cyberdeck.yaml',
}


def _sync_files(cfg: dict) -> int:
  smb_root = open_smb_session(cfg)

  entity_map = None
  if ENTITY_MAP_PATH.exists():
    with open(ENTITY_MAP_PATH) as f:
      entity_map = yaml.safe_load(f) or {}

  uploaded = 0
  for local_name, remote_rel in FILE_MAP.items():
    local_path = CYBERDECK_DIR / local_name
    if not local_path.exists():
      LOGGER.warning('Local file missing, skipping', extra={'file': str(local_path)})
      continue

    smb_rel = remote_rel.replace("/", "\\")
    remote_path = rf'{smb_root}\{smb_rel}'
    remote_dir = remote_path.rsplit('\\', 1)[0]
    smbclient.makedirs(remote_dir, exist_ok=True)

    try:
      with open(local_path, 'r', encoding='utf-8') as src:
        content = restore_content(src.read(), entity_map=entity_map)
      with smbclient.open_file(remote_path, mode='w') as dst:
        dst.write(content)
      uploaded += 1
      LOGGER.info('Synced', extra={'local': local_name, 'remote': remote_rel})
    except OSError as e:
      LOGGER.error('Failed to sync', extra={'file': local_name, 'error': str(e)})

  smbclient.reset_connection_cache()
  return uploaded


def main(argv: list[str] | None = None) -> None:
  """Sync Cyberdeck printer farm dashboard to Home Assistant."""
  parser = base_arg_parser(
    'Sync Cyberdeck dashboard and theme to Home Assistant via SMB.'
  )
  parser.add_argument('-r', '--restart', action='store_true',
                      help='Restart HA after sync (required on first deploy)')
  args = parser.parse_args(argv if argv is not None else sys.argv[1:])
  apply_log_level(args)

  if not CYBERDECK_DIR.exists():
    LOGGER.error('Cyberdeck directory not found at %s', CYBERDECK_DIR)
    sys.exit(1)

  cfg = load_config()

  LOGGER.info('Syncing Cyberdeck dashboard to HA')
  count = _sync_files(cfg)
  LOGGER.info('Sync complete', extra={'files_synced': count})

  if args.restart:
    restart_ha(cfg['token'], ha_base_url=cfg['ha_base_url'])
  else:
    if call_ha_service(cfg['token'], 'frontend', 'reload_themes',
                       ha_base_url=cfg['ha_base_url']):
      LOGGER.info('Themes reloaded')
    LOGGER.info('Dashboard YAML reloads automatically on next page visit')


if __name__ == '__main__':
  main(sys.argv[1:])
