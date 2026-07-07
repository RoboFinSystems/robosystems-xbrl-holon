"""robosystems-xbrl-holon — a SEC XBRL filing to a portable ``holon.jsonld``.

Fetch a filing from EDGAR, parse it into the neutral :class:`XbrlModel`, and
project that into the canonical scene/boundary/projection holon that renders
offline in the RoboSystems holon viewer.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .model import XbrlModel


def _get_version() -> str:
  try:
    return version("robosystems-xbrl-holon")
  except PackageNotFoundError:
    return "0.0.0+development"


__version__ = _get_version()

__all__ = ("XbrlModel", "__version__")
