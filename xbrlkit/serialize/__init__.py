"""Projections of the neutral ``XbrlModel`` into portable serializations.

:func:`to_holon` is the RDF/JSON-LD projection, :func:`to_tavi` the Project Tavi
compiled model, and :func:`to_oim` the xBRL-JSON (OIM) report — the only one
with a reference implementation to check against. :func:`build_holon_graph` exposes the flat RDF
graph the holon partitions (for SPARQL / SHACL). :func:`classify_network` is the
legacy four-primary heuristic, retained for callers that want it — the holon
itself emits no semantic block type.
"""

from __future__ import annotations

from .classify import classify_network
from .graph import build_holon_graph
from .holon import to_holon
from .oim import to_oim, to_oim_document
from .tavi import GapReport, to_tavi, to_tavi_report

__all__ = (
  "GapReport",
  "build_holon_graph",
  "classify_network",
  "to_holon",
  "to_oim",
  "to_oim_document",
  "to_tavi",
  "to_tavi_report",
)
