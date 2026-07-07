"""EdgarClient — a small synchronous SEC EDGAR client.

Mirrors the robosystems SEC adapter's client layer (ticker→CIK resolution,
submissions pagination, XBRL-zip URL construction) but platform-free: it reads
all settings from :class:`robosystems_xbrl_holon.config.Config`, uses
``requests`` synchronously, and throttles every call through a
:class:`~robosystems_xbrl_holon.edgar.rate_limit.RateLimiter`.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

from robosystems_xbrl_holon.config import CONFIG, Config

from .rate_limit import RateLimiter

COMPANY_TICKERS_PATH = "/files/company_tickers.json"


@dataclass
class FilingRef:
  """One filing's identity, enough to build its Archives URL and load it."""

  cik: str
  accession: str
  form: str
  filing_date: str
  primary_document: str
  is_inline: bool


class EdgarClient:
  """Synchronous EDGAR client. One HTTP session, one rate limiter."""

  def __init__(self, config: Config = CONFIG) -> None:
    self.config: Config = config
    self._session: requests.Session = requests.Session()
    self._session.headers.update(config.headers)
    self._limiter: RateLimiter = RateLimiter(config.rate_limit_per_sec)
    self._ticker_map: dict[str, str] | None = None

  def _get(self, url: str) -> requests.Response:
    """Throttled GET that raises on HTTP error."""
    self._limiter.wait()
    resp = self._session.get(url, timeout=self.config.request_timeout)
    resp.raise_for_status()
    return resp

  def ticker_to_cik(self, ticker: str) -> str:
    """Resolve a ticker symbol to its zero-padded 10-digit CIK.

    Fetches (and caches) the SEC ``company_tickers.json`` map. Raises
    :class:`LookupError` if the ticker is unknown.
    """
    if self._ticker_map is None:
      self._ticker_map = self._load_ticker_map()
    key = ticker.upper()
    cik = self._ticker_map.get(key)
    if cik is None:
      raise LookupError(f"Unknown ticker: {ticker}")
    return cik

  def _load_ticker_map(self) -> dict[str, str]:
    url = f"{self.config.sec_base_url}{COMPANY_TICKERS_PATH}"
    data = self._get(url).json()
    ticker_map: dict[str, str] = {}
    for row in data.values():
      symbol = str(row["ticker"]).upper()
      ticker_map[symbol] = f"{int(row['cik_str']):0>10}"
    return ticker_map

  def _get_submissions(self, name: str) -> dict[str, object]:
    url = f"{self.config.sec_data_url}/submissions/{name}"
    return self._get(url).json()

  def list_filings(self, cik: str, forms: list[str] | None = None) -> list[FilingRef]:
    """List a company's filings, newest-first, optionally filtered by form.

    Reads ``filings.recent`` from the main submissions file and merges every
    ``filings.files[].name`` pagination file. ``forms`` (e.g. ``["10-K"]``)
    filters by exact form type when given.
    """
    padded_cik = f"{int(cik):0>10}"
    main = self._get_submissions(f"CIK{padded_cik}.json")
    filings = main.get("filings", {})
    if not isinstance(filings, dict):
      filings = {}

    recent = filings.get("recent", {})
    refs: list[FilingRef] = []
    if isinstance(recent, dict):
      refs.extend(self._refs_from_arrays(padded_cik, recent))

    for file_info in filings.get("files", []) or []:
      name = file_info.get("name")
      if not name:
        continue
      page = self._get_submissions(name)
      refs.extend(self._refs_from_arrays(padded_cik, page))

    if forms is not None:
      wanted = set(forms)
      refs = [ref for ref in refs if ref.form in wanted]

    refs.sort(key=lambda ref: ref.filing_date, reverse=True)
    return refs

  @staticmethod
  def _refs_from_arrays(padded_cik: str, arrays: dict[str, object]) -> list[FilingRef]:
    accessions = arrays.get("accessionNumber") or []
    if not isinstance(accessions, list):
      return []
    forms = arrays.get("form") or []
    dates = arrays.get("filingDate") or []
    primary = arrays.get("primaryDocument") or []
    inline = arrays.get("isInlineXBRL") or []

    def at(seq: object, i: int) -> object:
      return seq[i] if isinstance(seq, list) and i < len(seq) else None

    refs: list[FilingRef] = []
    for i in range(len(accessions)):
      refs.append(
        FilingRef(
          cik=padded_cik,
          accession=str(accessions[i]),
          form=str(at(forms, i) or ""),
          filing_date=str(at(dates, i) or ""),
          primary_document=str(at(primary, i) or ""),
          is_inline=bool(at(inline, i)),
        )
      )
    return refs

  def get_filing_ref(self, cik: str, accession: str) -> FilingRef:
    """Return the :class:`FilingRef` for one accession.

    Falls back to a minimal ref (form/date unknown, ``is_inline=True``) when
    the accession is not found in the submissions history, so downloads can
    still proceed by URL construction alone.
    """
    padded_cik = f"{int(cik):0>10}"
    for ref in self.list_filings(cik):
      if ref.accession == accession:
        return ref
    return FilingRef(
      cik=padded_cik,
      accession=accession,
      form="",
      filing_date="",
      primary_document="",
      is_inline=True,
    )
