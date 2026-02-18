import fnmatch
import logging
import os
import shutil
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import smbclient
import yaml

from utils import LOGGER

USAGE = (
    'Usage: uv run python home_assistant_backup.py [-d] [-l LEVEL] [-h]\n'
    '  -d, --debug      Set log level to DEBUG\n'
    '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
    '  -h, --help       Show this help'
)

CONFIG_PATH = Path(__file__).resolve().parent / 'config.yaml'


def _load_config() -> dict[str, str]:
    """Load SMB config from config.yaml if present, else from environment."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            raw = yaml.safe_load(f) or {}
        return {
            'smb_server': str(raw.get('smb_server', '')),
            'smb_share': str(raw.get('smb_share', '')),
            'smb_path': str(raw.get('smb_path', '')),
            'smb_user': str(raw.get('smb_user', '')),
            'smb_password': str(raw.get('smb_password', '')),
        }
    return {
        'smb_server': os.environ.get('SMB_SERVER', ''),
        'smb_share': os.environ.get('SMB_SHARE', ''),
        'smb_path': os.environ.get('SMB_PATH', ''),
        'smb_user': os.environ.get('SMB_USER', ''),
        'smb_password': os.environ.get('SMB_PASSWORD', ''),
    }


_cfg = _load_config()
SMB_SERVER = _cfg['smb_server']
SMB_SHARE = _cfg['smb_share']
SMB_PATH = _cfg['smb_path']
SMB_USER = _cfg['smb_user']
SMB_PASSWORD = _cfg['smb_password']

DEST = os.path.join(os.getcwd(), 'home_assistant_backup')

IGNORE_PATTERNS = [
  '*.db',
  '*.db-*',
  '*.log',
  '*.log.*',
  '__pycache__',
  '.storage',
  '.cloud',
  'deps',
  'tts',
  'backups',
  '.ha_run.lock',
  '.HA_VERSION',
  'secrets.yaml',
  '*.august.conf',
  'custom_components',
]


def should_ignore(name: str) -> bool:
  '''Return True if the file/dir name matches any ignore pattern.'''
  return any(fnmatch.fnmatch(name, p) for p in IGNORE_PATTERNS)


def main(argv: list[str] | None = None) -> None:
  '''
  Backup Home Assistant config from SMB share to /home_assistant_backup directory.

  Example usage:

    > uv run python home_assistant_backup.py
    > uv run python home_assistant_backup.py -d
    > uv run python home_assistant_backup.py -l DEBUG

  Make sure you have filled out config.yaml (copied from config.example.yaml)
  or exported the corresponding environment variables:

    export SMB_SERVER=192.168.1.100
    export SMB_SHARE=config
    export SMB_USER=your_user
    export SMB_PASSWORD=your_password

  The backup will be saved in 'home_assistant_backup' in the current directory.

  Requires: smbprotocol, smbclient

  Args:
    argv: Command line arguments (defaults to sys.argv[1:])
  Returns:
    None
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
      LOGGER.debug('Running in debug mode')
    if opt in ('-l', '--log-level'):
      level = getattr(logging, arg.upper(), None)
      if level is None:
        LOGGER.error('Invalid log level: %s. Use DEBUG, INFO, WARNING, ERROR, or CRITICAL', arg)
        sys.exit(1)
      LOGGER.setLevel(level)
      LOGGER.debug('Log level set to %s', arg.upper())

  if not SMB_SERVER or not SMB_SHARE:
    LOGGER.error(
      'Set smb_server and smb_share in config.yaml (copy from config.example.yaml) '
      'or set SMB_SERVER and SMB_SHARE environment variables.'
    )
    sys.exit(1)
  smb_root = rf'\\{SMB_SERVER}\{SMB_SHARE}'
  if SMB_PATH:
    smb_root = rf'{smb_root}\{SMB_PATH.strip('/').replace('/', chr(92))}'

  smbclient.ClientConfig(username=SMB_USER or None, password=SMB_PASSWORD or None)
  LOGGER.debug(
    f"SMB_SERVER='{SMB_SERVER}', type={type(SMB_SERVER)}",
    extra={'SMB_SERVER': SMB_SERVER, 'type': str(type(SMB_SERVER))}
  )
  smbclient.register_session(
    SMB_SERVER,
    username=SMB_USER or None,
    password=SMB_PASSWORD or None,
  )
  LOGGER.info(
    'SMB session registered; backing up to local path',
    extra={'smb_root': smb_root, 'dest': os.path.abspath(DEST)},
  )

  if os.path.exists(DEST):
    LOGGER.info('Removing existing backup directory', extra={'path': DEST})
    shutil.rmtree(DEST)

  root_len = len(smb_root.rstrip('\\')) + 1  # +1 for trailing backslash

  files_copied = 0
  LOGGER.info('Starting walk of SMB share', extra={'smb_root': smb_root})
  for directory_path, directory_names, file_names in smbclient.walk(smb_root):
    # Prune ignored directories (modify in-place)
    directory_names[:] = [d for d in directory_names if not should_ignore(d)]

    relative_directory = \
      directory_path[root_len:].replace('\\', os.sep) \
      if len(directory_path) > root_len \
      else ''

    local_directory = \
      os.path.join(DEST, relative_directory) if relative_directory else DEST

    for file_name in file_names:
      if should_ignore(file_name):
        continue

      smb_file = f'{directory_path}\\{file_name}'
      local_file = os.path.join(local_directory, file_name)

      os.makedirs(local_directory, exist_ok=True)

      try:
        with smbclient.open_file(smb_file, mode='rb') as src:
          with open(local_file, 'wb') as dst:
            dst.write(src.read())
        files_copied += 1
      except OSError as e:
        LOGGER.warning(
          'Failed to copy file',
          extra={'smb_file': smb_file, 'local_file': local_file, 'error': str(e)},
        )

  smbclient.reset_connection_cache()
  LOGGER.info(
    'Backup finished; connection cache reset',
    extra={'files_copied': files_copied, 'dest': os.path.abspath(DEST)},
  )


if __name__ == '__main__':
  main(sys.argv[1:])
