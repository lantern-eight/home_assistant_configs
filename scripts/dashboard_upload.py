import logging
import os
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import requests
import smbclient
import yaml

from utils import LOGGER

USAGE = (
  'Usage: uv run python scripts/dashboard_upload.py [-d] [-l LEVEL] [-n] [-h]\n'
  '  -d, --debug      Set log level to DEBUG\n'
  '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
  '  -n, --no-reload  Skip HA lovelace reload after upload\n'
  '  -h, --help       Show this help'
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / 'config.yaml'
DASHBOARD_DIR = REPO_ROOT / 'dashboards' / 'Material-Design-3-Dynamic-Mobile-Dashboard'
HA_BASE_URL = 'http://homeassistant.local:8123'

UPLOAD_FILES = [
  'dashboard.yaml',
]

UPLOAD_SKIP = {
  'MY_CUSTOMIZATIONS.md',
  '.github',
  'README.md',
  'wallpaper',
  'hue asset',
  'template sensor',
  'assets',
}


def _load_config() -> dict:
  '''Load SMB + token config from config.yaml if present, else from environment.'''
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
  return {
    'smb_server': os.environ.get('SMB_SERVER', ''),
    'smb_share': os.environ.get('SMB_SHARE', ''),
    'smb_path': os.environ.get('SMB_PATH', ''),
    'smb_user': os.environ.get('SMB_USER', ''),
    'smb_password': os.environ.get('SMB_PASSWORD', ''),
    'token': os.environ.get('HA_TOKEN', ''),
  }


def _smb_makedirs(smb_path: str) -> None:
  '''Recursively create SMB directories (like os.makedirs).'''
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


def _upload_dashboard(cfg: dict) -> int:
  '''Upload dashboard files to HA via SMB. Returns count of files uploaded.'''
  smb_server = cfg['smb_server']
  smb_share = cfg['smb_share']
  smb_path = cfg['smb_path']
  smb_user = cfg['smb_user']
  smb_password = cfg['smb_password']

  if not smb_server or not smb_share:
    LOGGER.error(
      'Set smb_server and smb_share in config.yaml (copy from config.example.yaml) '
      'or set SMB_SERVER and SMB_SHARE environment variables.'
    )
    sys.exit(1)

  smb_root = rf'\\{smb_server}\{smb_share}'
  if smb_path:
    smb_root = rf'{smb_root}\{smb_path.strip("/").replace("/", chr(92))}'

  smbclient.ClientConfig(username=smb_user or None, password=smb_password or None)
  smbclient.register_session(
    smb_server,
    username=smb_user or None,
    password=smb_password or None,
  )
  LOGGER.info('SMB session registered', extra={'smb_root': smb_root})

  remote_dashboard_dir = rf'{smb_root}\dashboards\Material-Design-3-Dynamic-Mobile-Dashboard'
  _smb_makedirs(remote_dashboard_dir)

  files_uploaded = 0
  for local_file in UPLOAD_FILES:
    local_path = DASHBOARD_DIR / local_file
    if not local_path.exists():
      LOGGER.warning('Local file not found, skipping', extra={'file': str(local_path)})
      continue

    remote_path = rf'{remote_dashboard_dir}\{local_file}'
    try:
      with open(local_path, 'rb') as src:
        with smbclient.open_file(remote_path, mode='wb') as dst:
          dst.write(src.read())
      files_uploaded += 1
      LOGGER.info('Uploaded', extra={'local': str(local_path), 'remote': remote_path})
    except OSError as e:
      LOGGER.error('Failed to upload', extra={'file': local_file, 'error': str(e)})

  smbclient.reset_connection_cache()
  return files_uploaded


def _reload_lovelace(token: str) -> bool:
  '''Call HA API to reload lovelace resources.'''
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping lovelace reload')
    return False

  headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
  try:
    resp = requests.post(
      f'{HA_BASE_URL}/api/services/lovelace/reload_resources',
      headers=headers,
      timeout=15,
    )
    if resp.status_code == 200:
      LOGGER.info('Lovelace resources reloaded')
      return True
    LOGGER.warning('Lovelace reload response', extra={'status': resp.status_code, 'body': resp.text})
    return False
  except requests.RequestException as e:
    LOGGER.warning('Failed to reload lovelace', extra={'error': str(e)})
    return False


def main(argv: list[str] | None = None) -> None:
  '''
  Upload the MD3 dashboard to Home Assistant via SMB.

  Example usage:
    > uv run python dashboard_upload.py
    > uv run python dashboard_upload.py -d
    > uv run python dashboard_upload.py -n   # skip reload
  '''
  argv = argv if argv is not None else sys.argv[1:]

  try:
    opts, _ = getopt(argv, 'hdl:n', ['help', 'debug', 'log-level=', 'no-reload'])
  except GetoptError:
    LOGGER.error('Invalid options. %s', USAGE)
    sys.exit(1)

  skip_reload = False
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
    if opt in ('-n', '--no-reload'):
      skip_reload = True

  if not DASHBOARD_DIR.exists():
    LOGGER.error('Dashboard directory not found at %s', DASHBOARD_DIR)
    sys.exit(1)

  cfg = _load_config()

  LOGGER.info('Uploading dashboard files via SMB')
  count = _upload_dashboard(cfg)
  LOGGER.info('Upload complete', extra={'files_uploaded': count})

  if not skip_reload:
    _reload_lovelace(cfg['token'])
  else:
    LOGGER.info('Skipping lovelace reload (--no-reload)')


if __name__ == '__main__':
  main(sys.argv[1:])
