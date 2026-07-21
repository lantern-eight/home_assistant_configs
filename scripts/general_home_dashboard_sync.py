"""Sync General Home Mobile dashboard and sensors to Home Assistant via SMB.

Also syncs the repo-root packages/ directory — general-purpose HA packages
(utility meters, house-wide helpers) that are not specific to one dashboard.
Every *.yaml there is uploaded to HA's packages/ directory, where
configuration.yaml loads the whole directory via `!include_dir_named`.
"""

import logging
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import requests
import smbclient
import yaml

from ha_registry import apply_registry_metadata, restore_content
from utils import LOGGER

USAGE = (
  'Usage: uv run python scripts/general_home_dashboard_sync.py [-d] [-l LEVEL] [-r] [-c] [-h]\n'
  '  -c, --categories Apply categories and labels from registry_metadata.yaml\n'
  '  -d, --debug      Set log level to DEBUG\n'
  '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
  '  -r, --restart    Restart HA after sync (required on first deploy or sensor changes)\n'
  '  -h, --help       Show this help'
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / 'config.yaml'
ENTITY_MAP_PATH = REPO_ROOT / 'entity_map.yaml'
DASHBOARD_DIR = REPO_ROOT / 'dashboards' / 'general_home_mobile'
PACKAGES_DIR = REPO_ROOT / 'packages'
SCRIPTS_DIR = REPO_ROOT / 'scripts'
HA_BASE_URL = 'http://homeassistant.local:8123'

FILE_MAP = {
  'dashboard.yaml': 'dashboards/general_home_mobile/dashboard.yaml',
  'sensors.yaml':   'template_sensors/general_home_sensors.yaml',
  'theme_sensors.yaml': 'template_sensors/theme_sensors.yaml',
  'general_home_mobile.yaml': 'packages/general_home_mobile.yaml',
  'general_home_theme.jinja': 'custom_templates/general_home_theme.jinja',
  'popup_history_fix.js': 'www/popup_history_fix.js',
}

SCRIPT_MAP = {
  'ha_scripts/generate_theme_thumbnails.py': 'scripts/generate_theme_thumbnails.py',
  'ha_scripts/list_theme_backgrounds.py': 'scripts/list_theme_backgrounds.py',
}


def _load_config() -> dict:
  if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
      raw = yaml.safe_load(f) or {}
    return {
      'smb_server': str(raw.get('smb_server', '')),
      'smb_share': str(raw.get('smb_share', '')),
      'smb_path': str(raw.get('smb_path', '')),
      'smb_user': str(raw.get('smb_user', '')),
      'smb_password': str(raw.get('smb_password', '')),
      'token': str(raw.get('token', '')),
    }
  LOGGER.error('config.yaml not found — copy from config.example.yaml and fill in values')
  sys.exit(1)


def _smb_makedirs(smb_path: str) -> None:
  try:
    smbclient.stat(smb_path)
    return
  except OSError:
    pass
  parent = smb_path.rsplit('\\', 1)[0]
  if parent and parent != smb_path:
    _smb_makedirs(parent)
  try:
    smbclient.mkdir(smb_path)
  except OSError:
    pass


def _restore_content(content: str) -> str:
  '''Replace redacted placeholders with real values before pushing to HA.'''
  return restore_content(content, ENTITY_MAP_PATH)


def _upload_file(smb_root: str, local_path: Path, remote_rel: str, restore: bool) -> bool:
  """Upload one local file to the HA config share, creating remote dirs as needed.

  With restore=True, <entity_N> placeholders are replaced with real values
  before upload (for yaml pushed to HA). Scripts upload verbatim. Returns
  True on success, False on failure (error is logged, not raised).
  """
  remote_path = rf'{smb_root}\{remote_rel.replace("/", chr(92))}'
  remote_dir = remote_path.rsplit('\\', 1)[0]
  _smb_makedirs(remote_dir)

  try:
    with open(local_path, 'r', encoding='utf-8') as src:
      content = src.read()
    if restore:
      content = _restore_content(content)
    with smbclient.open_file(remote_path, mode='w') as dst:
      dst.write(content)
    LOGGER.info('Synced', extra={'local': local_path.name, 'remote': remote_rel})
    return True
  except OSError as e:
    LOGGER.error('Failed to sync', extra={'file': local_path.name, 'error': str(e)})
    return False


def _sync_files(cfg: dict) -> int:
  smb_server = cfg['smb_server']
  smb_share = cfg['smb_share']
  smb_path = cfg['smb_path']

  if not smb_server or not smb_share:
    LOGGER.error('Set smb_server and smb_share in config.yaml')
    sys.exit(1)

  smb_root = rf'\\{smb_server}\{smb_share}'
  if smb_path:
    smb_root = rf'{smb_root}\{smb_path.strip("/").replace("/", chr(92))}'

  smbclient.ClientConfig(username=cfg['smb_user'] or None, password=cfg['smb_password'] or None)
  smbclient.register_session(
    smb_server,
    username=cfg['smb_user'] or None,
    password=cfg['smb_password'] or None,
  )
  LOGGER.info('SMB session registered', extra={'smb_root': smb_root})

  uploaded = 0
  for local_name, remote_rel in FILE_MAP.items():
    local_path = DASHBOARD_DIR / local_name
    if not local_path.exists():
      LOGGER.warning('Local file missing, skipping', extra={'file': str(local_path)})
      continue
    if _upload_file(smb_root, local_path, remote_rel, restore=True):
      uploaded += 1

  # General HA packages (repo-root packages/) — every yaml file is a package,
  # loaded by configuration.yaml via `packages: !include_dir_named packages`.
  for local_path in sorted(PACKAGES_DIR.glob('*.yaml')):
    if _upload_file(smb_root, local_path, f'packages/{local_path.name}', restore=True):
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


def _reload_services(token: str) -> None:
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping service reloads')
    return
  headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
  # custom_templates first: template sensors and card_mod styles import from it.
  for service in ('homeassistant/reload_custom_templates', 'template/reload', 'command_line/reload'):
    domain, svc = service.split('/', 1)
    try:
      resp = requests.post(
        f'{HA_BASE_URL}/api/services/{domain}/{svc}',
        headers=headers,
        timeout=30,
      )
      if resp.status_code == 200:
        LOGGER.info('Reloaded', extra={'service': service})
      else:
        LOGGER.warning('Reload failed', extra={'service': service, 'status': resp.status_code})
    except requests.RequestException as e:
      LOGGER.warning('Reload error', extra={'service': service, 'error': str(e)})


def _restart_ha(token: str) -> bool:
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping restart')
    return False
  headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
  try:
    LOGGER.info('Restarting Home Assistant...')
    resp = requests.post(f'{HA_BASE_URL}/api/services/homeassistant/restart', headers=headers, timeout=30)
    if resp.status_code == 200:
      LOGGER.info('HA restart triggered — dashboard will reload on next visit')
      return True
    LOGGER.warning('Restart failed', extra={'status': resp.status_code})
    return False
  except requests.RequestException as e:
    LOGGER.warning('Restart error', extra={'error': str(e)})
    return False


def _apply_registry_metadata(cfg: dict) -> None:
  """Apply dashboard-specific categories/labels from registry_metadata.yaml."""
  metadata_path = DASHBOARD_DIR / 'registry_metadata.yaml'
  apply_registry_metadata(metadata_path, cfg['token'], ENTITY_MAP_PATH)


def main(argv: list[str] | None = None) -> None:
  """
  Sync General Home Mobile dashboard to Home Assistant.

  Uploads dashboard.yaml and template sensors via SMB.
  Use --restart on first deploy or after editing sensors/configuration.
  Use --categories to create/assign categories and labels via WebSocket.

  Example:
    > uv run python general_home_dashboard_sync.py           # sync dashboard only
    > uv run python general_home_dashboard_sync.py -r         # sync + restart HA
    > uv run python general_home_dashboard_sync.py -c         # sync + apply categories/labels
    > uv run python general_home_dashboard_sync.py -d         # sync with debug logging
  """
  argv = argv if argv is not None else sys.argv[1:]

  try:
    opts, _ = getopt(argv, 'hcdl:r', ['help', 'categories', 'debug', 'log-level=', 'restart'])
  except GetoptError:
    LOGGER.error('Invalid options. %s', USAGE)
    sys.exit(1)

  do_restart = False
  do_categories = False
  for opt, arg in opts:
    if opt in ('-h', '--help'):
      print(USAGE)
      sys.exit(0)
    if opt in ('-c', '--categories'):
      do_categories = True
    if opt in ('-d', '--debug'):
      LOGGER.setLevel(logging.DEBUG)
    if opt in ('-l', '--log-level'):
      level = getattr(logging, arg.upper(), None)
      if level is None:
        LOGGER.error('Invalid log level: %s', arg)
        sys.exit(1)
      LOGGER.setLevel(level)
    if opt in ('-r', '--restart'):
      do_restart = True

  if not DASHBOARD_DIR.exists():
    LOGGER.error('Dashboard directory not found at %s', DASHBOARD_DIR)
    sys.exit(1)

  cfg = _load_config()

  LOGGER.info('Syncing General Home Mobile dashboard to HA')
  count = _sync_files(cfg)
  LOGGER.info('Sync complete', extra={'files_synced': count})

  if do_categories:
    _apply_registry_metadata(cfg)

  if do_restart:
    _restart_ha(cfg['token'])
  else:
    _reload_services(cfg['token'])
    LOGGER.info('Dashboard YAML reloads automatically on next page visit')


if __name__ == '__main__':
  main(sys.argv[1:])
