"""Serialize the neutral ``XbrlModel`` into the canonical ``holon.jsonld``.

:func:`to_holon` is the public entry point; :func:`classify_network` is the
presentation-network → primary-statement heuristic it uses (exported for reuse
and testing).
"""

from __future__ import annotations

from .classify import classify_network
from .holon import to_holon

__all__ = ("classify_network", "to_holon")
