import json
import logging
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import requests
import yaml

from utils import LOGGER

USAGE = (
  'Usage: uv run python ha_entity_discovery.py [-d] [-l LEVEL] [-h]\n'
  '  -d, --debug      Set log level to DEBUG\n'
  '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
  '  -h, --help       Show this help'
)

CONFIG_PATH = Path(__file__).resolve().parent / 'config.yaml'
OUTPUT_PATH = Path(__file__).resolve().parent / 'ha_entities.json'
HA_BASE_URL = 'http://homeassistant.local:8123'


def _load_config() -> dict:
  '''Load HA token from config.yaml if present, else from environment.'''
  if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
      raw = yaml.safe_load(f) or {}
    return {'token': str(raw.get('token', ''))}
  return {'token': os.environ.get('HA_TOKEN', '')}


def _ha_headers(token: str) -> dict:
  return {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def _get_states(token: str) -> list[dict]:
  resp = requests.get(f'{HA_BASE_URL}/api/states', headers=_ha_headers(token), timeout=30)
  resp.raise_for_status()
  return resp.json()


def _render_template(token: str, template: str) -> str:
  resp = requests.post(
    f'{HA_BASE_URL}/api/template',
    headers=_ha_headers(token),
    json={'template': template},
    timeout=30,
  )
  resp.raise_for_status()
  return resp.text


def _get_areas(token: str) -> list[dict]:
  '''Fetch area list with names and entity counts.'''
  template = (
    '['
    '{% for area_id in areas() %}'
    '{"id":"{{ area_id }}",'
    '"name":"{{ area_name(area_id) }}",'
    '"entity_count":{{ area_entities(area_id) | list | length }}}'
    '{% if not loop.last %},{% endif %}'
    '{% endfor %}'
    ']'
  )
  raw = _render_template(token, template)
  return json.loads(raw)


def _get_area_entities(token: str, area_id: str) -> list[str]:
  '''Fetch entity IDs belonging to an area.'''
  template = '{{ area_entities("' + area_id + '") | list | tojson }}'
  raw = _render_template(token, template)
  return json.loads(raw)


def _build_discovery(token: str) -> dict:
  '''Build the full entity discovery structure.'''
  LOGGER.info('Fetching states from HA')
  states = _get_states(token)

  entities_by_id = {}
  for s in states:
    entities_by_id[s['entity_id']] = {
      'entity_id': s['entity_id'],
      'state': s['state'],
      'friendly_name': s['attributes'].get('friendly_name', ''),
      'device_class': s['attributes'].get('device_class', ''),
      'unit': s['attributes'].get('unit_of_measurement', ''),
    }
  LOGGER.info('Fetched entity states', extra={'count': len(entities_by_id)})

  LOGGER.info('Fetching areas from HA')
  areas = _get_areas(token)

  area_details = []
  for area in areas:
    area_entity_ids = _get_area_entities(token, area['id'])
    area_entities = []
    for eid in sorted(area_entity_ids):
      info = entities_by_id.get(eid, {'entity_id': eid})
      area_entities.append(info)
    area_details.append({
      'id': area['id'],
      'name': area['name'],
      'entity_count': area['entity_count'],
      'entities': area_entities,
    })
    LOGGER.debug('Fetched area', extra={'area': area['name'], 'entities': len(area_entities)})

  domain_summary = {}
  for eid in entities_by_id:
    domain = eid.split('.')[0]
    domain_summary[domain] = domain_summary.get(domain, 0) + 1

  return {
    'total_entities': len(entities_by_id),
    'domain_summary': dict(sorted(domain_summary.items())),
    'areas': area_details,
    'all_entities': entities_by_id,
  }


def _print_summary(discovery: dict) -> None:
  '''Print a human-readable summary to stdout.'''
  print(f'\n=== HA Entity Discovery ===')
  print(f'Total entities: {discovery["total_entities"]}')

  print(f'\n--- Domains ---')
  for domain, count in discovery['domain_summary'].items():
    print(f'  {domain}: {count}')

  print(f'\n--- Areas ({len(discovery["areas"])}) ---')
  for area in discovery['areas']:
    print(f'\n  {area["name"]} ({area["id"]}): {area["entity_count"]} entities')
    key_domains = ('light', 'switch', 'climate', 'fan', 'cover', 'camera',
                   'vacuum', 'media_player', 'binary_sensor', 'sensor')
    for entity in area['entities']:
      eid = entity.get('entity_id', '')
      domain = eid.split('.')[0]
      if domain in key_domains:
        name = entity.get('friendly_name', '')
        state = entity.get('state', '')
        print(f'    {eid} | {name} | {state}')


def main(argv: list[str] | None = None) -> None:
  '''
  Discover all entities and areas from a Home Assistant instance and save to JSON.

  Example usage:
    > uv run python ha_entity_discovery.py
    > uv run python ha_entity_discovery.py -d
  '''
  argv = argv if argv is not None else sys.argv[1:]

  try:
    opts, _ = getopt(argv, 'hdl:', ['help', 'debug', 'log-level='])
  except GetoptError:
    LOGGER.error('Invalid options. %s', USAGE)
    sys.exit(1)

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

  cfg = _load_config()
  token = cfg['token']
  if not token or token == 'your_token_here':
    LOGGER.error('No valid HA token found. Set token in config.yaml or HA_TOKEN env var.')
    sys.exit(1)

  LOGGER.info('Starting entity discovery', extra={'ha_url': HA_BASE_URL})

  try:
    discovery = _build_discovery(token)
  except requests.RequestException as e:
    LOGGER.error('Failed to connect to HA', extra={'error': str(e)})
    sys.exit(1)

  with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    json.dump(discovery, f, indent=2, ensure_ascii=False)
  LOGGER.info('Discovery saved', extra={'path': str(OUTPUT_PATH)})

  _print_summary(discovery)


if __name__ == '__main__':
  main(sys.argv[1:])
