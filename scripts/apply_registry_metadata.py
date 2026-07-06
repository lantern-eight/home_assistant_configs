"""Apply general HA registry metadata (labels + categories) via WebSocket.

Reads registry_metadata.yaml from the repo root and pushes labels, categories,
and entity assignments to Home Assistant. Separate from the dashboard sync
script because these labels are general-purpose (not dashboard-specific).

Usage:
  uv run python scripts/apply_registry_metadata.py [-d] [-l LEVEL] [-h]
  -d, --debug      Set log level to DEBUG
  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  -h, --help       Show this help
"""

import logging
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import yaml

from ha_registry import apply_registry_metadata
from utils import LOGGER

USAGE = (
  'Usage: uv run python scripts/apply_registry_metadata.py [-d] [-l LEVEL] [-h]\n'
  '  -d, --debug      Set log level to DEBUG\n'
  '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
  '  -h, --help       Show this help'
)

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / 'config.yaml'
ENTITY_MAP_PATH = REPO_ROOT / 'entity_map.yaml'
METADATA_PATH = REPO_ROOT / 'registry_metadata.yaml'


def _load_token() -> str:
  if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
      raw = yaml.safe_load(f) or {}
    return str(raw.get('token', ''))
  LOGGER.error('config.yaml not found — copy from config.example.yaml and fill in values')
  sys.exit(1)


def main(argv: list[str] | None = None) -> None:
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

  token = _load_token()
  LOGGER.info('Applying general registry metadata')
  apply_registry_metadata(METADATA_PATH, token, ENTITY_MAP_PATH)


if __name__ == '__main__':
  main(sys.argv[1:])
