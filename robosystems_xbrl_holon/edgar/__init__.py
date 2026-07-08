"""EDGAR fetch layer — resolve tickers, list filings, download XBRL zips.

A platform-free mirror of the robosystems SEC adapter client: synchronous
``requests``, local-filesystem output, all settings from
:class:`robosystems_xbrl_holon.config.Config`.
"""

from __future__ import annotations

from .client import CompanyInfo, EdgarClient, FilingRef
from .download import download_filing, fetch

__all__ = ["CompanyInfo", "EdgarClient", "FilingRef", "download_filing", "fetch"]
