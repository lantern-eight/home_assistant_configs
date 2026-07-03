"""Tests for the BACKUP_FILES process list."""

from home_assistant_backup import BACKUP_FILES


class TestBackupFiles:
  """Verify the BACKUP_FILES process list is well-formed."""

  def test_not_empty(self):
    assert len(BACKUP_FILES) > 0

  def test_all_entries_are_strings(self):
    for entry in BACKUP_FILES:
      assert isinstance(entry, str)

  def test_no_leading_slashes(self):
    for entry in BACKUP_FILES:
      assert not entry.startswith('/'), f'{entry} should be a relative path'
      assert not entry.startswith('\\'), f'{entry} should be a relative path'

  def test_configuration_yaml_present(self):
    assert 'configuration.yaml' in BACKUP_FILES
