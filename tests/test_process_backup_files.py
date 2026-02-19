"""End-to-end tests for _process_backup_files: write known input files, run the
function, and verify the output content matches expectations."""

import os
import tempfile

from home_assistant_backup import _process_backup_files


def _write_file(directory: str, name: str, content: str) -> str:
  path = os.path.join(directory, name)
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(content)
  return path


def _read_file(path: str) -> str:
  with open(path, "r", encoding="utf-8") as f:
    return f.read()


class TestProcessBackupFilesYaml:

  def test_ids_shortened_in_yaml(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "unique_id: abcdef01234567890abcdef012345678\n"
      path = _write_file(tmp, "test.yaml", content)
      _process_backup_files(tmp, [])
      assert _read_file(path) == "unique_id: abc...678\n"

  def test_names_redacted_in_yaml(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "alias: Alice's Morning Routine\n"
      path = _write_file(tmp, "automations.yaml", content)
      _process_backup_files(tmp, ["Alice"])
      result = _read_file(path)
      assert "Alice" not in result
      assert "<person_1>" in result

  def test_pronouns_neutralized_in_yaml(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "message: Tell him his light is on\n"
      path = _write_file(tmp, "scripts.yaml", content)
      _process_backup_files(tmp, [])
      result = _read_file(path)
      assert result == "message: Tell them their light is on\n"

  def test_all_transformations_combined(self):
    with tempfile.TemporaryDirectory() as tmp:
      hex_id = "aabbccdd11223344aabbccdd11223344"
      content = (
        f"unique_id: {hex_id}\n"
        "alias: Wake up Alice\n"
        "message: Tell her the lights are on\n"
      )
      path = _write_file(tmp, "automation.yaml", content)
      _process_backup_files(tmp, ["Alice"])
      result = _read_file(path)
      assert "aab...344" in result
      assert hex_id not in result
      assert "Alice" not in result
      assert "<person_1>" in result
      assert "Tell them the lights are on" in result


class TestProcessBackupFilesExtensions:

  def test_json_file_is_processed(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = '{"name": "Alice"}'
      path = _write_file(tmp, "data.json", content)
      _process_backup_files(tmp, ["Alice"])
      assert "<person_1>" in _read_file(path)

  def test_conf_file_is_processed(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "owner = Alice\n"
      path = _write_file(tmp, "app.conf", content)
      _process_backup_files(tmp, ["Alice"])
      assert "<person_1>" in _read_file(path)

  def test_txt_file_is_processed(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "Alice was here\n"
      path = _write_file(tmp, "notes.txt", content)
      _process_backup_files(tmp, ["Alice"])
      assert "<person_1>" in _read_file(path)

  def test_py_file_is_not_processed(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "name = 'Alice'\n"
      path = _write_file(tmp, "script.py", content)
      _process_backup_files(tmp, ["Alice"])
      assert _read_file(path) == content

  def test_md_file_is_not_processed(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "# Alice's notes\n"
      path = _write_file(tmp, "readme.md", content)
      _process_backup_files(tmp, ["Alice"])
      assert _read_file(path) == content

  def test_binary_like_extension_not_processed(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "Alice data"
      path = _write_file(tmp, "data.db", content)
      _process_backup_files(tmp, ["Alice"])
      assert _read_file(path) == content


class TestProcessBackupFilesSubdirectories:

  def test_processes_files_in_subdirectories(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "alias: Bob's automation\n"
      path = _write_file(tmp, "subdir/deep/auto.yaml", content)
      _process_backup_files(tmp, ["Bob"])
      result = _read_file(path)
      assert "Bob" not in result
      assert "<person_1>" in result


class TestProcessBackupFilesEdgeCases:

  def test_empty_names_list(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "alias: Alice test\nmessage: call him\n"
      path = _write_file(tmp, "test.yaml", content)
      _process_backup_files(tmp, [])
      result = _read_file(path)
      assert "Alice" in result, "No name redaction with empty list"
      assert "call them" in result, "Pronouns still neutralized"

  def test_file_without_any_matches_unchanged(self):
    with tempfile.TemporaryDirectory() as tmp:
      content = "plain: value\nnumber: 42\n"
      path = _write_file(tmp, "plain.yaml", content)
      _process_backup_files(tmp, [])
      assert _read_file(path) == content

  def test_empty_file(self):
    with tempfile.TemporaryDirectory() as tmp:
      path = _write_file(tmp, "empty.yaml", "")
      _process_backup_files(tmp, ["Alice"])
      assert _read_file(path) == ""

  def test_empty_directory(self):
    with tempfile.TemporaryDirectory() as tmp:
      _process_backup_files(tmp, ["Alice"])
