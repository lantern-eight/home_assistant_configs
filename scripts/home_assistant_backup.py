import os
import re
import sys
from pathlib import Path

import smbclient
import yaml

from ha_registry import restore_content
from utils import (
  ENTITY_MAP_PATH,
  LOGGER,
  REPO_ROOT,
  apply_log_level,
  base_arg_parser,
  load_config,
  open_smb_session,
)

_BLUE = '\033[1;34m'
_RESET = '\033[0m'


def _status(msg: str) -> None:
  '''Print a blue status line to stdout (no-op if stdout is not a TTY).'''
  if sys.stdout.isatty():
    print(f'{_BLUE}=> {msg}{_RESET}')
  else:
    print(f'=> {msg}')


DEST = str(REPO_ROOT / 'home_assistant_backup')
DASHBOARDS_DIR = str(REPO_ROOT / 'dashboards')
PACKAGES_DIR = str(REPO_ROOT / 'packages')


def _iter_sanitize_dirs():
  '''Yield local directories that participate in sanitize/restore passes.'''
  for path in (DEST, DASHBOARDS_DIR, PACKAGES_DIR):
    if os.path.isdir(path):
      yield path

BACKUP_FILES = [
  'configuration.yaml',
]


PROCESSABLE_EXTENSIONS = ('.yaml', '.json', '.conf', '.txt', '.jinja')

_ID_PATTERN = re.compile(
  r'\b('
  r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
  r'|[0-9a-fA-F]{32}'
  r')\b'
)

PRONOUN_MAP = [
  (r'\bhe\b',    'they'),
  (r'\bhim\b',   'them'),
  (r'\bhis\b',   'their'),
  (r'\bshe\b',   'they'),
  (r'\bher\b',   'them'),
  (r'\bhers\b',  'theirs'),
]


def _normalize_redact_entities(entities):
  '''Normalize redact_entities from config: None -> [], str -> [str], list unchanged.'''
  if entities is None:
    return []
  if isinstance(entities, str):
    return [entities]
  return entities


def shorten_ids(content: str, id_map: dict | None = None) -> str:
  '''Replace 32-char hex IDs and hyphenated UUIDs with first3...last3.'''
  def _shorten(match):
    s = match.group(1)
    short = f'{s[:3]}...{s[-3:]}'
    if id_map is not None:
      id_map[short] = s
    return short
  return _ID_PATTERN.sub(_shorten, content)


def redact_entities_in_text(content: str, entities: list[str], entities_map: dict | None = None) -> str:
  '''Replace each string in *entities* with a stable '<entity_N>' placeholder.

  If *entities_map* already contains a mapping for a given value (e.g. from a
  previous run loaded off disk), that placeholder is reused so repeated /
  partial sanitize runs and reordering of *entities* stay stable. New values
  pick up the next unused index instead of just enumerating *entities*.
  '''
  # Reverse-lookup of real value (lowercased) -> placeholder, plus the set of
  # already-used <entity_N> indices so we can pick the next free one.
  existing: dict[str, str] = {}
  used_indices: set[int] = set()
  if entities_map is not None:
    for placeholder, real in entities_map.items():
      existing[real.lower()] = placeholder
      m = re.match(r'<entity_(\d+)>$', placeholder)
      if m:
        used_indices.add(int(m.group(1)))

  next_index = 1

  for entity in entities:
    if not entity or not entity.strip():
      while next_index in used_indices:
        next_index += 1
      used_indices.add(next_index)
      next_index += 1
      continue

    placeholder = existing.get(entity.lower())
    if placeholder is None:
      while next_index in used_indices:
        next_index += 1
      placeholder = f'<entity_{next_index}>'
      used_indices.add(next_index)
      existing[entity.lower()] = placeholder
      if entities_map is not None:
        entities_map[placeholder] = entity

    content = re.sub(re.escape(entity), placeholder, content, flags=re.IGNORECASE)

  return content


def neutralize_pronouns(content: str) -> str:
  '''Replace gendered pronouns with gender-neutral equivalents.'''
  for pattern, replacement in PRONOUN_MAP:
    content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
  return content


class _LiteralDumper(yaml.SafeDumper):
  '''SafeDumper that uses literal block style (|) for multiline strings.'''


def _literal_str_representer(dumper, data):
  if '\n' in data:
    # PyYAML refuses literal block style when any line has trailing whitespace;
    # strip it since trailing spaces in Jinja2 templates are insignificant.
    cleaned = '\n'.join(line.rstrip() for line in data.split('\n'))
    return dumper.represent_scalar('tag:yaml.org,2002:str', cleaned, style='|')
  return dumper.represent_scalar('tag:yaml.org,2002:str', data)


_LiteralDumper.add_representer(str, _literal_str_representer)


def normalize_yaml_escapes(content: str) -> str:
  '''Round-trip YAML to restore human-readable multi-line formatting.

  HA storage-mode files (automations, scripts) collapse multi-line
  strings into single lines with escaped newlines on save. This
  round-trips through PyYAML with a literal-block dumper to expand
  them back into readable block-scalar (|) form.

  Only intended for home_assistant_backup/ files; safe_load resolves anchors
  and dump writes the expanded form, destroying YAML aliases.
  '''
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
  '''Write the entity map to a YAML file.'''
  with open(path, 'w', encoding='utf-8') as f:
    yaml.dump(entity_map, f, default_flow_style=False, sort_keys=True)
  LOGGER.info('Entity map saved', extra={'path': str(path)})


def load_entity_map(path: Path | str = ENTITY_MAP_PATH) -> dict:
  '''Read the entity map from a YAML file.'''
  with open(path, 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f) or {}
  return {'ids': data.get('ids', {}), 'entities': data.get('entities', {})}


def _process_backup_files(
  dest_dir: str,
  redact_entities: list[str],
  entity_map: dict | None = None,
  normalize_yaml: bool = True,
) -> None:
  '''Post-process backup files to redact sensitive info and shorten IDs.'''
  LOGGER.info('Starting post-processing of backup files', extra={'redact_count': len(redact_entities)})

  id_map = entity_map['ids'] if entity_map is not None else None
  entities_map = entity_map['entities'] if entity_map is not None else None

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
        content = redact_entities_in_text(content, redact_entities, entities_map)
        content = neutralize_pronouns(content)
        if normalize_yaml and file.endswith('.yaml'):
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
  '''Reverse redaction in backup files using a previously saved entity map.'''
  LOGGER.info(
    'Starting restore of backup files',
    extra={
      'entity_count': len(entity_map.get('entities', {})),
      'id_count': len(entity_map.get('ids', {})),
    },
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
        content = restore_content(content, entity_map=entity_map)

        if content != original:
          with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

      except Exception as e:
        LOGGER.warning(
          'Failed to restore file',
          extra={'file': file_path, 'error': str(e)},
        )


def _run_backup(cfg: dict) -> None:
  '''Pull specific HA config files from the SMB share into DEST.'''
  _status('Starting SMB backup from Home Assistant')
  _status(f'Connecting to SMB share \\\\{cfg["smb_server"]}\\{cfg["smb_share"]}')
  smb_root = open_smb_session(cfg)

  LOGGER.info(
    'Pulling files to local path',
    extra={'smb_root': smb_root, 'dest': os.path.abspath(DEST)},
  )

  os.makedirs(DEST, exist_ok=True)

  files_copied = 0
  _status(f'Pulling {len(BACKUP_FILES)} file(s) from SMB share...')
  LOGGER.info('Pulling specific files', extra={'files': BACKUP_FILES})
  for relative_path in BACKUP_FILES:
    smb_rel = relative_path.replace("/", "\\")
    smb_file = rf'{smb_root}\{smb_rel}'
    local_file = os.path.join(DEST, relative_path)

    os.makedirs(os.path.dirname(local_file), exist_ok=True)

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
  _status(f'Backup complete — {files_copied}/{len(BACKUP_FILES)} files copied to {os.path.abspath(DEST)}')
  LOGGER.info(
    'Backup finished; connection cache reset',
    extra={'files_copied': files_copied, 'total': len(BACKUP_FILES), 'dest': os.path.abspath(DEST)},
  )


def _run_sanitize(redact_entities: list[str]) -> None:
  '''Run the redaction pass over DEST, DASHBOARDS_DIR, and PACKAGES_DIR.

  Loads the existing entity_map.yaml first if it exists so that placeholder
  numbering for already-known strings stays stable. This makes partial /
  repeated sanitize runs safe: real strings already replaced with
  <entity_N> in a file are left alone, and any unredacted occurrences pick
  up the SAME placeholder as before instead of drifting.
  '''
  _status('Starting sanitize / redaction pass')
  entity_map: dict = {'ids': {}, 'entities': {}}
  if ENTITY_MAP_PATH.exists():
    entity_map = load_entity_map(ENTITY_MAP_PATH)
    LOGGER.info(
      'Loaded existing entity_map for stable placeholder reuse',
      extra={
        'entity_count': len(entity_map['entities']),
        'id_count': len(entity_map['ids']),
        'path': str(ENTITY_MAP_PATH),
      },
    )

  for dir_path in _iter_sanitize_dirs():
    _status(f'Redacting files in {dir_path}')
    normalize = dir_path not in (DASHBOARDS_DIR, PACKAGES_DIR)
    _process_backup_files(
      dir_path, redact_entities, entity_map,
      normalize_yaml=normalize,
    )

  if entity_map['ids'] or entity_map['entities']:
    _status(f'Saving entity map to {ENTITY_MAP_PATH}')
    save_entity_map(entity_map, ENTITY_MAP_PATH)
  _status('Sanitize complete')


def main(argv: list[str] | None = None) -> None:
  '''Pull specific HA config files from the SMB share into home_assistant_backup/.

  Only the files listed in BACKUP_FILES are pulled, not the entire
  HA config directory. To back up additional files, add them to BACKUP_FILES.

  Modes (mutually exclusive):
    (default) backup + sanitize
    -b/--backup    backup only
    -s/--sanitize  sanitize only (processes DEST, dashboards/, packages/)
    -r/--restore   restore redactions using entity_map.yaml
  '''
  # description shown at the top of --help output
  parser = base_arg_parser(
    'Pull HA config files via SMB, redact sensitive data, '
    'or restore redacted files.'
  )
  mode_group = parser.add_mutually_exclusive_group()
  mode_group.add_argument('-b', '--backup', action='store_true',
                          help='Pull BACKUP_FILES from SMB (no sanitize)')
  mode_group.add_argument('-s', '--sanitize', action='store_true',
                          help='Run the redaction pass only (no SMB pull)')
  mode_group.add_argument('-r', '--restore', action='store_true',
                          help='Restore redacted files using entity_map.yaml')
  args = parser.parse_args(argv if argv is not None else sys.argv[1:])
  apply_log_level(args)

  cfg = load_config(allow_env_fallback=True)
  redact_entities = _normalize_redact_entities(cfg.get('redact_entities', []))

  if args.restore:
    _status('Mode: restore — reversing redactions using entity_map.yaml')
    if not ENTITY_MAP_PATH.exists():
      LOGGER.error('entity_map.yaml not found at %s — run a backup first', ENTITY_MAP_PATH)
      sys.exit(1)
    entity_map = load_entity_map(ENTITY_MAP_PATH)
    for dir_path in _iter_sanitize_dirs():
      _status(f'Restoring files in {dir_path}')
      _restore_backup_files(dir_path, entity_map)
    _status('Restore complete')
    LOGGER.info('Restore complete')
    return

  if args.backup:
    _status('Mode: backup only')
    _run_backup(cfg)
    return

  if args.sanitize:
    _status('Mode: sanitize only')
    _run_sanitize(redact_entities)
    return

  _status('Mode: backup + sanitize (default)')
  _run_backup(cfg)
  _run_sanitize(redact_entities)


if __name__ == '__main__':
  main(sys.argv[1:])
