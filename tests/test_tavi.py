"""Tests for the Project Tavi projection (``serialize/tavi.py``).

Covers the compiled-model envelope, the four core dimensions on a fact, the
abstract-concept split into heading objects, calculation link properties, and
the gap report — the record of what a real filing carries that Tavi has nowhere
to put, which is the substantive output of the projection.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from xbrlkit.model import (
  Arc,
  Concept,
  DimQualifier,
  EntityIdentity,
  FilingMeta,
  Label,
  Network,
  Period,
  Unit,
  XbrlFact,
  XbrlModel,
)
from xbrlkit.serialize import to_tavi, to_tavi_report
from xbrlkit.serialize.tavi import DOCTYPE_COMPILED, RESERVED_NAMESPACES

US_GAAP = "http://fasb.org/us-gaap/2024-01-31"


def _model() -> XbrlModel:
  """A minimal filing: one abstract header, two concepts, a calculation, a share count."""
  concepts = {
    "us-gaap:AssetsAbstract": Concept(
      qname="us-gaap:AssetsAbstract",
      namespace=US_GAAP,
      name="AssetsAbstract",
      is_abstract=True,
      labels=[
        Label(value="Assets [Abstract]", role="http://www.xbrl.org/2003/role/label")
      ],
    ),
    "us-gaap:Assets": Concept(
      qname="us-gaap:Assets",
      namespace=US_GAAP,
      name="Assets",
      period_type="instant",
      balance="debit",
      is_numeric=True,
      item_type="monetaryItemType",
      labels=[Label(value="Assets", role="http://www.xbrl.org/2003/role/label")],
    ),
    "us-gaap:Cash": Concept(
      qname="us-gaap:Cash",
      namespace=US_GAAP,
      name="Cash",
      period_type="instant",
      balance="debit",
      is_numeric=True,
      item_type="monetaryItemType",
      labels=[Label(value="Cash", role="http://www.xbrl.org/2003/role/terseLabel")],
    ),
    "us-gaap:SharesOutstanding": Concept(
      qname="us-gaap:SharesOutstanding",
      namespace=US_GAAP,
      name="SharesOutstanding",
      period_type="instant",
      is_numeric=True,
      item_type="sharesItemType",
    ),
  }
  periods = [
    Period(
      id="p-instant",
      period_type="instant",
      end=date(2024, 12, 31),
      calendar_year=2024,
      calendar_quarter="FY",
      calendar_period_key="2024",
    ),
    Period(
      id="p-duration",
      period_type="duration",
      start=date(2024, 1, 1),
      end=date(2024, 12, 31),
      duration_type="annual",
      calendar_year=2024,
      calendar_quarter="FY",
      calendar_period_key="2024",
    ),
  ]
  facts = [
    XbrlFact(
      id="f1",
      concept_qname="us-gaap:Assets",
      period_id="p-instant",
      unit_id="u-usd",
      entity_cik="0001234567",
      numeric_value=1000.0,
      decimals="-3",
    ),
    XbrlFact(
      id="f2",
      concept_qname="us-gaap:Cash",
      period_id="p-instant",
      unit_id="u-usd",
      entity_cik="0001234567",
      numeric_value=400.0,
      decimals="-3",
      dims=[
        DimQualifier(
          axis_qname="us-gaap:SegmentAxis", member_qname="us-gaap:NorthAmerica"
        )
      ],
    ),
    XbrlFact(
      id="f3",
      concept_qname="us-gaap:SharesOutstanding",
      period_id="p-duration",
      entity_cik="0001234567",
      numeric_value=50.0,
      decimals="INF",
    ),
  ]
  dim = "http://xbrl.org/int/dim/arcrole"
  networks = [
    Network(
      role_uri="http://example.com/role/Segments",
      definition="Segments",
      kind="definition",
      arcs=[
        Arc(
          from_qname="us-gaap:CashAbstract",
          to_qname="us-gaap:SegmentTable",
          arcrole=f"{dim}/all",
          is_root=True,
        ),
        Arc(
          from_qname="us-gaap:SegmentTable",
          to_qname="us-gaap:SegmentAxis",
          arcrole=f"{dim}/hypercube-dimension",
        ),
        Arc(
          from_qname="us-gaap:SegmentAxis",
          to_qname="us-gaap:SegmentDomain",
          arcrole=f"{dim}/dimension-domain",
        ),
        Arc(
          from_qname="us-gaap:SegmentDomain",
          to_qname="us-gaap:NorthAmerica",
          arcrole=f"{dim}/domain-member",
        ),
      ],
    ),
    Network(
      role_uri="http://example.com/role/BalanceSheet",
      definition="Balance Sheet",
      kind="presentation",
      arcs=[
        Arc(
          from_qname="us-gaap:AssetsAbstract",
          to_qname="us-gaap:Assets",
          arcrole="http://www.xbrl.org/2003/arcrole/parent-child",
          order=1.0,
          is_root=True,
        )
      ],
    ),
    Network(
      role_uri="http://example.com/role/BalanceSheet",
      definition="Balance Sheet",
      kind="calculation",
      arcs=[
        Arc(
          from_qname="us-gaap:Assets",
          to_qname="us-gaap:Cash",
          arcrole="http://www.xbrl.org/2003/arcrole/summation-item",
          order=1.0,
          weight=1.0,
          is_root=True,
        )
      ],
    ),
  ]
  return XbrlModel(
    filing=FilingMeta(
      accession="0000000000-24-000001",
      cik="0001234567",
      form="10-K",
      filing_date=date(2025, 2, 14),
      taxonomy_namespaces=[US_GAAP],
    ),
    entity=EntityIdentity(cik="0001234567", name="Acme Corp"),
    concepts=concepts,
    periods=periods,
    units=[Unit(id="u-usd", measure="iso4217:USD")],
    facts=facts,
    networks=networks,
  )


def _document() -> dict[str, Any]:
  document, _ = to_tavi_report(_model())
  return document


def test_compiled_model_envelope() -> None:
  """documentInfo declares a compiled model and binds the reserved prefixes."""
  info = _document()["documentInfo"]
  assert info["documentType"] == DOCTYPE_COMPILED
  namespaces = info["namespaces"]
  for prefix, uri in RESERVED_NAMESPACES.items():
    assert namespaces[prefix] == uri
  # A compiled model must not carry a documentNamespacePrefix (section 4.2.1).
  assert "documentNamespacePrefix" not in info
  assert US_GAAP in namespaces.values()


def test_model_is_a_report() -> None:
  model = _document()["xbrlModel"]
  assert model["modelType"] == "xbrl:report"
  assert {"property": "xbrl:reportFilingDate", "value": "2025-02-14"} in model[
    "properties"
  ]


def test_abstract_concepts_become_headings() -> None:
  """Section 5.3: no reportable value, still on the concept dimension."""
  model = _document()["xbrlModel"]
  assert {"name": "us-gaap:AssetsAbstract"} in model["headings"]
  assert all(c["name"] != "us-gaap:AssetsAbstract" for c in model["concepts"])


def test_concept_carries_datatype_period_type_and_balance() -> None:
  model = _document()["xbrlModel"]
  assets = next(c for c in model["concepts"] if c["name"] == "us-gaap:Assets")
  assert assets["dataType"] == "xbrlr:monetary"
  assert assets["periodType"] == "instant"
  assert {"property": "xbrla:balance", "value": "debit"} in assets["properties"]


def test_fact_carries_the_four_core_dimensions() -> None:
  """The near-identity mapping: factDimensions is a flat map (section 8.5)."""
  facts = _document()["xbrlModel"]["facts"]
  assets = facts[0]
  assert assets["factDimensions"] == {
    "xbrl:concept": "us-gaap:Assets",
    "xbrl:period": "2024-12-31",
    "xbrl:entity": "rpt:cik-0001234567",
    "xbrl:unit": "iso4217:USD",
  }
  assert assets["factValues"] == [{"value": 1000.0, "decimals": -3}]


def test_taxonomy_dimension_is_a_peer_of_the_core_dimensions() -> None:
  facts = _document()["xbrlModel"]["facts"]
  cash = next(f for f in facts if f["factDimensions"]["xbrl:concept"] == "us-gaap:Cash")
  assert cash["factDimensions"]["us-gaap:SegmentAxis"] == "us-gaap:NorthAmerica"


def test_duration_period_is_an_iso_interval() -> None:
  facts = _document()["xbrlModel"]["facts"]
  shares = next(
    f
    for f in facts
    if f["factDimensions"]["xbrl:concept"] == "us-gaap:SharesOutstanding"
  )
  assert shares["factDimensions"]["xbrl:period"] == "2024-01-01/2024-12-31"
  # decimals INF means infinitely precise, which Tavi expresses by omission.
  assert "decimals" not in shares["factValues"][0]


def test_calculation_relationship_carries_weight() -> None:
  """Section 14.3.1: weight is required on summation-item."""
  networks = _document()["xbrlModel"]["networks"]
  calc = next(n for n in networks if n["relationshipTypeName"] == "xbrl:summation-item")
  properties = calc["relationships"][0]["properties"]
  assert {"property": "xbrl:weight", "value": 1.0} in properties


def test_extended_link_role_becomes_one_group() -> None:
  """Both networks share an ELR, so they share a group (section 10.1)."""
  model = _document()["xbrlModel"]
  assert len(model["groups"]) == 1
  group = model["groups"][0]
  assert group["groupURI"] == "http://example.com/role/BalanceSheet"
  assert len(model["groupContents"]) == 2
  # A group carries only name and groupURI; its readable name is a label.
  assert set(group) == {"name", "groupURI"}


def test_group_definition_is_a_label_not_an_invented_property() -> None:
  """The ELR definition is a labelObject, as the specification's examples show.

  It was previously written as an `xbrl:groupDescription` property, which no
  property type in the model defines and which a validator would reject.
  """
  model = _document()["xbrlModel"]
  group_name = model["groups"][0]["name"]
  label = next(entry for entry in model["labels"] if entry["forObject"] == group_name)
  assert label == {
    "forObject": group_name,
    "labelType": "xbrl:label",
    "value": "Balance Sheet",
  }
  assert not any(
    p.get("property") == "xbrl:groupDescription"
    for obj in model["groups"]
    for p in obj.get("properties", [])
  )


def test_gap_report_records_the_unmapped_shares_datatype() -> None:
  """No built-in shares datatype exists, so it is recorded rather than guessed."""
  _, gaps = to_tavi_report(_model())
  assert gaps.item_types_without_builtin["sharesItemType"] == 1
  assert "sharesItemType" not in gaps.item_types_unmapped_here
  shares = next(
    c
    for c in _document()["xbrlModel"]["concepts"]
    if c["name"].endswith("SharesOutstanding")
  )
  assert "dataType" not in shares


def test_gap_report_records_dropped_period_semantics() -> None:
  """xbrl:period is a bare interval — the calendar placement has no home."""
  _, gaps = to_tavi_report(_model())
  dropped = gaps.dropped_period_semantics
  assert len(dropped) == 2
  annual = next(d for d in dropped if d["duration_type"] == "annual")
  assert annual["calendar_period_key"] == "2024"
  assert annual["period"] == "2024-01-01/2024-12-31"


def test_label_roles_map_to_the_core_model_label_types() -> None:
  """The standard role is xbrl:label, and the negated family exists in Tavi."""
  labels = _document()["xbrlModel"]["labels"]
  assets = next(entry for entry in labels if entry["forObject"] == "us-gaap:Assets")
  assert assets["labelType"] == "xbrl:label"
  cash = next(entry for entry in labels if entry["forObject"] == "us-gaap:Cash")
  assert cash["labelType"] == "xbrl:terseLabel"
  _, gaps = to_tavi_report(_model())
  assert gaps.unmapped_label_roles == {}


def test_gap_report_carries_the_spec_ambiguities() -> None:
  _, gaps = to_tavi_report(_model())
  ids = {a["id"] for a in gaps.to_dict()["against_the_model"]["spec_ambiguities"]}
  assert "xs-namespace-scheme" in ids
  assert "no-shares-datatype" in ids
  assert "duplicate-label-uris" in ids


def test_serialization_is_deterministic_and_valid_json() -> None:
  first = to_tavi(_model())
  second = to_tavi(_model())
  assert first == second
  assert json.loads(first)["documentInfo"]["documentType"] == DOCTYPE_COMPILED


def test_hypercube_becomes_a_cube_with_its_axis() -> None:
  """The `all` and `hypercube-dimension` arcs rebuild into a cubeObject."""
  model = _document()["xbrlModel"]
  cube = next(c for c in model["cubes"] if c["name"] == "rpt:cube-0")
  by_dimension = {d["dimension"]: d for d in cube["cubeDimensions"]}
  # Section 5.10.2: the concept dimension must be present, and is left open.
  assert by_dimension["xbrl:concept"] == {"dimension": "xbrl:concept"}
  # Core dimensions are optional so facts that omit one still fall inside.
  assert by_dimension["xbrl:period"]["optional"] is True
  assert by_dimension["us-gaap:SegmentAxis"]["domainNetwork"] == "rpt:domain-0"


def test_axis_domain_and_member_leave_the_concept_list() -> None:
  """In Tavi they are dimension, domain class and member objects, not concepts."""
  model = _document()["xbrlModel"]
  names = {c["name"] for c in model["concepts"]} | {
    h["name"] for h in model["headings"]
  }
  assert "us-gaap:SegmentAxis" not in names
  assert "us-gaap:SegmentDomain" not in names
  assert "us-gaap:NorthAmerica" not in names
  assert {"name": "us-gaap:SegmentAxis", "domainClass": "us-gaap:SegmentDomain"} in (
    model["dimensions"]
  )
  assert {"name": "us-gaap:SegmentDomain"} in model["domainClasses"]
  assert {
    "name": "us-gaap:NorthAmerica",
    "domainClasses": ["us-gaap:SegmentDomain"],
  } in model["members"]


def test_domain_network_is_rooted_at_the_domain_class() -> None:
  """Section 5.10.1: the domain's root must match the dimension's domainClass."""
  network = _document()["xbrlModel"]["domainNetworks"][0]
  assert network["root"] == "us-gaap:SegmentDomain"
  assert network["relationships"] == [
    {"source": "us-gaap:SegmentDomain", "target": "us-gaap:NorthAmerica"}
  ]


def test_every_fact_now_falls_inside_a_cube() -> None:
  """Section 8.5.2.5 — the open cube catches the undimensioned facts."""
  _, gaps = to_tavi_report(_model())
  assert gaps.dimensional_facts == 1
  assert gaps.facts_without_cube == 0


def test_explicit_out_path_is_honoured_exactly(tmp_path: Any) -> None:
  """`-o` with one format writes that path, as it did before --format existed."""
  from xbrlkit.cli import _write_outputs

  target = tmp_path / "custom-name.json"
  _write_outputs(_model(), target, "holon", named=True)
  assert target.exists()
  assert not (tmp_path / "custom-name.json.holon.jsonld").exists()


def test_both_formats_derive_a_shared_stem(tmp_path: Any) -> None:
  """Two documents from one parse cannot share a name, so the stem is derived."""
  from xbrlkit.cli import _write_outputs

  _write_outputs(_model(), tmp_path / "acme.holon.jsonld", "both", named=True)
  assert (tmp_path / "acme.holon.jsonld").exists()
  assert (tmp_path / "acme.tavi.json").exists()
  assert (tmp_path / "acme.tavi.gaps.json").exists()
