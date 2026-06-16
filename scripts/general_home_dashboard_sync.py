"""Sync General Home Mobile dashboard and sensors to Home Assistant via SMB."""

import logging
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import requests
import smbclient
import yaml

from utils import LOGGER

USAGE = (
  'Usage: uv run python scripts/general_home_dashboard_sync.py [-d] [-l LEVEL] [-r] [-h]\n'
  '  -d, --debug      Set log level to DEBUG\n'
  '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
  '  -r, --restart    Restart HA after sync (required on first deploy or sensor changes)\n'
  '  -h, --help       Show this help'
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / 'config.yaml'
ENTITY_MAP_PATH = REPO_ROOT / 'entity_map.yaml'
DASHBOARD_DIR = REPO_ROOT / 'dashboards' / 'general_home_mobile'
HA_BASE_URL = 'http://homeassistant.local:8123'

FILE_MAP = {
  'dashboard.yaml': 'dashboards/general_home_mobile/dashboard.yaml',
  'sensors.yaml':   'template_sensors/general_home_sensors.yaml',
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
  if not ENTITY_MAP_PATH.exists():
    return content
  with open(ENTITY_MAP_PATH) as f:
    entity_map = yaml.safe_load(f) or {}
  for placeholder, real_value in entity_map.get('entities', {}).items():
    content = content.replace(placeholder, real_value)
  for short_id, full_id in entity_map.get('ids', {}).items():
    content = content.replace(short_id, full_id)
  return content


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

    remote_path = rf'{smb_root}\{remote_rel.replace("/", chr(92))}'
    remote_dir = remote_path.rsplit('\\', 1)[0]
    _smb_makedirs(remote_dir)

    try:
      with open(local_path, 'r', encoding='utf-8') as src:
        content = _restore_content(src.read())
      with smbclient.open_file(remote_path, mode='w') as dst:
        dst.write(content)
      uploaded += 1
      LOGGER.info('Synced', extra={'local': local_name, 'remote': remote_rel})
    except OSError as e:
      LOGGER.error('Failed to sync', extra={'file': local_name, 'error': str(e)})

  smbclient.reset_connection_cache()
  return uploaded


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


def main(argv: list[str] | None = None) -> None:
  """
  Sync General Home Mobile dashboard to Home Assistant.

  Uploads dashboard.yaml and template sensors via SMB.
  Use --restart on first deploy or after editing sensors/configuration.

  Example:
    > uv run python general_home_dashboard_sync.py           # sync dashboard only
    > uv run python general_home_dashboard_sync.py -r         # sync + restart HA
    > uv run python general_home_dashboard_sync.py -d         # sync with debug logging
  """
  argv = argv if argv is not None else sys.argv[1:]

  try:
    opts, _ = getopt(argv, 'hdl:r', ['help', 'debug', 'log-level=', 'restart'])
  except GetoptError:
    LOGGER.error('Invalid options. %s', USAGE)
    sys.exit(1)

  do_restart = False
  for opt, arg in opts:
    if opt in ('-h', '--help'):
      print(USAGE)
      sys.exit(0)
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

  if do_restart:
    _restart_ha(cfg['token'])
  else:
    LOGGER.info('Dashboard YAML reloads automatically on next page visit')


if __name__ == '__main__':
  main(sys.argv[1:])
