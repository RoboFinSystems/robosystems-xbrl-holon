"""EDGAR fetch layer — resolve tickers, list filings, download XBRL zips,
discover filings in bulk through EFTS.

Platform-free: synchronous ``requests``, local-filesystem output, all settings
from :class:`xbrlkit.config.Config`, and EDGAR's two throttle signatures (a 429,
an empty 200) ridden out with a bounded wait-and-retry.
"""

from __future__ import annotations

from .client import CompanyInfo, EdgarClient, EdgarThrottled, FilingRef
from .download import download_filing, fetch
from .efts import EftsClient, EftsHit, query_efts

__all__ = [
  "CompanyInfo",
  "EdgarClient",
  "EdgarThrottled",
  "EftsClient",
  "EftsHit",
  "FilingRef",
  "download_filing",
  "fetch",
  "query_efts",
]
