"""Tests for the holon projection (``serialize/``).

Covers the presentation-network classifier, the model → ``holon.jsonld``
projection (three named graphs, an InformationBlock, facts grouped by
factSet), and a SHACL drift-guard over the exact bundle the holon serializes
from.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from robosystems_xbrl_holon.model import (
  Arc,
  Concept,
  EntityIdentity,
  FilingMeta,
  Network,
  Period,
  Unit,
  XbrlFact,
  XbrlModel,
)
from robosystems_xbrl_holon.serialize import classify_network, to_holon
from robosystems_xbrl_holon.serialize._kernel.jsonld import build_graph, shacl_report
from robosystems_xbrl_holon.serialize.holon import build_bundle


def _model() -> XbrlModel:
  """A minimal, hand-authored single-filing model: a two-line balance sheet."""
  filing = FilingMeta(
    accession="0000000000-24-000001",
    cik="0001234567",
    form="10-K",
    taxonomy_namespaces=["http://fasb.org/us-gaap/2024-01-31"],
  )
  entity = EntityIdentity(
    cik="0001234567",
    name="Acme Corp",
    legal_name="Acme Corporation",
    ein="12-3456789",
  )
  concepts = {
    "us-gaap:Assets": Concept(
      qname="us-gaap:Assets",
      namespace="http://fasb.org/us-gaap/2024-01-31",
      name="Assets",
      period_type="instant",
      balance="debit",
      is_numeric=True,
      item_type="monetaryItemType",
      substitution_group="xbrli:item",
      pref_label="Assets",
    ),
    "us-gaap:Cash": Concept(
      qname="us-gaap:Cash",
      namespace="http://fasb.org/us-gaap/2024-01-31",
      name="CashAndCashEquivalentsAtCarryingValue",
      period_type="instant",
      balance="debit",
      is_numeric=True,
      item_type="monetaryItemType",
      substitution_group="xbrli:item",
      pref_label="Cash",
    ),
  }
  periods = [Period(id="I-2024", period_type="instant", end=date(2024, 12, 31))]
  units = [Unit(id="usd", measure="iso4217:USD")]
  facts = [
    XbrlFact(
      id="f1",
      concept_qname="us-gaap:Assets",
      period_id="I-2024",
      unit_id="usd",
      entity_cik="0001234567",
      numeric_value=1000.0,
      decimals="-3",
      value_kind="numeric",
    ),
    XbrlFact(
      id="f2",
      concept_qname="us-gaap:Cash",
      period_id="I-2024",
      unit_id="usd",
      entity_cik="0001234567",
      numeric_value=250.0,
      decimals="-3",
      value_kind="numeric",
    ),
    # A text fact — must be shed by the numeric-only projection.
    XbrlFact(
      id="f3",
      concept_qname="dei:EntityRegistrantName",
      period_id="I-2024",
      entity_cik="0001234567",
      value_str="Acme Corp",
      value_kind="text",
    ),
  ]
  networks = [
    Network(
      role_uri="http://acme.com/role/BalanceSheet",
      definition="Consolidated Balance Sheets",
      kind="presentation",
      arcs=[Arc(from_qname="us-gaap:Assets", to_qname="us-gaap:Cash", order=1.0)],
    ),
    Network(
      role_uri="http://acme.com/role/BalanceSheet",
      definition="Consolidated Balance Sheets",
      kind="calculation",
      arcs=[
        Arc(from_qname="us-gaap:Assets", to_qname="us-gaap:Cash", order=1.0, weight=1.0)
      ],
    ),
  ]
  return XbrlModel(
    filing=filing,
    entity=entity,
    concepts=concepts,
    periods=periods,
    units=units,
    facts=facts,
    networks=networks,
  )


def _types(node: dict[str, Any]) -> list[str]:
  t = node.get("@type", [])
  return t if isinstance(t, list) else [t]


def _all_nodes(doc: dict[str, Any]) -> list[dict[str, Any]]:
  nodes: list[dict[str, Any]] = []
  for entry in doc.get("@graph", []):
    if isinstance(entry, dict) and "@graph" in entry:
      nodes.extend(entry["@graph"])
    elif isinstance(entry, dict):
      nodes.append(entry)
  return nodes


def test_classify_network() -> None:
  assert classify_network("x", "Consolidated Balance Sheets") == "balance_sheet"
  assert (
    classify_network("x", "Consolidated Statements of Financial Position")
    == "balance_sheet"
  )
  assert classify_network("x", "Consolidated Statements of Operations") == (
    "income_statement"
  )
  assert (
    classify_network("x", "Statements of Comprehensive Income") == "income_statement"
  )
  assert classify_network("x", "Consolidated Statements of Cash Flows") == (
    "cash_flow_statement"
  )
  assert (
    classify_network("x", "Statement of Stockholders' Equity") == "equity_statement"
  )
  # Non-primary + parenthetical networks are skipped.
  assert classify_network("x", "Notes to the Financial Statements") is None
  assert classify_network("x", "Balance Sheet (Parenthetical)") is None
  # Role-URI fallback when the definition does not classify.
  assert classify_network("http://x/role/BalanceSheet", None) == "balance_sheet"


def test_to_holon_three_named_graphs() -> None:
  doc = json.loads(to_holon(_model()))
  assert "@graph" in doc

  ids = {
    entry.get("@id", "")
    for entry in doc["@graph"]
    if isinstance(entry, dict) and "@graph" in entry
  }
  assert any(i.endswith("#scene") for i in ids)
  assert any(i.endswith("#boundary") for i in ids)
  assert any(i.endswith("#projection") for i in ids)


def test_to_holon_information_block_and_facts() -> None:
  doc = json.loads(to_holon(_model()))
  nodes = _all_nodes(doc)

  ib_nodes = [n for n in nodes if "rs:InformationBlock" in _types(n)]
  assert ib_nodes, "expected at least one rs:InformationBlock"

  fact_nodes = [n for n in nodes if "rs:Fact" in _types(n)]
  # Only the two numeric facts survive; the text fact is shed.
  assert len(fact_nodes) == 2
  assert all("factSet" in n for n in fact_nodes), (
    "every projected fact should carry rs:factSet"
  )


def test_bundle_shacl_conforms() -> None:
  # Drift-guard: the exact bundle the holon serializes from must satisfy the
  # rs: structural topology (positive Fact/Association shapes + banned dialects).
  bundle = build_bundle(_model())
  result = shacl_report(build_graph(bundle))
  assert result.ran
  assert result.conforms, result.report
