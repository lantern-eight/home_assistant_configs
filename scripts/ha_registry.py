"""Shared logic for applying HA registry metadata (labels + categories) via WebSocket."""

import json
from pathlib import Path

import yaml

from utils import LOGGER

try:
  from websockets.sync.client import connect as ws_connect
  HAS_WEBSOCKETS = True
except ImportError:
  HAS_WEBSOCKETS = False

HA_BASE_URL = 'http://homeassistant.local:8123'


def restore_content(content: str, entity_map_path: Path) -> str:
  """Replace redacted <entity_N> placeholders with real values."""
  if not entity_map_path.exists():
    return content
  with open(entity_map_path) as f:
    entity_map = yaml.safe_load(f) or {}
  for placeholder, real_value in entity_map.get('entities', {}).items():
    content = content.replace(placeholder, real_value)
  for short_id, full_id in entity_map.get('ids', {}).items():
    content = content.replace(short_id, full_id)
  return content


def apply_registry_metadata(metadata_path: Path, token: str, entity_map_path: Path) -> None:
  """Create and assign categories/labels from a registry_metadata.yaml via WebSocket.

  Reads the metadata file, un-redacts entity IDs using entity_map_path,
  then connects to HA's WebSocket API to ensure labels/categories exist
  and assigns them to the listed entities.
  """
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

  entities_resolved = {}
  for entity_id, props in entities_def.items():
    entities_resolved[restore_content(entity_id, entity_map_path)] = props

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
