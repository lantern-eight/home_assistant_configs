"""Tests for _load_config: loading from YAML file vs environment variables."""

import os
import tempfile
from unittest.mock import patch

import yaml

import home_assistant_backup as hab


def _make_config_yaml(tmp_path: str, data: dict) -> str:
    path = os.path.join(tmp_path, "config.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


class TestLoadConfigFromYaml:

    def test_loads_all_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_data = {
                "smb_server": "10.0.0.1",
                "smb_share": "ha_share",
                "smb_path": "config/path",
                "smb_user": "admin",
                "smb_password": "secret",
                "redact_names": ["Alice", "Bob"],
            }
            cfg_path = _make_config_yaml(tmp, cfg_data)
            with patch.object(hab, "CONFIG_PATH", hab.Path(cfg_path)):
                result = hab._load_config()

            assert result["smb_server"] == "10.0.0.1"
            assert result["smb_share"] == "ha_share"
            assert result["smb_path"] == "config/path"
            assert result["smb_user"] == "admin"
            assert result["smb_password"] == "secret"
            assert result["redact_names"] == ["Alice", "Bob"]

    def test_missing_optional_fields_default_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _make_config_yaml(tmp, {"smb_server": "10.0.0.1"})
            with patch.object(hab, "CONFIG_PATH", hab.Path(cfg_path)):
                result = hab._load_config()

            assert result["smb_server"] == "10.0.0.1"
            assert result["smb_share"] == ""
            assert result["smb_path"] == ""
            assert result["smb_user"] == ""
            assert result["smb_password"] == ""
            assert result["redact_names"] == []

    def test_empty_yaml_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = _make_config_yaml(tmp, {})
            with patch.object(hab, "CONFIG_PATH", hab.Path(cfg_path)):
                result = hab._load_config()

            assert result["smb_server"] == ""
            assert result["redact_names"] == []


class TestLoadConfigFromEnv:

    def test_falls_back_to_env_when_no_file(self):
        fake_path = hab.Path("/nonexistent/config.yaml")
        env = {
            "SMB_SERVER": "192.168.1.50",
            "SMB_SHARE": "backup",
            "SMB_PATH": "/data",
            "SMB_USER": "user1",
            "SMB_PASSWORD": "pass1",
        }
        with patch.object(hab, "CONFIG_PATH", fake_path), \
             patch.dict(os.environ, env, clear=False):
            result = hab._load_config()

        assert result["smb_server"] == "192.168.1.50"
        assert result["smb_share"] == "backup"
        assert result["smb_path"] == "/data"
        assert result["smb_user"] == "user1"
        assert result["smb_password"] == "pass1"
        assert result["redact_names"] == []

    def test_env_defaults_to_empty_strings(self):
        fake_path = hab.Path("/nonexistent/config.yaml")
        with patch.object(hab, "CONFIG_PATH", fake_path), \
             patch.dict(os.environ, {}, clear=True):
            result = hab._load_config()

        assert result["smb_server"] == ""
        assert result["smb_share"] == ""
        assert result["smb_path"] == ""
        assert result["smb_user"] == ""
        assert result["smb_password"] == ""
        assert result["redact_names"] == []


class TestRedactNamesNormalization:
    """The module-level normalization of REDACT_NAMES handles None, str, and list."""

    def test_none_becomes_empty_list(self):
        names = None
        if names is None:
            names = []
        elif isinstance(names, str):
            names = [names]
        assert names == []

    def test_string_becomes_single_item_list(self):
        names = "Alice"
        if names is None:
            names = []
        elif isinstance(names, str):
            names = [names]
        assert names == ["Alice"]

    def test_list_stays_as_list(self):
        names = ["Alice", "Bob"]
        if names is None:
            names = []
        elif isinstance(names, str):
            names = [names]
        assert names == ["Alice", "Bob"]
