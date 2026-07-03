"""Pytest configuration for this repo.

Python scripts live under scripts/ (not the repo root). Tests import them
directly, e.g. ``from home_assistant_backup import _process_backup_files``.
This file prepends scripts/ to sys.path before any test modules load so those
imports resolve without installing the package or running from scripts/.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))


@pytest.fixture(autouse=True)
def _isolate_sanitize_dirs(monkeypatch):
  '''Prevent tests from redacting the real dashboards/ and packages/ trees.'''
  monkeypatch.setattr(
    'home_assistant_backup.DASHBOARDS_DIR',
    str(Path(__file__).resolve().parent / '__no_dashboards__'),
  )
  monkeypatch.setattr(
    'home_assistant_backup.PACKAGES_DIR',
    str(Path(__file__).resolve().parent / '__no_packages__'),
  )
