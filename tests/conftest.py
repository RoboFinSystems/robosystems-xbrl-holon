"""Shared pytest fixtures for the robosystems-xbrl-holon test suite."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_output_dir(tmp_path: Path) -> Path:
  """Return a temporary directory for tests that write output artifacts."""
  out = tmp_path / "output"
  out.mkdir()
  return out
