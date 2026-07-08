"""The SEC User-Agent / ``.env`` config contract.

The CLI calls ``load_dotenv()`` at startup and then builds a fresh ``Config``,
so a ``SEC_GOV_USER_AGENT`` set in a local ``.env`` reaches the EDGAR client.
These tests exercise that env -> ``Config`` path without any network access.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from robosystems_xbrl_holon.config import DEFAULT_USER_AGENT, Config


def test_env_user_agent_overrides_default(monkeypatch):
  monkeypatch.setenv("SEC_GOV_USER_AGENT", "Acme Corp ops@acme.com")
  cfg = Config()
  assert cfg.user_agent == "Acme Corp ops@acme.com"
  assert cfg.headers["User-Agent"] == "Acme Corp ops@acme.com"


def test_default_user_agent_when_unset(monkeypatch):
  monkeypatch.delenv("SEC_GOV_USER_AGENT", raising=False)
  assert Config().user_agent == DEFAULT_USER_AGENT


def test_dotenv_file_populates_config(tmp_path):
  """A ``.env`` loaded via ``load_dotenv`` flows into a fresh ``Config``."""
  # load_dotenv mutates os.environ directly, so save/restore around it rather
  # than relying on monkeypatch (which can't unwind that external mutation).
  original = os.environ.pop("SEC_GOV_USER_AGENT", None)
  try:
    env = tmp_path / ".env"
    env.write_text('SEC_GOV_USER_AGENT="Dotenv User dev@example.com"\n')
    load_dotenv(dotenv_path=env, override=True)
    assert Config().user_agent == "Dotenv User dev@example.com"
  finally:
    if original is None:
      os.environ.pop("SEC_GOV_USER_AGENT", None)
    else:
      os.environ["SEC_GOV_USER_AGENT"] = original


def test_env_example_template_is_tracked_and_documents_user_agent():
  """The tracked template must survive the ``.env*`` gitignore un-ignore."""
  example = Path(__file__).resolve().parent.parent / ".env.example"
  assert example.exists()
  assert "SEC_GOV_USER_AGENT" in example.read_text()
