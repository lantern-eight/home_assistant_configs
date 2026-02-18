"""Tests for the should_ignore() pattern-matching function."""

import pytest

from home_assistant_backup import should_ignore


class TestShouldIgnoreMatchingPatterns:
    """Filenames/dirnames that SHOULD be ignored."""

    @pytest.mark.parametrize("name", [
        "home-assistant_v2.db",
        "data.db",
    ])
    def test_db_files(self, name):
        assert should_ignore(name) is True

    @pytest.mark.parametrize("name", [
        "home-assistant_v2.db-shm",
        "home-assistant_v2.db-wal",
    ])
    def test_db_journal_files(self, name):
        assert should_ignore(name) is True

    @pytest.mark.parametrize("name", [
        "home-assistant.log",
        "access.log",
    ])
    def test_log_files(self, name):
        assert should_ignore(name) is True

    @pytest.mark.parametrize("name", [
        "home-assistant.log.1",
        "access.log.fault",
    ])
    def test_rotated_log_files(self, name):
        assert should_ignore(name) is True

    @pytest.mark.parametrize("name", [
        "__pycache__",
        ".storage",
        ".cloud",
        "deps",
        "tts",
        "backups",
        "custom_components",
    ])
    def test_ignored_directories(self, name):
        assert should_ignore(name) is True

    def test_ha_run_lock(self):
        assert should_ignore(".ha_run.lock") is True

    def test_ha_version(self):
        assert should_ignore(".HA_VERSION") is True

    def test_secrets_yaml(self):
        assert should_ignore("secrets.yaml") is True

    def test_august_conf(self):
        assert should_ignore("anything.august.conf") is True


class TestShouldIgnoreNonMatchingPatterns:
    """Filenames/dirnames that should NOT be ignored."""

    @pytest.mark.parametrize("name", [
        "configuration.yaml",
        "automations.yaml",
        "scenes.yaml",
        "scripts.yaml",
        "custom__sensors.yaml",
    ])
    def test_normal_yaml_files(self, name):
        assert should_ignore(name) is False

    @pytest.mark.parametrize("name", [
        "home_assistant_backup.py",
        "utils.py",
        "README.md",
        "pyproject.toml",
    ])
    def test_project_files(self, name):
        assert should_ignore(name) is False

    def test_json_file(self):
        assert should_ignore("data.json") is False

    def test_txt_file(self):
        assert should_ignore("notes.txt") is False

    def test_regular_conf(self):
        assert should_ignore("regular.conf") is False

    def test_blueprints_dir(self):
        assert should_ignore("blueprints") is False
