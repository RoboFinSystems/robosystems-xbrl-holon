"""Minimal EDGAR package shim so Arelle can load the vendored ``EDGAR.transform``
plugin (the SEC inline-XBRL transformation registry) without the full EDGAR
plugin (which pulls in the matplotlib-backed renderer we do not need)."""
