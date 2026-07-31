'''Shared utilities for Home Assistant config sync scripts.

Provides logging, configuration, SMB session management, HA service calls,
entity map restore, registry metadata sync, and argument parsing used
across all repo scripts.
'''

import argparse
import json
import logging
import os
import sys
from logging import Logger
from pathlib import Path

import requests
import smbclient
import yaml
from pythonjsonlogger import jsonlogger

try:
  from websockets.sync.client import connect as ws_connect
  HAS_WEBSOCKETS = True
except ImportError:
  HAS_WEBSOCKETS = False

# ---------------------------------------------------------------------------
# ANSI escape codes for level-based coloring (when stdout is a TTY)
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_DIM = "\033[2m"

_LEVEL_COLORS = {
  logging.CRITICAL: _RED,
  logging.ERROR: _RED,
  logging.WARNING: _YELLOW,
  logging.INFO: _GREEN,
  logging.DEBUG: _DIM,
}


class ColoredStreamHandler(logging.StreamHandler):
  '''StreamHandler that colorizes the formatted log line by level when stream is a TTY.'''

  def __init__(self, stream=None):
    super().__init__(stream or sys.stdout)

  def emit(self, record: logging.LogRecord) -> None:
    try:
      msg = self.format(record)
      if self.stream and getattr(self.stream, "isatty", lambda: False)():
        color = _LEVEL_COLORS.get(record.levelno, _RESET)
        msg = f"{color}{msg}{_RESET}"
      if self.stream:
        self.stream.write(msg + self.terminator)
        self.flush()
    except Exception:
      self.handleError(record)


def init_logger() -> Logger:
  '''Create and return a logger with JSON formatter and optional TTY coloring.'''
  log_format = (
    "%(asctime)s %(levelname)s %(name)s %(message)s "
    "%(filename)s %(funcName)s %(lineno)d"
  )
  logger = logging.getLogger("ha_backup")
  level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
  logger.setLevel(getattr(logging, level_name, logging.INFO))

  console_handler = ColoredStreamHandler(sys.stdout)
  formatter = jsonlogger.JsonFormatter(log_format)
  console_handler.setFormatter(formatter)
  logger.addHandler(console_handler)

  return logger


LOGGER = init_logger()

# ---------------------------------------------------------------------------
# Shared path constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / 'config.yaml'
ENTITY_MAP_PATH = REPO_ROOT / 'entity_map.yaml'
HA_BASE_URL = 'http://homeassistant.local:8123'

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def load_config(*, allow_env_fallback=False) -> dict:
  '''Load configuration from config.yaml.

  Returns a dict with smb_server, smb_share, smb_path, smb_user,
  smb_password, token, redact_entities, and ha_base_url.

  With allow_env_fallback=True, falls back to environment variables
  if config.yaml is missing (used by the backup script for CI-style runs).
  Otherwise, exits with an error message.
  '''
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
      'redact_entities': raw.get('redact_entities', []),
      'ha_base_url': str(raw.get('ha_base_url', HA_BASE_URL)),
    }
  if allow_env_fallback:
    return {
      'smb_server': os.environ.get('SMB_SERVER', ''),
      'smb_share': os.environ.get('SMB_SHARE', ''),
      'smb_path': os.environ.get('SMB_PATH', ''),
      'smb_user': os.environ.get('SMB_USER', ''),
      'smb_password': os.environ.get('SMB_PASSWORD', ''),
      'token': os.environ.get('HA_TOKEN', ''),
      'redact_entities': [],
      'ha_base_url': os.environ.get('HA_BASE_URL', HA_BASE_URL),
    }
  LOGGER.error('config.yaml not found — copy from config.example.yaml and fill in values')
  sys.exit(1)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def base_arg_parser(description: str) -> argparse.ArgumentParser:
  '''Create an ArgumentParser with the shared -d/--debug and -l/--log-level flags.'''
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument(
    '-d', '--debug', action='store_true',
    help='Set log level to DEBUG',
  )
  parser.add_argument(
    '-l', '--log-level', dest='log_level',
    choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
    help='Set log level',
  )
  return parser


def apply_log_level(args) -> None:
  '''Apply the log level from parsed arguments to the shared logger.'''
  if args.debug:
    LOGGER.setLevel(logging.DEBUG)
  elif args.log_level:
    LOGGER.setLevel(getattr(logging, args.log_level))

# ---------------------------------------------------------------------------
# SMB session management
# ---------------------------------------------------------------------------


def open_smb_session(cfg: dict) -> str:
  '''Register an SMB session and return the computed smb_root UNC path.

  Validates that smb_server and smb_share are set, constructs the UNC path,
  and registers the SMB session. Exits on missing server/share.
  '''
  smb_server = cfg['smb_server']
  smb_share = cfg['smb_share']
  smb_path = cfg['smb_path']

  if not smb_server or not smb_share:
    LOGGER.error('Set smb_server and smb_share in config.yaml')
    sys.exit(1)

  smb_root = rf'\\{smb_server}\{smb_share}'
  if smb_path:
    smb_subpath = smb_path.strip("/").replace("/", "\\")
    smb_root = rf'{smb_root}\{smb_subpath}'

  smbclient.ClientConfig(username=cfg['smb_user'] or None, password=cfg['smb_password'] or None)
  smbclient.register_session(
    smb_server,
    username=cfg['smb_user'] or None,
    password=cfg['smb_password'] or None,
  )
  LOGGER.info('SMB session registered', extra={'smb_root': smb_root})
  return smb_root

# ---------------------------------------------------------------------------
# HA service calls
# ---------------------------------------------------------------------------


def call_ha_service(token: str, domain: str, service: str, *,
                    ha_base_url: str = HA_BASE_URL, timeout: int = 30) -> bool:
  '''POST to an HA service endpoint. Returns True on success.'''
  if not token or token == 'your_token_here':
    LOGGER.warning('No valid HA token; skipping %s/%s', domain, service)
    return False
  headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
  try:
    resp = requests.post(
      f'{ha_base_url}/api/services/{domain}/{service}',
      headers=headers,
      timeout=timeout,
    )
    if resp.status_code == 200:
      return True
    LOGGER.warning(
      'Service call failed',
      extra={'service': f'{domain}/{service}', 'status': resp.status_code},
    )
    return False
  except requests.RequestException as e:
    LOGGER.warning(
      'Service call error',
      extra={'service': f'{domain}/{service}', 'error': str(e)},
    )
    return False


def restart_ha(token: str, *, ha_base_url: str = HA_BASE_URL) -> bool:
  '''Restart Home Assistant via the REST API.'''
  LOGGER.info('Restarting Home Assistant...')
  if call_ha_service(token, 'homeassistant', 'restart', ha_base_url=ha_base_url):
    LOGGER.info('HA restart triggered — dashboard will reload on next visit')
    return True
  return False

# ---------------------------------------------------------------------------
# Entity map restore
# ---------------------------------------------------------------------------


def restore_content(content: str, entity_map_path: Path = None, *,
                    entity_map: dict = None) -> str:
  '''Replace redacted <entity_N> placeholders with real values.

  Pass entity_map_path to load from disk, or entity_map as a pre-parsed
  dict to avoid repeated file I/O across multiple calls.
  '''
  if entity_map is None:
    if entity_map_path is None or not entity_map_path.exists():
      return content
    with open(entity_map_path) as f:
      entity_map = yaml.safe_load(f) or {}
  for placeholder, real_value in entity_map.get('entities', {}).items():
    content = content.replace(placeholder, real_value)
  for short_id, full_id in entity_map.get('ids', {}).items():
    content = content.replace(short_id, full_id)
  return content

# ---------------------------------------------------------------------------
# Registry metadata (labels + categories) via WebSocket
# ---------------------------------------------------------------------------


def apply_registry_metadata(metadata_path: Path, token: str, entity_map_path: Path) -> None:
  '''Create and assign categories/labels from a registry_metadata.yaml via WebSocket.

  Reads the metadata file, un-redacts entity IDs using entity_map_path,
  then connects to HA's WebSocket API to ensure labels/categories exist
  and assigns them to the listed entities.
  '''
  if not HAS_WEBSOCKETS:
    LOGGER.error('websockets library required: run `uv sync`')
    return

  if not metadata_path.exists():
    LOGGER.warning('Registry metadata file not found', extra={'path': str(metadata_path)})
    return

  with open(metadata_path) as f:
    metadata = yaml.safe_load(f) or {}

  categories_def = metadata.get('categories', {})
  labels_def = metadata.get('labels', {})
  entities_def = metadata.get('entities', {})

  if not entities_def:
    LOGGER.info('No entities in metadata file, skipping', extra={'path': str(metadata_path)})
    return

  parsed_entity_map = {}
  if entity_map_path and entity_map_path.exists():
    with open(entity_map_path) as f:
      parsed_entity_map = yaml.safe_load(f) or {}

  entities_resolved = {}
  for entity_id, props in entities_def.items():
    entities_resolved[restore_content(entity_id, entity_map=parsed_entity_map)] = props

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

  LOGGER.info('Category/label sync complete', extra={'file': metadata_path.name})
