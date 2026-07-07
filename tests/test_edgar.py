"""Unit tests for the ``edgar`` fetch layer (no network by default).

The lone live test is marked ``integration`` and skipped in normal runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from robosystems_xbrl_holon.edgar import EdgarClient, download_filing
from robosystems_xbrl_holon.edgar.download import _xbrl_zip_url


class FakeResponse:
  """Minimal stand-in for ``requests.Response``."""

  def __init__(
    self, payload: Any = None, status_code: int = 200, content: bytes = b"x"
  ) -> None:
    self._payload = payload
    self.status_code = status_code
    self.content = content

  def json(self) -> Any:
    return self._payload

  def raise_for_status(self) -> None:
    if self.status_code >= 400:
      raise AssertionError(f"HTTP {self.status_code}")


def test_xbrl_zip_url_cik_zero_strip_and_accession_dashes() -> None:
  # Padded CIK -> leading zeros stripped; accession dashes stripped in the
  # path segment but kept in the .zip filename.
  url = _xbrl_zip_url("https://www.sec.gov", "0000320193", "0000320193-24-000123")
  assert url == (
    "https://www.sec.gov/Archives/edgar/data/"
    "320193/000032019324000123/0000320193-24-000123-xbrl.zip"
  )


def test_xbrl_zip_url_plain_int_cik() -> None:
  # A non-padded CIK string resolves identically.
  url = _xbrl_zip_url("https://www.sec.gov", "320193", "0000320193-24-000123")
  assert "/edgar/data/320193/000032019324000123/" in url
  assert url.endswith("0000320193-24-000123-xbrl.zip")


def test_ticker_map_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
  payload = {
    "0": {"cik_str": 320193, "ticker": "aapl", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
  }
  client = EdgarClient()
  monkeypatch.setattr(client._session, "get", lambda *a, **k: FakeResponse(payload))

  # Ticker is upper-cased; CIK is zero-padded to 10 digits.
  assert client.ticker_to_cik("AAPL") == "0000320193"
  assert client.ticker_to_cik("aapl") == "0000320193"
  assert client.ticker_to_cik("msft") == "0000789019"


def test_ticker_unknown_raises(monkeypatch: pytest.MonkeyPatch) -> None:
  payload = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple"}}
  client = EdgarClient()
  monkeypatch.setattr(client._session, "get", lambda *a, **k: FakeResponse(payload))
  with pytest.raises(LookupError):
    client.ticker_to_cik("NOPE")


def test_download_filing_404_raises(
  monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
  client = EdgarClient()
  from robosystems_xbrl_holon.edgar.client import FilingRef

  monkeypatch.setattr(
    client,
    "get_filing_ref",
    lambda cik, accession: FilingRef(
      cik=f"{int(cik):0>10}",
      accession=accession,
      form="",
      filing_date="",
      primary_document="",
      is_inline=True,
    ),
  )
  monkeypatch.setattr(
    client._session,
    "get",
    lambda *a, **k: FakeResponse(status_code=404, content=b""),
  )
  with pytest.raises(FileNotFoundError):
    download_filing(client, "320193", "0000320193-24-000123", tmp_path)


@pytest.mark.integration
def test_live_aapl_ticker_to_cik() -> None:
  client = EdgarClient()
  assert client.ticker_to_cik("AAPL") == "0000320193"
