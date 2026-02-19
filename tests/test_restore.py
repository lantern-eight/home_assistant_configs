"""Tests for entity map I/O, entity map accumulation during processing,
and the _restore_backup_files round-trip."""

import os
import tempfile

import yaml

from home_assistant_backup import (
    _process_backup_files,
    _restore_backup_files,
    load_entity_map,
    redact_names_in_text,
    save_entity_map,
    shorten_ids,
)


def _write_file(directory: str, name: str, content: str) -> str:
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

class TestEntityMapSaveLoad:

    def test_round_trip(self):
        entity_map = {
            "ids": {"abc...678": "abcdef01234567890abcdef012345678"},
            "names": {"<person_1>": "Alice", "<person_2>": "Bob"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "entity_map.yaml")
            save_entity_map(entity_map, path)
            loaded = load_entity_map(path)
        assert loaded == entity_map

    def test_load_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "entity_map.yaml")
            with open(path, "w") as f:
                f.write("")
            loaded = load_entity_map(path)
        assert loaded == {"ids": {}, "names": {}}

    def test_load_partial_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "entity_map.yaml")
            with open(path, "w") as f:
                yaml.dump({"names": {"<person_1>": "Alice"}}, f)
            loaded = load_entity_map(path)
        assert loaded["ids"] == {}
        assert loaded["names"] == {"<person_1>": "Alice"}

    def test_saved_file_is_valid_yaml(self):
        entity_map = {
            "ids": {"abc...678": "abcdef01234567890abcdef012345678"},
            "names": {"<person_1>": "Alice"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "entity_map.yaml")
            save_entity_map(entity_map, path)
            with open(path) as f:
                raw = yaml.safe_load(f)
        assert raw["ids"]["abc...678"] == "abcdef01234567890abcdef012345678"
        assert raw["names"]["<person_1>"] == "Alice"


# ---------------------------------------------------------------------------
# entity_map accumulation in shorten_ids / redact_names_in_text
# ---------------------------------------------------------------------------

class TestEntityMapAccumulation:

    def test_shorten_ids_populates_id_map(self):
        id_map = {}
        hex_id = "abcdef01234567890abcdef012345678"
        shorten_ids(f"unique_id: {hex_id}", id_map)
        assert id_map == {"abc...678": hex_id}

    def test_shorten_ids_multiple_ids(self):
        id_map = {}
        id1 = "11111111111111111111111111111111"
        id2 = "22222222222222222222222222222222"
        shorten_ids(f"{id1}\n{id2}", id_map)
        assert id_map["111...111"] == id1
        assert id_map["222...222"] == id2

    def test_shorten_ids_no_map_when_none(self):
        shorten_ids("abcdef01234567890abcdef012345678")

    def test_redact_names_populates_name_map(self):
        name_map = {}
        redact_names_in_text("Hello Alice and Bob", ["Alice", "Bob"], name_map)
        assert name_map == {"<person_1>": "Alice", "<person_2>": "Bob"}

    def test_redact_names_no_map_when_none(self):
        redact_names_in_text("Hello Alice", ["Alice"])

    def test_process_backup_files_populates_entity_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            hex_id = "aabbccdd11223344aabbccdd11223344"
            content = f"unique_id: {hex_id}\nalias: Wake up Alice\n"
            _write_file(tmp, "auto.yaml", content)

            entity_map = {"ids": {}, "names": {}}
            _process_backup_files(tmp, ["Alice"], entity_map)

            assert entity_map["ids"]["aab...344"] == hex_id
            assert entity_map["names"]["<person_1>"] == "Alice"


# ---------------------------------------------------------------------------
# _restore_backup_files
# ---------------------------------------------------------------------------

class TestRestoreBackupFiles:

    def test_restores_names(self):
        entity_map = {"ids": {}, "names": {"<person_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "auto.yaml", "alias: <person_1>'s Routine\n")
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == "alias: Alice's Routine\n"

    def test_restores_ids(self):
        full_id = "abcdef01234567890abcdef012345678"
        entity_map = {"ids": {"abc...678": full_id}, "names": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "auto.yaml", "unique_id: abc...678\n")
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == f"unique_id: {full_id}\n"

    def test_restores_names_and_ids_combined(self):
        full_id = "aabbccdd11223344aabbccdd11223344"
        entity_map = {
            "ids": {"aab...344": full_id},
            "names": {"<person_1>": "Alice"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            content = "unique_id: aab...344\nalias: <person_1> Morning\n"
            path = _write_file(tmp, "auto.yaml", content)
            _restore_backup_files(tmp, entity_map)
            result = _read_file(path)
            assert full_id in result
            assert "Alice Morning" in result
            assert "<person_1>" not in result
            assert "aab...344" not in result

    def test_restores_multiple_names(self):
        entity_map = {
            "ids": {},
            "names": {"<person_1>": "Alice", "<person_2>": "Bob"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            content = "<person_1> and <person_2> went home\n"
            path = _write_file(tmp, "auto.yaml", content)
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == "Alice and Bob went home\n"

    def test_restores_across_subdirectories(self):
        entity_map = {"ids": {}, "names": {"<person_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "sub/deep/auto.yaml", "alias: <person_1>\n")
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == "alias: Alice\n"

    def test_skips_non_processable_extensions(self):
        entity_map = {"ids": {}, "names": {"<person_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            content = "name = '<person_1>'\n"
            path = _write_file(tmp, "script.py", content)
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == content

    def test_no_match_leaves_file_unchanged(self):
        entity_map = {"ids": {}, "names": {"<person_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            content = "plain: value\n"
            path = _write_file(tmp, "plain.yaml", content)
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == content

    def test_empty_entity_map(self):
        entity_map = {"ids": {}, "names": {}}
        with tempfile.TemporaryDirectory() as tmp:
            content = "alias: test\n"
            path = _write_file(tmp, "auto.yaml", content)
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == content

    def test_empty_directory(self):
        entity_map = {"ids": {"abc...678": "x" * 32}, "names": {"<person_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            _restore_backup_files(tmp, entity_map)


# ---------------------------------------------------------------------------
# Full round-trip: process then restore
# ---------------------------------------------------------------------------

class TestProcessThenRestore:

    def test_round_trip_names_and_ids(self):
        """Process -> save map -> restore recovers original IDs and names."""
        hex_id = "aabbccdd11223344aabbccdd11223344"
        original = f"unique_id: {hex_id}\nalias: Wake up Alice\n"

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "auto.yaml", original)

            entity_map = {"ids": {}, "names": {}}
            _process_backup_files(tmp, ["Alice"], entity_map)

            redacted = _read_file(path)
            assert hex_id not in redacted
            assert "Alice" not in redacted

            _restore_backup_files(tmp, entity_map)
            restored = _read_file(path)

            assert hex_id in restored
            assert "Alice" in restored

    def test_round_trip_preserves_pronouns_as_neutral(self):
        """Pronouns stay neutralized after restore (expected limitation)."""
        original = "message: Tell him his light is on\n"

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "scripts.yaml", original)

            entity_map = {"ids": {}, "names": {}}
            _process_backup_files(tmp, [], entity_map)
            _restore_backup_files(tmp, entity_map)

            assert _read_file(path) == "message: Tell them their light is on\n"

    def test_round_trip_via_saved_map_file(self):
        """Full cycle: process -> save map to disk -> load map -> restore."""
        hex_id = "11223344556677881122334455667788"
        original = f"id: {hex_id}\nowner: Bob\n"

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "config.yaml", original)
            map_path = os.path.join(tmp, "entity_map.yaml")

            entity_map = {"ids": {}, "names": {}}
            _process_backup_files(tmp, ["Bob"], entity_map)
            save_entity_map(entity_map, map_path)

            loaded_map = load_entity_map(map_path)
            _restore_backup_files(tmp, loaded_map)

            restored = _read_file(path)
            assert hex_id in restored
            assert "Bob" in restored
