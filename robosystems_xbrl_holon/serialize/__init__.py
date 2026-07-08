"""Serialize the neutral ``XbrlModel`` into the canonical ``holon.jsonld``.

:func:`to_holon` is the public entry point; :func:`build_holon_graph` exposes the
flat RDF graph it partitions (for SPARQL / SHACL). :func:`classify_network` is
the legacy four-primary heuristic, retained for callers that want it — the holon
itself emits no semantic block type.
"""

from __future__ import annotations

from .classify import classify_network
from .graph import build_holon_graph
from .holon import to_holon

__all__ = ("build_holon_graph", "classify_network", "to_holon")
