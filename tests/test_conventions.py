"""Convention tests — enforce what docs currently only describe.

Five categories:
1. FILE_MAP existence: every source path in the sync scripts' FILE_MAPs exists.
2. PII scan: no unredacted IDs or names in tracked/staged YAML/jinja/md.
3. Doc/map agreement: agents.md deploy tables match the FILE_MAPs.
4. Automation icons: rows do not override what the entity registry sets.
5. HACS card documentation: the dashboard README lists the cards it uses.
"""

import re
import subprocess

import yaml

from utils import CONFIG_PATH, REPO_ROOT

import ha_sync

_ID_PATTERN = re.compile(
  r'\b('
  r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
  r'|[0-9a-fA-F]{32}'
  r')\b'
)


# ── 1. FILE_MAP existence ──────────────────────────────────────────────────


class TestFileMapExistence:
  """Every source file referenced by a sync script FILE_MAP must exist on disk."""

  def test_general_file_map(self):
    missing = []
    for local_name in ha_sync.GENERAL_HOME_FILE_MAP:
      path = ha_sync.GENERAL_HOME_DIR / local_name
      if not path.exists():
        missing.append(str(path))
    assert not missing, f"FILE_MAP source files missing: {missing}"

  def test_general_script_map(self):
    missing = []
    for local_name in ha_sync.GENERAL_HOME_SCRIPT_MAP:
      path = ha_sync.SCRIPTS_DIR / local_name
      if not path.exists():
        missing.append(str(path))
    assert not missing, f"SCRIPT_MAP source files missing: {missing}"

  def test_cyberdeck_file_map(self):
    missing = []
    for local_name in ha_sync.CYBERDECK_FILE_MAP:
      path = ha_sync.CYBERDECK_DIR / local_name
      if not path.exists():
        missing.append(str(path))
    assert not missing, f"FILE_MAP source files missing: {missing}"


# ── 2. PII scan ────────────────────────────────────────────────────────────


# Local-only scratch directories. `plans/` holds working plans that track
# in-progress work across sessions on one machine; they are gitignored, so
# git already hides them here. Listing the prefix as well keeps the PII scan
# off them even if a file is ever force-added, since a plan may legitimately
# quote UUID-shaped things like design-tool URLs.
_SCAN_EXCLUDED_PREFIXES = ('plans/',)


def _git_visible_files(*extensions):
  """Return tracked and untracked (non-ignored) files matching extensions."""
  globs = [f'*.{ext.lstrip(".")}' for ext in extensions]
  args = [
    'git', 'ls-files',
    '--cached', '--others', '--exclude-standard', '--',
  ]
  args.extend(globs)
  result = subprocess.run(
    args, capture_output=True, text=True, cwd=str(REPO_ROOT),
  )
  return [
    line for line in result.stdout.splitlines()
    if line and not line.startswith(_SCAN_EXCLUDED_PREFIXES)
  ]


def _redact_entities():
  """Load redact_entities from config.yaml, or [] if absent."""
  if not CONFIG_PATH.exists():
    return []
  with open(CONFIG_PATH) as f:
    raw = yaml.safe_load(f) or {}
  return raw.get('redact_entities', [])


_SCAN_EXTENSIONS = ('.yaml', '.jinja', '.md')


class TestNoPiiInTrackedFiles:
  """No unredacted IDs or names in tracked/staged files."""

  def test_no_raw_ids(self):
    violations = []
    for rel_path in _git_visible_files(*_SCAN_EXTENSIONS):
      path = REPO_ROOT / rel_path
      content = path.read_text(encoding='utf-8', errors='replace')
      for lineno, line in enumerate(content.splitlines(), 1):
        for match in _ID_PATTERN.finditer(line):
          violations.append(f"{rel_path}:{lineno}: {match.group(1)}")
    assert not violations, (
      "Unredacted IDs found in tracked files:\n" + "\n".join(violations)
    )

  def test_no_raw_names(self):
    names = _redact_entities()
    if not names:
      return
    pattern = re.compile(
      '|'.join(re.escape(n) for n in names), re.IGNORECASE,
    )
    violations = []
    for rel_path in _git_visible_files(*_SCAN_EXTENSIONS):
      path = REPO_ROOT / rel_path
      content = path.read_text(encoding='utf-8', errors='replace')
      for lineno, line in enumerate(content.splitlines(), 1):
        for match in pattern.finditer(line):
          violations.append(f"{rel_path}:{lineno}: {match.group()}")
    assert not violations, (
      "Unredacted names found in tracked files:\n"
      + "\n".join(violations)
    )


# ── 3. Doc/map agreement ───────────────────────────────────────────────────


_BACKTICK_CELL = re.compile(r'`([^`]+)`')
_BOLD_CELL = re.compile(r'\*\*([^*]+)\*\*')


def _extract_table_column(text, header_pattern, column_index=0,
                          cell_pattern=_BACKTICK_CELL):
  """Extract marked-up values from a markdown table column.

  Finds the first table whose header row matches header_pattern,
  then pulls the first cell_pattern match from the given column index
  in each data row (skipping the separator row). Defaults to
  backtick-quoted values; pass _BOLD_CELL for **bold** ones.
  """
  lines = text.splitlines()
  values = []
  in_table = False
  skip_separator = False
  backtick = cell_pattern

  for line in lines:
    stripped = line.strip()
    if not in_table:
      if stripped.startswith('|') and re.search(header_pattern, stripped):
        in_table = True
        skip_separator = True
        continue
    else:
      if skip_separator:
        skip_separator = False
        continue
      if not stripped.startswith('|'):
        break
      cells = [c.strip() for c in stripped.strip('|').split('|')]
      if column_index < len(cells):
        match = backtick.search(cells[column_index])
        if match:
          values.append(match.group(1))
  return values


class TestDocMapAgreement:
  """agents.md deploy tables must list the files the FILE_MAPs actually ship."""

  def test_cyberdeck_deploy_table_matches_file_map(self):
    agents_md = (REPO_ROOT / 'agents.md').read_text(encoding='utf-8')
    doc_files = _extract_table_column(agents_md, r'Local file.*HA destination')
    map_files = sorted(ha_sync.CYBERDECK_FILE_MAP.keys())
    assert sorted(doc_files) == map_files, (
      f"Cyberdeck deploy table drift:\n"
      f"  in docs but not FILE_MAP: {sorted(set(doc_files) - set(map_files))}\n"
      f"  in FILE_MAP but not docs: {sorted(set(map_files) - set(doc_files))}"
    )

  def test_cyberdeck_deploy_table_destinations_match(self):
    agents_md = (REPO_ROOT / 'agents.md').read_text(encoding='utf-8')
    doc_destinations = _extract_table_column(
      agents_md, r'Local file.*HA destination', column_index=1,
    )
    doc_files = _extract_table_column(agents_md, r'Local file.*HA destination')
    doc_map = dict(zip(doc_files, doc_destinations))
    for local_name, remote_path in ha_sync.CYBERDECK_FILE_MAP.items():
      assert local_name in doc_map, f"{local_name} missing from deploy table"
      assert doc_map[local_name] == remote_path, (
        f"{local_name}: docs say '{doc_map[local_name]}', "
        f"FILE_MAP says '{remote_path}'"
      )

  def test_general_file_map_keys_in_file_roles_table(self):
    agents_md = (
      REPO_ROOT / 'dashboards' / 'general_home_mobile' / 'agents.md'
    ).read_text(encoding='utf-8')
    doc_files = _extract_table_column(agents_md, r'File\s*\|.*What it does')
    map_files = set(ha_sync.GENERAL_HOME_FILE_MAP.keys())
    missing = map_files - set(doc_files)
    assert not missing, (
      f"FILE_MAP entries missing from File Roles table: {sorted(missing)}"
    )


# ── 4. HACS card documentation ─────────────────────────────────────────────

# Entries that are real dependencies but never appear as a `custom:` card
# type, so they cannot be derived from dashboard.yaml: card-mod is a CSS
# injector, kiosk-mode and material-you-utilities are frontend modules.
_NON_CARD_HACS_ENTRIES = {
  'card-mod',
  'kiosk-mode',
  'material-you-utilities',
}

# mushroom ships a family of card types under one HACS package.
_CARD_TYPE_TO_HACS = {'mushroom': 'mushroom'}


def _hacs_package_for(card_type):
  """Map a `custom:` card type to the HACS package that provides it."""
  for prefix, package in _CARD_TYPE_TO_HACS.items():
    if card_type.startswith(prefix):
      return package
  return card_type


class TestAutomationIconsLiveInTheRegistry:
  """Automation icons belong to the entity, not to a dashboard row.

  A Home Assistant automation cannot declare an icon in its own YAML, so the
  only way one appears in the Settings list, in search, or on a related-entity
  view is via the entity registry — which `registry_metadata.yaml` drives.
  A row that names its own icon overrides that for one dashboard and leaves
  the entity bare everywhere else, which is how this page ended up with a
  second, private set of icons in the first place.
  """

  def _automation_rows_with_icons(self):
    dashboard = (
      REPO_ROOT / 'dashboards' / 'general_home_mobile' / 'dashboard.yaml'
    ).read_text(encoding='utf-8')

    offenders = []
    lines = dashboard.splitlines()
    for index, line in enumerate(lines):
      match = re.match(r'^(\s*)(?:- )?entity: (automation\.\S+)$', line)
      if not match:
        continue
      indent = match.group(1)
      body = indent + '  ' if line.lstrip().startswith('- ') else indent
      # Scan the row's own keys only — stop at the first nested block so a
      # tap_action's or a fold's inner keys are never mistaken for the row's.
      for following in lines[index + 1:index + 10]:
        if re.match(rf'^{re.escape(body)}icon: ', following):
          offenders.append(f'{match.group(2)} (line {index + 1})')
          break
        if re.match(rf'^{re.escape(body)}(card_mod|tap_action):', following):
          break
        if not following.startswith(body):
          break
    return offenders

  def test_no_automation_row_declares_its_own_icon(self):
    offenders = self._automation_rows_with_icons()
    assert not offenders, (
      "Automation rows declaring their own icon. Move these to the `icon:` "
      "key on the entity in registry_metadata.yaml, so the icon shows "
      f"everywhere in Home Assistant rather than on this page only: {offenders}"
    )


class TestHacsCardsDocumented:
  """The dashboard README must list the cards dashboard.yaml actually uses.

  The table is a setup checklist — a card missing from it means a fresh
  install renders "Custom element doesn't exist" with no clue what to
  install, and a card lingering in it sends people to install something
  nothing uses.
  """

  def _used_and_documented(self):
    dashboard_dir = REPO_ROOT / 'dashboards' / 'general_home_mobile'
    dashboard = (dashboard_dir / 'dashboard.yaml').read_text(encoding='utf-8')
    readme = (dashboard_dir / 'README.md').read_text(encoding='utf-8')

    used = {
      _hacs_package_for(match)
      for match in re.findall(r'custom:([a-z0-9-]+)', dashboard)
    }
    documented = set(_extract_table_column(
      readme, r'Integration\s*\|\s*Purpose', cell_pattern=_BOLD_CELL,
    ))
    return used, documented

  def test_every_used_card_is_documented(self):
    used, documented = self._used_and_documented()
    missing = used - documented
    assert not missing, (
      "Cards used by dashboard.yaml but absent from the README's HACS "
      f"table: {sorted(missing)}"
    )

  def test_no_documented_card_is_unused(self):
    used, documented = self._used_and_documented()
    stale = documented - used - _NON_CARD_HACS_ENTRIES
    assert not stale, (
      "Cards listed in the README's HACS table that dashboard.yaml no "
      f"longer uses: {sorted(stale)}"
    )
