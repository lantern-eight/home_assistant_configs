"""Sync General Home Mobile dashboard and sensors to Home Assistant via SMB."""

import json
import logging
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import requests
import smbclient
import yaml

from utils import LOGGER

try:
  from websockets.sync.client import connect as ws_connect
  HAS_WEBSOCKETS = True
except ImportError:
  HAS_WEBSOCKETS = False

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
SCRIPTS_DIR = REPO_ROOT / 'scripts'
HA_BASE_URL = 'http://homeassistant.local:8123'

FILE_MAP = {
  'dashboard.yaml': 'dashboards/general_home_mobile/dashboard.yaml',
  'sensors.yaml':   'template_sensors/general_home_sensors.yaml',
  'theme_sensors.yaml': 'template_sensors/theme_sensors.yaml',
  'general_home_mobile.yaml': 'packages/general_home_mobile.yaml',
  'popup_history_fix.js': 'www/popup_history_fix.js',
}

SCRIPT_MAP = {
  'generate_theme_thumbnails.py': 'scripts/generate_theme_thumbnails.py',
  'list_theme_backgrounds.py': 'scripts/list_theme_backgrounds.py',
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

  for local_name, remote_rel in SCRIPT_MAP.items():
    local_path = SCRIPTS_DIR / local_name
    if not local_path.exists():
      LOGGER.warning('Local script missing, skipping', extra={'file': str(local_path)})
      continue

    remote_path = rf'{smb_root}\{remote_rel.replace("/", chr(92))}'
    remote_dir = remote_path.rsplit('\\', 1)[0]
    _smb_makedirs(remote_dir)

    try:
      with open(local_path, 'r', encoding='utf-8') as src:
        content = src.read()
      with smbclient.open_file(remote_path, mode='w') as dst:
        dst.write(content)
      uploaded += 1
      LOGGER.info('Synced script', extra={'local': local_name, 'remote': remote_rel})
    except OSError as e:
      LOGGER.error('Failed to sync script', extra={'file': local_name, 'error': str(e)})

  smbclient.reset_connection_cache()
  return uploaded


def _reload_services(token: str) -> None:
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping service reloads')
    return
  headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
  for service in ('template/reload', 'command_line/reload'):
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
  """Create and assign categories/labels from registry_metadata.yaml via WebSocket."""
  if not HAS_WEBSOCKETS:
    LOGGER.error('websockets library required for -c flag: run `uv sync`')
    sys.exit(1)

  metadata_path = DASHBOARD_DIR / 'registry_metadata.yaml'
  if not metadata_path.exists():
    LOGGER.warning('registry_metadata.yaml not found, skipping category/label sync')
    return

  with open(metadata_path) as f:
    metadata = yaml.safe_load(f) or {}

  categories_def = metadata.get('categories', {})
  labels_def = metadata.get('labels', {})
  entities_def = metadata.get('entities', {})

  if not entities_def:
    LOGGER.info('No entities in registry_metadata.yaml, skipping')
    return

  entities_resolved = {}
  for entity_id, props in entities_def.items():
    entities_resolved[_restore_content(entity_id)] = props

  token = cfg['token']
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping category/label sync')
    return

  ws_uri = HA_BASE_URL.replace('http', 'ws', 1) + '/api/websocket'
  msg_id = 0

  def send_cmd(ws, cmd):
    nonlocal msg_id
    msg_id += 1
    cmd['id'] = msg_id
    ws.send(json.dumps(cmd))
    resp = json.loads(ws.recv())
    while resp.get('id') != msg_id:
      resp = json.loads(ws.recv())
    if not resp.get('success', True):
      LOGGER.warning('WS command failed', extra={'cmd': cmd.get('type'), 'error': resp.get('error')})
    return resp

  with ws_connect(ws_uri) as ws:
    auth_req = json.loads(ws.recv())
    if auth_req.get('type') != 'auth_required':
      LOGGER.error('Unexpected WS response: %s', auth_req.get('type'))
      return
    ws.send(json.dumps({'type': 'auth', 'access_token': token}))
    auth_resp = json.loads(ws.recv())
    if auth_resp.get('type') != 'auth_ok':
      LOGGER.error('WS auth failed: %s', auth_resp)
      return
    LOGGER.info('WebSocket authenticated')

    existing_labels = send_cmd(ws, {'type': 'config/label_registry/list'})
    label_map = {l['name']: l['label_id'] for l in (existing_labels.get('result') or [])}
    for name, props in labels_def.items():
      if name not in label_map:
        resp = send_cmd(ws, {
          'type': 'config/label_registry/create',
          'name': name,
          'color': props.get('color', 'grey'),
          'icon': props.get('icon', ''),
        })
        if resp.get('success'):
          label_map[name] = resp['result']['label_id']
          LOGGER.info('Created label', extra={'label': name})
      else:
        LOGGER.debug('Label exists', extra={'label': name})

    scopes = set()
    for props in categories_def.values():
      scopes.add(props.get('scope', 'helpers'))
    cat_map = {}
    for scope in scopes:
      existing = send_cmd(ws, {'type': 'config/category_registry/list', 'scope': scope})
      for c in (existing.get('result') or []):
        cat_map[(scope, c['name'])] = c['category_id']
    for name, props in categories_def.items():
      scope = props.get('scope', 'helpers')
      if (scope, name) not in cat_map:
        resp = send_cmd(ws, {
          'type': 'config/category_registry/create',
          'scope': scope,
          'name': name,
          'icon': props.get('icon', ''),
        })
        if resp.get('success'):
          cat_map[(scope, name)] = resp['result']['category_id']
          LOGGER.info('Created category', extra={'category': name, 'scope': scope})
      else:
        LOGGER.debug('Category exists', extra={'category': name})

    for entity_id, props in entities_resolved.items():
      label_ids = [label_map[l] for l in props.get('labels', []) if l in label_map]
      update_cmd = {
        'type': 'config/entity_registry/update',
        'entity_id': entity_id,
        'labels': label_ids,
      }
      entity_cat = props.get('category', '')
      if entity_cat:
        domain = entity_id.split('.')[0]
        scope = 'helpers' if domain.startswith('input_') else domain
        cat_id = cat_map.get((scope, entity_cat))
        if cat_id:
          update_cmd['categories'] = {scope: cat_id}
      resp = send_cmd(ws, update_cmd)
      if resp.get('success'):
        LOGGER.info('Updated entity metadata', extra={'entity': entity_id})
      else:
        LOGGER.warning('Failed to update entity', extra={
          'entity': entity_id, 'error': resp.get('error'),
        })

  LOGGER.info('Category/label sync complete')


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
