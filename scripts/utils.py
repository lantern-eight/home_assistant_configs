"""Shared utilities for Home Assistant config sync scripts.

Provides logging, configuration, SMB session management, HA service calls,
and argument parsing used across all repo scripts.
"""

import argparse
import logging
import os
import sys
from logging import Logger
from pathlib import Path

import requests
import smbclient
import yaml
from pythonjsonlogger import jsonlogger

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
  """StreamHandler that colorizes the formatted log line by level when stream is a TTY."""

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
  """Create and return a logger with JSON formatter and optional TTY coloring."""
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
  """Load configuration from config.yaml.

  Returns a dict with smb_server, smb_share, smb_path, smb_user,
  smb_password, token, redact_entities, and ha_base_url.

  With allow_env_fallback=True, falls back to environment variables
  if config.yaml is missing (used by the backup script for CI-style runs).
  Otherwise, exits with an error message.
  """
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
  """Create an ArgumentParser with the shared -d/--debug and -l/--log-level flags."""
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
  """Apply the log level from parsed arguments to the shared logger."""
  if args.debug:
    LOGGER.setLevel(logging.DEBUG)
  elif args.log_level:
    LOGGER.setLevel(getattr(logging, args.log_level))

# ---------------------------------------------------------------------------
# SMB session management
# ---------------------------------------------------------------------------


def open_smb_session(cfg: dict) -> str:
  """Register an SMB session and return the computed smb_root UNC path.

  Validates that smb_server and smb_share are set, constructs the UNC path,
  and registers the SMB session. Exits on missing server/share.
  """
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
  """POST to an HA service endpoint. Returns True on success."""
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
  """Restart Home Assistant via the REST API."""
  LOGGER.info('Restarting Home Assistant...')
  if call_ha_service(token, 'homeassistant', 'restart', ha_base_url=ha_base_url):
    LOGGER.info('HA restart triggered — dashboard will reload on next visit')
    return True
  return False
