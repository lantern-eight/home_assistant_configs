"""Convention tests — enforce what docs currently only describe.

Three categories:
1. FILE_MAP existence: every source path in the sync scripts' FILE_MAPs exists.
2. PII scan: no unredacted UUIDs or 32-char hex IDs in tracked YAML/jinja.
3. Doc/map agreement: agents.md deploy tables match the FILE_MAPs.
"""

import re
import subprocess

from utils import REPO_ROOT

import general_home_dashboard_sync as gen_sync
import cyberdeck_sync

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
    for local_name in gen_sync.FILE_MAP:
      path = gen_sync.DASHBOARD_DIR / local_name
      if not path.exists():
        missing.append(str(path))
    assert not missing, f"FILE_MAP source files missing: {missing}"

  def test_general_script_map(self):
    missing = []
    for local_name in gen_sync.SCRIPT_MAP:
      path = gen_sync.SCRIPTS_DIR / local_name
      if not path.exists():
        missing.append(str(path))
    assert not missing, f"SCRIPT_MAP source files missing: {missing}"

  def test_cyberdeck_file_map(self):
    missing = []
    for local_name in cyberdeck_sync.FILE_MAP:
      path = cyberdeck_sync.CYBERDECK_DIR / local_name
      if not path.exists():
        missing.append(str(path))
    assert not missing, f"FILE_MAP source files missing: {missing}"


# ── 2. PII scan ────────────────────────────────────────────────────────────


def _git_tracked_files(*extensions):
  """Return git-tracked files matching the given extensions."""
  globs = [f'*.{ext.lstrip(".")}' for ext in extensions]
  args = ['git', 'ls-files', '--']
  args.extend(globs)
  result = subprocess.run(
    args, capture_output=True, text=True, cwd=str(REPO_ROOT),
  )
  return [line for line in result.stdout.splitlines() if line]


class TestNoPiiInTrackedFiles:
  """No unredacted UUIDs or 32-char hex IDs in tracked YAML/jinja files."""

  def test_no_raw_ids_in_yaml(self):
    violations = []
    for rel_path in _git_tracked_files('.yaml', '.jinja'):
      path = REPO_ROOT / rel_path
      content = path.read_text(encoding='utf-8', errors='replace')
      for lineno, line in enumerate(content.splitlines(), 1):
        for match in _ID_PATTERN.finditer(line):
          violations.append(f"{rel_path}:{lineno}: {match.group(1)}")
    assert not violations, (
      f"Unredacted IDs found in tracked files:\n" + "\n".join(violations)
    )


# ── 3. Doc/map agreement ───────────────────────────────────────────────────


def _extract_table_column(text, header_pattern, column_index=0):
  """Extract backtick-quoted values from a markdown table column.

  Finds the first table whose header row matches header_pattern,
  then pulls backtick-quoted strings from the given column index
  in each data row (skipping the separator row).
  """
  lines = text.splitlines()
  values = []
  in_table = False
  skip_separator = False
  backtick = re.compile(r'`([^`]+)`')

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
    map_files = sorted(cyberdeck_sync.FILE_MAP.keys())
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
    for local_name, remote_path in cyberdeck_sync.FILE_MAP.items():
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
    map_files = set(gen_sync.FILE_MAP.keys())
    missing = map_files - set(doc_files)
    assert not missing, (
      f"FILE_MAP entries missing from File Roles table: {sorted(missing)}"
    )
