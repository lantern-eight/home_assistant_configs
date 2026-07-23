"""Apply general HA registry metadata (labels + categories) via WebSocket.

Reads registry_metadata.yaml from the repo root and pushes labels, categories,
and entity assignments to Home Assistant. Separate from the dashboard sync
script because these labels are general-purpose (not dashboard-specific).
"""

import sys

from ha_registry import apply_registry_metadata
from utils import (
  ENTITY_MAP_PATH,
  LOGGER,
  REPO_ROOT,
  apply_log_level,
  base_arg_parser,
  load_config,
)

METADATA_PATH = REPO_ROOT / 'registry_metadata.yaml'


def main(argv: list[str] | None = None) -> None:
  parser = base_arg_parser(
    'Apply general HA registry metadata (labels + categories) via WebSocket.'
  )
  args = parser.parse_args(argv if argv is not None else sys.argv[1:])
  apply_log_level(args)

  cfg = load_config()
  LOGGER.info('Applying general registry metadata')
  apply_registry_metadata(METADATA_PATH, cfg['token'], ENTITY_MAP_PATH)


if __name__ == '__main__':
  main(sys.argv[1:])
