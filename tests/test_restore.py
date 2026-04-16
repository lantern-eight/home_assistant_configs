"""Tests for entity map I/O, entity map accumulation during processing,
and the _restore_backup_files round-trip."""

import os
import tempfile

import yaml

from home_assistant_backup import (
    _process_backup_files,
    _restore_backup_files,
    _run_sanitize,
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
            "names": {"<entity_1>": "Alice", "<entity_2>": "Bob"},
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
                yaml.dump({"names": {"<entity_1>": "Alice"}}, f)
            loaded = load_entity_map(path)
        assert loaded["ids"] == {}
        assert loaded["names"] == {"<entity_1>": "Alice"}

    def test_saved_file_is_valid_yaml(self):
        entity_map = {
            "ids": {"abc...678": "abcdef01234567890abcdef012345678"},
            "names": {"<entity_1>": "Alice"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "entity_map.yaml")
            save_entity_map(entity_map, path)
            with open(path) as f:
                raw = yaml.safe_load(f)
        assert raw["ids"]["abc...678"] == "abcdef01234567890abcdef012345678"
        assert raw["names"]["<entity_1>"] == "Alice"


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
        assert name_map == {"<entity_1>": "Alice", "<entity_2>": "Bob"}

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
            assert entity_map["names"]["<entity_1>"] == "Alice"


# ---------------------------------------------------------------------------
# _restore_backup_files
# ---------------------------------------------------------------------------

class TestRestoreBackupFiles:

    def test_restores_names(self):
        entity_map = {"ids": {}, "names": {"<entity_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "auto.yaml", "alias: <entity_1>'s Routine\n")
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
            "names": {"<entity_1>": "Alice"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            content = "unique_id: aab...344\nalias: <entity_1> Morning\n"
            path = _write_file(tmp, "auto.yaml", content)
            _restore_backup_files(tmp, entity_map)
            result = _read_file(path)
            assert full_id in result
            assert "Alice Morning" in result
            assert "<entity_1>" not in result
            assert "aab...344" not in result

    def test_restores_multiple_names(self):
        entity_map = {
            "ids": {},
            "names": {"<entity_1>": "Alice", "<entity_2>": "Bob"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            content = "<entity_1> and <entity_2> went home\n"
            path = _write_file(tmp, "auto.yaml", content)
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == "Alice and Bob went home\n"

    def test_restores_across_subdirectories(self):
        entity_map = {"ids": {}, "names": {"<entity_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "sub/deep/auto.yaml", "alias: <entity_1>\n")
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == "alias: Alice\n"

    def test_skips_non_processable_extensions(self):
        entity_map = {"ids": {}, "names": {"<entity_1>": "Alice"}}
        with tempfile.TemporaryDirectory() as tmp:
            content = "name = '<entity_1>'\n"
            path = _write_file(tmp, "script.py", content)
            _restore_backup_files(tmp, entity_map)
            assert _read_file(path) == content

    def test_no_match_leaves_file_unchanged(self):
        entity_map = {"ids": {}, "names": {"<entity_1>": "Alice"}}
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
        entity_map = {"ids": {"abc...678": "x" * 32}, "names": {"<entity_1>": "Alice"}}
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


# ---------------------------------------------------------------------------
# redact_names_in_text placeholder reuse (stable partial-sanitize)
# ---------------------------------------------------------------------------

class TestRedactNamesReuse:

    def test_reuses_existing_placeholder_for_known_name(self):
        """A name already in name_map keeps its placeholder."""
        name_map = {"<entity_3>": "Zavala"}
        redact_names_in_text("Hello Zavala", ["Zavala"], name_map)
        # Map unchanged: still <entity_3>, no <entity_1> created.
        assert name_map == {"<entity_3>": "Zavala"}

    def test_assigns_next_free_index_skipping_used(self):
        """New names skip indices already taken by entries in name_map."""
        name_map = {"<entity_1>": "Alice", "<entity_3>": "Zavala"}
        redact_names_in_text("Bob and Dan", ["Bob", "Dan"], name_map)
        # 1 and 3 are used; Bob takes 2, Dan takes 4.
        assert name_map["<entity_1>"] == "Alice"
        assert name_map["<entity_2>"] == "Bob"
        assert name_map["<entity_3>"] == "Zavala"
        assert name_map["<entity_4>"] == "Dan"

    def test_case_insensitive_reuse(self):
        """Existing placeholder is reused even if redact_names casing differs."""
        name_map = {"<entity_5>": "Zavala"}
        result = redact_names_in_text("hi zavala and ZAVALA", ["zavala"], name_map)
        assert "<entity_5>" in result
        assert "zavala" not in result.lower().replace("<entity_5>", "")
        assert name_map == {"<entity_5>": "Zavala"}

    def test_stable_after_reordering_redact_names(self):
        """Reordering the redact_names list does NOT renumber placeholders."""
        name_map = {"<entity_1>": "Alice", "<entity_2>": "Bob"}
        # Original order was [Alice, Bob]; new run uses [Bob, Alice].
        redact_names_in_text("Alice met Bob", ["Bob", "Alice"], name_map)
        # Still <entity_1>: Alice and <entity_2>: Bob (not swapped).
        assert name_map == {"<entity_1>": "Alice", "<entity_2>": "Bob"}

    def test_replaces_using_reused_placeholder(self):
        """The actual content replacement uses the reused placeholder."""
        name_map = {"<entity_3>": "Zavala"}
        result = redact_names_in_text("alias: Zavala's room", ["Zavala"], name_map)
        assert result == "alias: <entity_3>'s room"


# ---------------------------------------------------------------------------
# Partial sanitization end-to-end (the key user concern)
# ---------------------------------------------------------------------------

class TestPartialSanitization:

    def test_mixed_file_only_redacts_real_names(self):
        """A file with both real names and placeholders: real names get
        redacted, existing placeholders are left alone (no double-encoding)."""
        with tempfile.TemporaryDirectory() as tmp:
            content = "alias: <entity_3>'s door\nmessage: Zavala opened the door\n"
            path = _write_file(tmp, "auto.yaml", content)

            entity_map = {"ids": {}, "names": {"<entity_3>": "Zavala"}}
            _process_backup_files(tmp, ["Zavala"], entity_map)

            result = _read_file(path)
            # Real "Zavala" is now <entity_3>; original <entity_3> untouched.
            assert "Zavala" not in result
            assert result.count("<entity_3>") == 2
            # Map unchanged — same placeholder, no new entry.
            assert entity_map["names"] == {"<entity_3>": "Zavala"}

    def test_uses_existing_map_for_consistent_placeholders(self):
        """A name in redact_names re-uses its existing placeholder rather than
        being assigned a new one based on list position."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_file(tmp, "auto.yaml", "alias: Zavala's door\n")
            # Map has Zavala at <entity_3>, even though it'd be index 1
            # if we just enumerated redact_names.
            entity_map = {"ids": {}, "names": {"<entity_3>": "Zavala"}}
            _process_backup_files(tmp, ["Zavala"], entity_map)
            assert _read_file(path) == "alias: <entity_3>'s door\n"

    def test_already_sanitized_file_not_rewritten(self):
        """A fully-sanitized file should be a no-op (content unchanged)."""
        with tempfile.TemporaryDirectory() as tmp:
            content = "alias: <entity_3>'s door\n"
            path = _write_file(tmp, "auto.yaml", content)
            mtime_before = os.path.getmtime(path)

            entity_map = {"ids": {}, "names": {"<entity_3>": "Zavala"}}
            _process_backup_files(tmp, ["Zavala"], entity_map)

            assert _read_file(path) == content
            # File should not have been rewritten (mtime unchanged).
            assert os.path.getmtime(path) == mtime_before


# ---------------------------------------------------------------------------
# _run_sanitize: loads existing entity_map, processes both dirs, saves merged
# ---------------------------------------------------------------------------

class TestRunSanitize:

    def test_loads_existing_map_and_reuses_placeholders(self, monkeypatch, tmp_path):
        """Sanitize loads the on-disk entity_map and keeps known placeholders."""
        dest = tmp_path / "backup"
        comments = tmp_path / "comments"
        map_path = tmp_path / "entity_map.yaml"
        dest.mkdir()
        comments.mkdir()

        # Pre-existing map with Zavala pinned to <entity_3>.
        save_entity_map({"ids": {}, "names": {"<entity_3>": "Zavala"}}, map_path)
        (dest / "auto.yaml").write_text(
            "alias: Zavala's door\nmessage: <entity_3> opened it\n"
        )
        (comments / "ref.yaml").write_text("note: Zavala's room\n")

        monkeypatch.setattr("home_assistant_backup.DEST", str(dest))
        monkeypatch.setattr("home_assistant_backup.COMMENTS_DIR", str(comments))
        monkeypatch.setattr("home_assistant_backup.ENTITY_MAP_PATH", map_path)
        monkeypatch.setattr("home_assistant_backup.REDACT_NAMES", ["Zavala"])

        _run_sanitize()

        assert (dest / "auto.yaml").read_text() == (
            "alias: <entity_3>'s door\nmessage: <entity_3> opened it\n"
        )
        assert (comments / "ref.yaml").read_text() == "note: <entity_3>'s room\n"
        # Map preserved; no <entity_1> created.
        final = load_entity_map(map_path)
        assert final["names"] == {"<entity_3>": "Zavala"}

    def test_works_without_existing_map(self, monkeypatch, tmp_path):
        """First-time sanitize (no entity_map.yaml yet) works and writes one."""
        dest = tmp_path / "backup"
        map_path = tmp_path / "entity_map.yaml"
        dest.mkdir()
        (dest / "auto.yaml").write_text("alias: Alice's morning\n")

        monkeypatch.setattr("home_assistant_backup.DEST", str(dest))
        monkeypatch.setattr(
            "home_assistant_backup.COMMENTS_DIR", str(tmp_path / "missing")
        )
        monkeypatch.setattr("home_assistant_backup.ENTITY_MAP_PATH", map_path)
        monkeypatch.setattr("home_assistant_backup.REDACT_NAMES", ["Alice"])

        _run_sanitize()

        assert (dest / "auto.yaml").read_text() == "alias: <entity_1>'s morning\n"
        assert map_path.exists()
        assert load_entity_map(map_path)["names"] == {"<entity_1>": "Alice"}

    def test_skips_missing_comments_dir(self, monkeypatch, tmp_path):
        """Sanitize should not error if COMMENTS_DIR doesn't exist."""
        dest = tmp_path / "backup"
        map_path = tmp_path / "entity_map.yaml"
        dest.mkdir()
        (dest / "auto.yaml").write_text("alias: Alice's morning\n")

        monkeypatch.setattr("home_assistant_backup.DEST", str(dest))
        monkeypatch.setattr(
            "home_assistant_backup.COMMENTS_DIR", str(tmp_path / "does_not_exist")
        )
        monkeypatch.setattr("home_assistant_backup.ENTITY_MAP_PATH", map_path)
        monkeypatch.setattr("home_assistant_backup.REDACT_NAMES", ["Alice"])

        # Should not raise.
        _run_sanitize()
        assert (dest / "auto.yaml").read_text() == "alias: <entity_1>'s morning\n"

    def test_processes_both_dirs_with_separate_files(self, monkeypatch, tmp_path):
        """Sanitize accumulates findings across both DEST and COMMENTS_DIR."""
        dest = tmp_path / "backup"
        comments = tmp_path / "comments"
        map_path = tmp_path / "entity_map.yaml"
        dest.mkdir()
        comments.mkdir()

        (dest / "auto.yaml").write_text("alias: Alice morning\n")
        (comments / "ref.yaml").write_text("note: Bob evening\n")

        monkeypatch.setattr("home_assistant_backup.DEST", str(dest))
        monkeypatch.setattr("home_assistant_backup.COMMENTS_DIR", str(comments))
        monkeypatch.setattr("home_assistant_backup.ENTITY_MAP_PATH", map_path)
        monkeypatch.setattr("home_assistant_backup.REDACT_NAMES", ["Alice", "Bob"])

        _run_sanitize()

        assert (dest / "auto.yaml").read_text() == "alias: <entity_1> morning\n"
        assert (comments / "ref.yaml").read_text() == "note: <entity_2> evening\n"
        final = load_entity_map(map_path)
        assert final["names"] == {"<entity_1>": "Alice", "<entity_2>": "Bob"}
