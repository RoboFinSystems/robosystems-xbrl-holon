"""Unit tests for the ``edgar`` fetch layer (no network by default).

The lone live test is marked ``integration`` and skipped in normal runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from xbrlkit.edgar import EdgarClient, download_filing
from xbrlkit.edgar.download import _xbrl_zip_url


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
      import requests

      raise requests.HTTPError(f"HTTP {self.status_code}", response=self)  # type: ignore[arg-type]


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
  from xbrlkit.edgar.client import FilingRef

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


def test_company_info_keeps_edgar_header_values_as_they_come():
  """EDGAR writes an unknown value as "" as often as null. The platform stores them
  as they come, except the website, whose fallback chain ends in None."""
  from xbrlkit.edgar.client import company_info_from_submissions

  info = company_info_from_submissions(
    "0001341439",
    {
      "name": "ORACLE CORP",
      "ein": "542185193",
      "tickers": ["ORCL"],
      "exchanges": ["NYSE"],
      "sic": "7372",
      "sicDescription": "Services-Prepackaged Software",
      "stateOfIncorporation": "",
      "fiscalYearEnd": "0531",
      "entityType": "operating",
      "category": "Large accelerated filer",
      "website": "",
      "investorWebsite": "",
      "phone": "(737) 867-1000",
    },
  )
  assert info.state_of_incorporation == ""
  assert info.website is None
  assert (info.ticker, info.exchange, info.phone) == ("ORCL", "NYSE", "(737) 867-1000")
  assert info.fiscal_year_end == "0531" and info.entity_type == "operating"
  empty = company_info_from_submissions("0000000001", {})
  assert empty.name is None and empty.ticker is None and empty.ein is None


# ---- throttle policy, company tickers, complete submissions ----------------------


class _Response(FakeResponse):
  def __init__(self, payload=None, status_code=200, content=b"x", headers=None):
    super().__init__(payload, status_code, content)
    self.headers = headers or {}


def _queued(
  monkeypatch: pytest.MonkeyPatch, responses: list
) -> tuple[EdgarClient, list[str]]:
  from xbrlkit.config import Config

  client = EdgarClient(Config(rate_limit_per_sec=0, throttle_backoff_s=2))
  urls: list[str] = []
  queue = list(responses)

  def get(url, timeout=None):
    urls.append(url)
    return queue.pop(0)

  monkeypatch.setattr(client._session, "get", get)
  return client, urls


def test_get_waits_out_a_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
  from xbrlkit.edgar import client as client_module

  sleeps: list[float] = []
  monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
  client, urls = _queued(
    monkeypatch,
    [_Response(status_code=429, headers={"Retry-After": "9"}), _Response({"a": 1})],
  )
  assert client._get("https://data.sec.gov/x").json() == {"a": 1}
  assert sleeps == [9.0] and len(urls) == 2


def test_get_treats_an_empty_200_as_a_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
  from xbrlkit.edgar import client as client_module

  sleeps: list[float] = []
  monkeypatch.setattr(client_module.time, "sleep", sleeps.append)
  client, _ = _queued(
    monkeypatch, [_Response(content=b"  "), _Response({"a": 1}, content=b"{}")]
  )
  assert client._get("https://data.sec.gov/x").json() == {"a": 1}
  assert sleeps == [2.0]  # Config.throttle_backoff_s


def test_get_gives_up_after_bounded_retries(monkeypatch: pytest.MonkeyPatch) -> None:
  from xbrlkit.edgar import EdgarThrottled
  from xbrlkit.edgar import client as client_module

  monkeypatch.setattr(client_module.time, "sleep", lambda s: None)
  client, urls = _queued(monkeypatch, [_Response(status_code=503)] * 10)
  with pytest.raises(EdgarThrottled):
    client._get("https://data.sec.gov/x")
  assert len(urls) == client_module.MAX_RETRIES + 1


def test_company_tickers_returns_the_raw_map(monkeypatch: pytest.MonkeyPatch) -> None:
  payload = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
  client, urls = _queued(monkeypatch, [_Response(payload)])
  assert client.company_tickers() == payload
  assert urls[0].endswith("/files/company_tickers.json")


def test_complete_submissions_merges_every_page(
  monkeypatch: pytest.MonkeyPatch,
) -> None:
  main = {
    "cik": "320193",
    "name": "Apple Inc.",
    "filings": {
      "recent": {"accessionNumber": ["a3", "a2"], "form": ["10-K", "10-Q"]},
      "files": [{"name": "CIK0000320193-submissions-001.json"}, {"name": "gone.json"}],
    },
  }
  page = {"accessionNumber": ["a1"], "form": ["10-K"], "extra": ["ignored"]}
  client, urls = _queued(
    monkeypatch, [_Response(main), _Response(page), _Response(status_code=404)]
  )

  merged = client.complete_submissions("320193")

  assert merged["name"] == "Apple Inc."
  assert merged["filings"] == {
    "accessionNumber": ["a3", "a2", "a1"],
    "form": ["10-K", "10-Q", "10-K"],
  }
  assert merged["_metadata"]["totalFilings"] == 3
  assert merged["_metadata"]["paginationFilesMerged"] == 1
  assert urls[1].endswith("/submissions/CIK0000320193-submissions-001.json")
