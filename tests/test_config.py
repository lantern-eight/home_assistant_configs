"""Tests for load_config (utils) and _normalize_redact_entities (home_assistant_backup)."""

import os
import tempfile
from unittest.mock import patch

import pytest
import yaml

import home_assistant_backup as hab
import utils


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
        "redact_entities": ["Alice", "Bob"],
        "token": "my_token",
        "ha_base_url": "http://192.168.1.1:8123",
      }
      cfg_path = _make_config_yaml(tmp, cfg_data)
      with patch.object(utils, "CONFIG_PATH", utils.Path(cfg_path)):
        result = utils.load_config()

      assert result["smb_server"] == "10.0.0.1"
      assert result["smb_share"] == "ha_share"
      assert result["smb_path"] == "config/path"
      assert result["smb_user"] == "admin"
      assert result["smb_password"] == "secret"
      assert result["redact_entities"] == ["Alice", "Bob"]
      assert result["token"] == "my_token"
      assert result["ha_base_url"] == "http://192.168.1.1:8123"

  def test_missing_optional_fields_default_to_empty(self):
    with tempfile.TemporaryDirectory() as tmp:
      cfg_path = _make_config_yaml(tmp, {"smb_server": "10.0.0.1"})
      with patch.object(utils, "CONFIG_PATH", utils.Path(cfg_path)):
        result = utils.load_config()

      assert result["smb_server"] == "10.0.0.1"
      assert result["smb_share"] == ""
      assert result["smb_path"] == ""
      assert result["smb_user"] == ""
      assert result["smb_password"] == ""
      assert result["token"] == ""
      assert result["redact_entities"] == []
      assert result["ha_base_url"] == utils.HA_BASE_URL

  def test_empty_yaml_file(self):
    with tempfile.TemporaryDirectory() as tmp:
      cfg_path = _make_config_yaml(tmp, {})
      with patch.object(utils, "CONFIG_PATH", utils.Path(cfg_path)):
        result = utils.load_config()

      assert result["smb_server"] == ""
      assert result["redact_entities"] == []


class TestLoadConfigFromEnv:

  def test_falls_back_to_env_when_no_file(self):
    fake_path = utils.Path("/nonexistent/config.yaml")
    env = {
      "SMB_SERVER": "192.168.1.50",
      "SMB_SHARE": "backup",
      "SMB_PATH": "/data",
      "SMB_USER": "user1",
      "SMB_PASSWORD": "pass1",
      "HA_TOKEN": "env_token",
    }
    with patch.object(utils, "CONFIG_PATH", fake_path), \
         patch.dict(os.environ, env, clear=False):
      result = utils.load_config(allow_env_fallback=True)

    assert result["smb_server"] == "192.168.1.50"
    assert result["smb_share"] == "backup"
    assert result["smb_path"] == "/data"
    assert result["smb_user"] == "user1"
    assert result["smb_password"] == "pass1"
    assert result["token"] == "env_token"
    assert result["redact_entities"] == []

  def test_env_defaults_to_empty_strings(self):
    fake_path = utils.Path("/nonexistent/config.yaml")
    with patch.object(utils, "CONFIG_PATH", fake_path), \
         patch.dict(os.environ, {}, clear=True):
      result = utils.load_config(allow_env_fallback=True)

    assert result["smb_server"] == ""
    assert result["smb_share"] == ""
    assert result["smb_path"] == ""
    assert result["smb_user"] == ""
    assert result["smb_password"] == ""
    assert result["token"] == ""
    assert result["redact_entities"] == []

  def test_exits_without_fallback_when_no_file(self):
    fake_path = utils.Path("/nonexistent/config.yaml")
    with patch.object(utils, "CONFIG_PATH", fake_path):
      with pytest.raises(SystemExit):
        utils.load_config()


class TestRedactEntitiesNormalization:
  """The module-level normalization of redact_entities handles None, str, and list."""

  def test_none_becomes_empty_list(self):
    assert hab._normalize_redact_entities(None) == []

  def test_string_becomes_single_item_list(self):
    assert hab._normalize_redact_entities("Alice") == ["Alice"]

  def test_list_stays_as_list(self):
    assert hab._normalize_redact_entities(["Alice", "Bob"]) == ["Alice", "Bob"]
