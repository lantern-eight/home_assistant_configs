"""Pytest configuration for this repo.

Python scripts live under scripts/ (not the repo root). Tests import them
directly, e.g. ``from ha_sync import _process_backup_files``.
This file prepends scripts/ to sys.path before any test modules load so those
imports resolve without installing the package or running from scripts/.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))


def _write_file(directory: str, name: str, content: str) -> str:
  path = os.path.join(directory, name)
  os.makedirs(os.path.dirname(path), exist_ok=True)
  with open(path, "w", encoding="utf-8") as f:
    f.write(content)
  return path


def _read_file(path: str) -> str:
  with open(path, "r", encoding="utf-8") as f:
    return f.read()


@pytest.fixture(autouse=True)
def _isolate_sanitize_dirs(monkeypatch):
  '''Prevent tests from redacting the real dashboards/ and packages/ trees.'''
  monkeypatch.setattr(
    'ha_sync.DASHBOARDS_DIR',
    str(Path(__file__).resolve().parent / '__no_dashboards__'),
  )
  monkeypatch.setattr(
    'ha_sync.PACKAGES_DIR',
    Path(__file__).resolve().parent / '__no_packages__',
  )
