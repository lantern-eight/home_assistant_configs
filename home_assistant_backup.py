import fnmatch
import logging
import os
import re
import shutil
import sys
from getopt import GetoptError, getopt
from pathlib import Path

import smbclient
import yaml

from utils import LOGGER

USAGE = (
    'Usage: uv run python home_assistant_backup.py [-d] [-l LEVEL] [-r] [-h]\n'
    '  -d, --debug      Set log level to DEBUG\n'
    '  -l, --log-level  Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)\n'
    '  -r, --restore    Restore redacted files using entity_map.yaml\n'
    '  -h, --help       Show this help'
)

CONFIG_PATH = Path(__file__).resolve().parent / 'config.yaml'
ENTITY_MAP_PATH = Path(__file__).resolve().parent / 'entity_map.yaml'


def _load_config() -> dict:
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
            'redact_names': raw.get('redact_names', []),
        }
    return {
        'smb_server': os.environ.get('SMB_SERVER', ''),
        'smb_share': os.environ.get('SMB_SHARE', ''),
        'smb_path': os.environ.get('SMB_PATH', ''),
        'smb_user': os.environ.get('SMB_USER', ''),
        'smb_password': os.environ.get('SMB_PASSWORD', ''),
        'redact_names': [],
    }


def _normalize_redact_names(names):
    """Normalize redact_names from config: None -> [], str -> [str], list unchanged."""
    if names is None:
        return []
    if isinstance(names, str):
        return [names]
    return names


_cfg = _load_config()
SMB_SERVER = _cfg['smb_server']
SMB_SHARE = _cfg['smb_share']
SMB_PATH = _cfg['smb_path']
SMB_USER = _cfg['smb_user']
SMB_PASSWORD = _cfg['smb_password']
REDACT_NAMES = _normalize_redact_names(_cfg.get('redact_names', []))

DEST = os.path.join(os.getcwd(), 'home_assistant_backup')
COMMENTS_DIR = os.path.join(os.getcwd(), 'home_assistant_backup_comments')

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


PROCESSABLE_EXTENSIONS = ('.yaml', '.json', '.conf', '.txt')

_ID_PATTERN = re.compile(r'\b([0-9a-fA-F]{32})\b')

PRONOUN_MAP = [
    (r"\bhe\b",    "they"),
    (r"\bhim\b",   "them"),
    (r"\bhis\b",   "their"),
    (r"\bshe\b",   "they"),
    (r"\bher\b",   "them"),
    (r"\bhers\b",  "theirs"),
]


def shorten_ids(content: str, id_map: dict | None = None) -> str:
    """Replace 32-char hex IDs with a shortened form (first3...last3)."""
    def _shorten(match):
        s = match.group(1)
        short = f'{s[:3]}...{s[-3:]}'
        if id_map is not None:
            id_map[short] = s
        return short
    return _ID_PATTERN.sub(_shorten, content)


def redact_names_in_text(content: str, names: list[str], name_map: dict | None = None) -> str:
    """Replace each name in *names* with '<entity_N>' (case-insensitive, numbered)."""
    for i, name in enumerate(names, 1):
        if name and len(name.strip()) > 0:
            placeholder = f'<entity_{i}>'
            if name_map is not None:
                name_map[placeholder] = name
            content = re.sub(re.escape(name), placeholder, content, flags=re.IGNORECASE)
    return content


def neutralize_pronouns(content: str) -> str:
    """Replace gendered pronouns with gender-neutral equivalents."""
    for pattern, replacement in PRONOUN_MAP:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    return content


class _LiteralDumper(yaml.SafeDumper):
    """SafeDumper that uses literal block style (|) for multiline strings."""


def _literal_str_representer(dumper, data):
    if '\n' in data:
        # PyYAML refuses literal block style when any line has trailing whitespace;
        # strip it since trailing spaces in Jinja2 templates are insignificant.
        cleaned = '\n'.join(line.rstrip() for line in data.split('\n'))
        return dumper.represent_scalar('tag:yaml.org,2002:str', cleaned, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


_LiteralDumper.add_representer(str, _literal_str_representer)


def normalize_yaml_escapes(content: str) -> str:
    """Round-trip YAML to convert escape sequences (e.g. \\n) to actual characters."""
    if '\\n' not in content:
        return content
    try:
        parsed = yaml.safe_load(content)
        if parsed is None:
            return content
        return yaml.dump(parsed, default_flow_style=False, allow_unicode=True, sort_keys=False, Dumper=_LiteralDumper)
    except yaml.YAMLError:
        return content


def save_entity_map(entity_map: dict, path: Path | str = ENTITY_MAP_PATH) -> None:
    """Write the entity map to a YAML file."""
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(entity_map, f, default_flow_style=False, sort_keys=True)
    LOGGER.info('Entity map saved', extra={'path': str(path)})


def load_entity_map(path: Path | str = ENTITY_MAP_PATH) -> dict:
    """Read the entity map from a YAML file."""
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    return {'ids': data.get('ids', {}), 'names': data.get('names', {})}


def _process_backup_files(
    dest_dir: str,
    redact_names: list[str],
    entity_map: dict | None = None,
) -> None:
    """Post-process backup files to redact sensitive info and shorten IDs."""
    LOGGER.info('Starting post-processing of backup files', extra={'redact_count': len(redact_names)})

    id_map = entity_map['ids'] if entity_map is not None else None
    name_map = entity_map['names'] if entity_map is not None else None

    for root, _, files in os.walk(dest_dir):
        for file in files:
            if not file.endswith(PROCESSABLE_EXTENSIONS):
                continue
            
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original = content
                content = shorten_ids(content, id_map)
                content = redact_names_in_text(content, redact_names, name_map)
                content = neutralize_pronouns(content)
                if file.endswith('.yaml'):
                    content = normalize_yaml_escapes(content)
                
                if content != original:
                     with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
            except Exception as e:
                LOGGER.warning(
                    'Failed to process file',
                    extra={'file': file_path, 'error': str(e)}
                )


def _restore_backup_files(dest_dir: str, entity_map: dict) -> None:
    """Reverse redaction in backup files using a previously saved entity map."""
    names = entity_map.get('names', {})
    ids = entity_map.get('ids', {})
    LOGGER.info(
        'Starting restore of backup files',
        extra={'name_count': len(names), 'id_count': len(ids)},
    )

    for root, _, files in os.walk(dest_dir):
        for file in files:
            if not file.endswith(PROCESSABLE_EXTENSIONS):
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                original = content
                for placeholder, real_name in names.items():
                    content = content.replace(placeholder, real_name)
                for short_id, full_id in ids.items():
                    content = content.replace(short_id, full_id)

                if content != original:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)

            except Exception as e:
                LOGGER.warning(
                    'Failed to restore file',
                    extra={'file': file_path, 'error': str(e)},
                )


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
    opts, _ = getopt(argv, 'hdl:r', ['help', 'debug', 'log-level=', 'restore'])
  except GetoptError:
    LOGGER.error('Invalid options. %s', USAGE)
    sys.exit(1)

  restore_mode = False
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
    if opt in ('-r', '--restore'):
      restore_mode = True

  if restore_mode:
    if not ENTITY_MAP_PATH.exists():
      LOGGER.error('entity_map.yaml not found at %s — run a backup first', ENTITY_MAP_PATH)
      sys.exit(1)
    entity_map = load_entity_map(ENTITY_MAP_PATH)
    _restore_backup_files(DEST, entity_map)
    if os.path.isdir(COMMENTS_DIR):
      _restore_backup_files(COMMENTS_DIR, entity_map)
    LOGGER.info('Restore complete')
    return

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

  # Post-process files (redaction + ID shortening) and build entity map
  entity_map = {'ids': {}, 'names': {}}
  _process_backup_files(DEST, REDACT_NAMES, entity_map)
  if os.path.isdir(COMMENTS_DIR):
    _process_backup_files(COMMENTS_DIR, REDACT_NAMES, entity_map)
  if entity_map['ids'] or entity_map['names']:
    save_entity_map(entity_map, ENTITY_MAP_PATH)

  smbclient.reset_connection_cache()
  LOGGER.info(
    'Backup finished; connection cache reset',
    extra={'files_copied': files_copied, 'dest': os.path.abspath(DEST)},
  )


if __name__ == '__main__':
  main(sys.argv[1:])
