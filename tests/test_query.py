"""Tests for the in-memory SPARQL query layer (``query.py``).

Round-trips a hand-authored model through ``to_holon`` → ``parse_holon`` →
``fact_grid`` and asserts the consolidated-slice semantics that back MCP parity:
dimensional breakdowns are excluded, facts dedup on ``(qname, end)`` keeping the
newest, and period-type filtering works.
"""

from __future__ import annotations

from datetime import date

from robosystems_xbrl_holon.model import (
  Concept,
  DimQualifier,
  EntityIdentity,
  FilingMeta,
  Network,
  Arc,
  Period,
  Unit,
  XbrlFact,
  XbrlModel,
)
from robosystems_xbrl_holon.query import fact_grid, parse_holon
from robosystems_xbrl_holon.serialize import to_holon


def _model() -> XbrlModel:
  """Revenue reported consolidated (two years) plus one segment breakdown."""
  concepts = {
    "us-gaap:Revenues": Concept(
      qname="us-gaap:Revenues",
      namespace="http://fasb.org/us-gaap/2024-01-31",
      name="Revenues",
      period_type="duration",
      balance="credit",
      is_numeric=True,
      item_type="monetaryItemType",
      pref_label="Revenues",
    ),
  }
  periods = [
    Period(
      id="D-2024",
      period_type="duration",
      start=date(2024, 1, 1),
      end=date(2024, 12, 31),
      duration_type="annual",
    ),
    Period(
      id="D-2023",
      period_type="duration",
      start=date(2023, 1, 1),
      end=date(2023, 12, 31),
      duration_type="annual",
    ),
  ]
  units = [Unit(id="usd", measure="iso4217:USD")]
  seg = DimQualifier(
    axis_qname="us-gaap:StatementBusinessSegmentsAxis",
    member_qname="acme:WidgetsMember",
    is_explicit=True,
    axis_type="segment",
  )
  facts = [
    XbrlFact(
      id="c24",
      concept_qname="us-gaap:Revenues",
      period_id="D-2024",
      unit_id="usd",
      entity_cik="0001234567",
      numeric_value=1000.0,
      value_kind="numeric",
    ),
    XbrlFact(
      id="d24",  # a dimensional breakdown for the same concept + period
      concept_qname="us-gaap:Revenues",
      period_id="D-2024",
      unit_id="usd",
      entity_cik="0001234567",
      dims=[seg],
      numeric_value=600.0,
      value_kind="numeric",
    ),
    XbrlFact(
      id="c23",
      concept_qname="us-gaap:Revenues",
      period_id="D-2023",
      unit_id="usd",
      entity_cik="0001234567",
      numeric_value=900.0,
      value_kind="numeric",
    ),
  ]
  networks = [
    Network(
      role_uri="http://acme.com/role/Income",
      definition="Consolidated Statements of Operations",
      kind="presentation",
      arcs=[Arc(from_qname="us-gaap:Revenues", to_qname="us-gaap:Revenues", order=1.0)],
    )
  ]
  return XbrlModel(
    filing=FilingMeta(accession="0000000000-24-000003", cik="0001234567", form="10-K"),
    entity=EntityIdentity(cik="0001234567", name="Acme"),
    concepts=concepts,
    periods=periods,
    units=units,
    facts=facts,
    networks=networks,
  )


def _graph():
  return parse_holon(to_holon(_model()))


def test_fact_grid_excludes_dimensional_breakdowns() -> None:
  rows = fact_grid(_graph(), elements=["us-gaap:Revenues"], period_type="annual")
  by_end = {r.end_date: r.value for r in rows}
  # The 600 segment breakdown must never surface as a consolidated value.
  assert by_end == {"2024-12-31": 1000.0, "2023-12-31": 900.0}


def test_fact_grid_period_filter() -> None:
  rows = fact_grid(
    _graph(),
    elements=["us-gaap:Revenues"],
    periods=["2024-12-31"],
    period_type="annual",
  )
  assert len(rows) == 1
  assert rows[0].value == 1000.0
  assert rows[0].qname == "us-gaap:Revenues"


def test_fact_grid_orders_newest_first() -> None:
  rows = fact_grid(_graph(), elements=["us-gaap:Revenues"], period_type="annual")
  assert [r.end_date for r in rows] == ["2024-12-31", "2023-12-31"]
