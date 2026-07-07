"""Deterministic identity for parsed XBRL nodes.

Mirrors the robosystems SEC adapter's UUID5 scheme (``processors/ids.py``):
every id is ``uuid.uuid5(NAMESPACE, f"{kind}:{content}")`` against a fixed
package namespace UUID, so the same input always yields the same id across
runs, processes, and machines.

Two families of id:

- **Shared nodes** (Element / Period / Unit / Entity / Label) hash content
  only, so identical values dedupe *across* filings — e.g. ``iso4217:USD`` or
  the period ``2024-12-31`` resolve to one id no matter which filing produced
  them.
- **Report-scoped nodes** (Fact / dimension) fold the report URI into the
  content so facts from different filings never collide.

In-memory the neutral model only needs stable Period/Unit ids to dedupe those
lists; the helpers return plain strings.
"""

from __future__ import annotations

import uuid

# Fixed package namespace. Distinct from the robosystems platform namespace so
# ids minted here never collide with the platform pipeline's ids.
NAMESPACE = uuid.UUID("6f2a1c0e-3b4d-5a6f-8c9d-0e1f2a3b4c5d")


def _mint(kind: str, content: str) -> str:
  """Return the deterministic UUID5 string for ``kind`` + ``content``."""
  return str(uuid.uuid5(NAMESPACE, f"{kind}:{content}"))


def element_id(namespace: str, name: str) -> str:
  """Id for a concept/element, keyed by its namespace + local name."""
  return _mint("element", f"{namespace}#{name}")


def period_id(period_uri: str) -> str:
  """Id for a reporting period, keyed by its content-derived URI."""
  return _mint("period", period_uri)


def unit_id(measure_uri: str) -> str:
  """Id for a unit of measure, keyed by its resolved measure URI."""
  return _mint("unit", measure_uri)


def entity_id(entity_uri: str) -> str:
  """Id for a reporting entity, keyed by its canonical scheme#cik URI."""
  return _mint("entity", entity_uri)


def label_id(value: str, role: str | None, language: str | None) -> str:
  """Id for a label-linkbase entry, keyed by value/role/language."""
  return _mint("label", f"{value}#{role}#{language}")


def fact_id(report_uri: str, md5: str) -> str:
  """Id for a reported fact — report-scoped by ``report_uri``."""
  return _mint("fact", f"{report_uri}#fact-{md5}")


def dimension_id(report_uri: str, axis_uri: str, member: str) -> str:
  """Id for a fact dimension — report-scoped, keyed by axis + member."""
  return _mint("dimension", f"{report_uri}#dimension-{axis_uri}-{member}")
