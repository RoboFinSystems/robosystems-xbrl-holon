"""Project a neutral ``XbrlModel`` into the canonical ``holon.jsonld``.

This is the only genuinely new logic in the package: it builds a
:class:`StatementBundle` (the shape the vendored encoder consumes) from the
neutral model and hands it to :func:`serialize_to_holon_jsonld`. The RDF
encoding, SHACL shapes, and scene/boundary/projection partition all live in the
read-only kernel — this module only maps model → bundle.

The MVP projection deliberately sheds fidelity: only numeric facts and the four
primary financial statements survive; text facts, dimensions, and disclosure
networks are dropped (they remain in the neutral model for the LPG projection).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..model import Concept, Network, XbrlModel
from ._kernel.bundle import (
  BundleArc,
  BundleElement,
  BundleFact,
  BundleLinkbaseLink,
  BundleLinkbases,
  BundlePeriod,
  BundleUnit,
  EntityMeta,
  FrameworkPin,
  PeriodMeta,
  ReportMeta,
  StatementBundle,
)
from ._kernel.holon import serialize_to_holon_jsonld
from .classify import BLOCK_TYPES, classify_network

_PARENT_CHILD = "http://www.xbrl.org/2003/arcrole/parent-child"
_SUMMATION_ITEM = "http://www.xbrl.org/2003/arcrole/summation-item"


@dataclass
class _KeptNetwork:
  """A classified primary presentation network retained for projection."""

  network: Network
  fs_id: str
  structure_id: str
  concepts: set[str] = field(default_factory=set)


def _us_gaap_version(namespaces: list[str]) -> str:
  """Derive a us-gaap framework version from a taxonomy namespace, else unknown."""
  for ns in namespaces:
    if "us-gaap/" in ns:
      tail = ns.split("us-gaap/", 1)[1].rstrip("/#")
      if tail:
        return tail
  return "unknown"


def _keep_primary_networks(model: XbrlModel) -> dict[str, _KeptNetwork]:
  """Retain the first presentation network per classified primary block type."""
  kept: dict[str, _KeptNetwork] = {}
  for net in model.networks:
    if net.kind != "presentation":
      continue
    bt = classify_network(net.role_uri, net.definition)
    if bt is None or bt in kept:
      continue
    concepts: set[str] = set()
    for arc in net.arcs:
      concepts.add(arc.from_qname)
      concepts.add(arc.to_qname)
    kept[bt] = _KeptNetwork(
      network=net,
      fs_id=f"fs_{bt}",
      structure_id=net.role_uri or f"fs_{bt}",
      concepts=concepts,
    )
  return kept


def _fact_set_for(concept_qname: str, kept: dict[str, _KeptNetwork]) -> str | None:
  """First classified block (in canonical order) whose network cites the concept."""
  for bt in BLOCK_TYPES:
    kn = kept.get(bt)
    if kn is not None and concept_qname in kn.concepts:
      return kn.fs_id
  return None


def _match_calc_block(calc: Network, kept: dict[str, _KeptNetwork]) -> str | None:
  """Match a calculation network to a kept primary by role URI, then concepts."""
  for bt in BLOCK_TYPES:
    kn = kept.get(bt)
    if kn is not None and kn.network.role_uri and calc.role_uri == kn.network.role_uri:
      return bt
  calc_concepts: set[str] = set()
  for arc in calc.arcs:
    calc_concepts.add(arc.from_qname)
    calc_concepts.add(arc.to_qname)
  for bt in BLOCK_TYPES:
    kn = kept.get(bt)
    if kn is not None and calc_concepts & kn.concepts:
      return bt
  return None


def build_bundle(model: XbrlModel, *, report_id: str | None = None) -> StatementBundle:
  """Build the ``StatementBundle`` this filing projects to (before encoding).

  Exposed alongside :func:`to_holon` so callers (and the SHACL drift-guard
  test) can run ``build_graph`` / ``shacl_report`` over the exact bundle the
  holon is serialized from.
  """
  report_id = report_id or model.filing.accession
  entity = EntityMeta(
    id=model.entity.cik,
    name=model.entity.name or model.entity.cik,
    legal_name=model.entity.legal_name,
    ein=model.entity.ein,
    country=None,
  )

  kept = _keep_primary_networks(model)

  period_by_id = {p.id: p for p in model.periods}
  unit_by_id = {u.id: u for u in model.units}

  # Pass 1 — select emittable facts: numeric, resolvable period + unit.
  emittable = []
  for fact in model.facts:
    if fact.value_kind != "numeric" or fact.numeric_value is None:
      continue
    # Dimensional facts are note-level breakdowns (by segment / security type /
    # member). The undimensioned MVP holon drops dimensions, so emitting them
    # would collapse every breakdown onto the consolidated face-of-statement
    # cell for the same (concept, period) — the renderer then shows a breakdown
    # value or nulls the cell. Keep only the undimensioned (consolidated) fact.
    if fact.dims:
      continue
    if fact.unit_id is None:
      continue
    period = period_by_id.get(fact.period_id)
    unit = unit_by_id.get(fact.unit_id)
    if period is None or unit is None:
      continue
    period_end = period.end or period.start
    if period_end is None:
      continue
    emittable.append((fact, period, unit, period_end))

  # Deterministic short refs from first-seen order among emitted facts.
  period_ref: dict[str, str] = {}
  unit_ref: dict[str, str] = {}
  for fact, period, unit, _end in emittable:
    if period.id not in period_ref:
      period_ref[period.id] = f"p_{len(period_ref)}"
    if unit.id not in unit_ref:
      unit_ref[unit.id] = f"u_{len(unit_ref)}"

  period_nodes: list[BundlePeriod] = []
  period_columns: list[PeriodMeta] = []
  seen_periods: set[str] = set()
  for _fact, period, _unit, period_end in emittable:
    if period.id in seen_periods:
      continue
    seen_periods.add(period.id)
    ref = period_ref[period.id]
    ptype: str = "instant" if period.period_type == "instant" else "duration"
    start_node: date | None = (
      None if ptype == "instant" else (period.start or period_end)
    )
    period_nodes.append(
      BundlePeriod(
        id=ref,
        period_start=start_node,
        period_end=period_end,
        period_type=ptype,
      )
    )
    period_columns.append(
      PeriodMeta(
        start=period.start or period_end,
        end=period_end,
        label=period.id or period_end.isoformat(),
        period_type=ptype,
      )
    )

  units: list[BundleUnit] = []
  seen_units: set[str] = set()
  for _fact, _period, unit, _end in emittable:
    if unit.id in seen_units:
      continue
    seen_units.add(unit.id)
    units.append(BundleUnit(id=unit_ref[unit.id], measure=unit.measure))

  facts: list[BundleFact] = []
  for fact, period, unit, _end in emittable:
    facts.append(
      BundleFact(
        id=fact.id,
        element_id=fact.concept_qname,
        element_qname=fact.concept_qname,
        value=fact.numeric_value,
        period_ref=period_ref[period.id],
        unit_ref=unit_ref[unit.id],
        entity_ref=model.entity.cik,
        decimals=fact.decimals or "INF",
        fact_set_id=_fact_set_for(fact.concept_qname, kept),
      )
    )

  # schema_concepts — every concept an emitted fact or kept arc references.
  concept_qnames: set[str] = {f.element_qname for f in facts}
  for kn in kept.values():
    concept_qnames.update(kn.concepts)
  schema_concepts = [
    _bundle_element(qname, model.concepts.get(qname))
    for qname in sorted(concept_qnames)
  ]

  presentation_links: list[BundleLinkbaseLink] = []
  for bt in BLOCK_TYPES:
    kn = kept.get(bt)
    if kn is None:
      continue
    presentation_links.append(
      BundleLinkbaseLink(
        link_type="presentationLink",
        role_uri=kn.network.role_uri,
        structure_id=kn.structure_id,
        structure_name=kn.network.definition or bt,
        block_type=bt,
        arcs=[
          BundleArc(
            arc_type="presentationArc",
            arcrole=_PARENT_CHILD,
            from_qname=arc.from_qname,
            to_qname=arc.to_qname,
            order_value=arc.order,
          )
          for arc in kn.network.arcs
        ],
      )
    )

  calculation_links: list[BundleLinkbaseLink] = []
  for calc in model.networks:
    if calc.kind != "calculation" or not calc.arcs:
      continue
    bt = _match_calc_block(calc, kept)
    if bt is None:
      continue
    kn = kept[bt]
    calculation_links.append(
      BundleLinkbaseLink(
        link_type="calculationLink",
        role_uri=calc.role_uri,
        structure_id=calc.role_uri or kn.structure_id,
        structure_name=calc.definition or bt,
        block_type=bt,
        arcs=[
          BundleArc(
            arc_type="calculationArc",
            arcrole=_SUMMATION_ITEM,
            from_qname=arc.from_qname,
            to_qname=arc.to_qname,
            order_value=arc.order,
            weight=arc.weight,
          )
          for arc in calc.arcs
        ],
      )
    )

  ib_envelopes = [
    {
      "id": f"ib_{bt}",
      "block_type": bt,
      "name": kept[bt].network.definition or bt.title(),
      "fact_set": {"id": kept[bt].fs_id},
    }
    for bt in BLOCK_TYPES
    if bt in kept
  ]

  return StatementBundle(
    entity=entity,
    periods=period_columns,
    reporting_style="sec-as-filed",
    framework_pins=[
      FrameworkPin(
        framework="us-gaap",
        version=_us_gaap_version(model.filing.taxonomy_namespaces),
      )
    ],
    schema_concepts=schema_concepts,
    linkbases=BundleLinkbases(
      presentation_links=presentation_links,
      calculation_links=calculation_links,
    ),
    period_nodes=period_nodes,
    units=units,
    facts=facts,
    ib_envelopes=ib_envelopes,
    mode="report",
    report_meta=ReportMeta(
      report_id=report_id,
      generation_count=0,
      filing_status="filed",
    ),
  )


def _bundle_element(qname: str, concept: Concept | None) -> BundleElement:
  """Map a model :class:`Concept` (or a synthesized minimal one) to an element."""
  if concept is None:
    concept = Concept(qname=qname, namespace="", name=qname.split(":", 1)[-1])
  period_type: str = "instant" if concept.period_type == "instant" else "duration"
  source = qname.split(":", 1)[0] if ":" in qname else "unknown"
  is_monetary = (concept.item_type or "").startswith("monetary") or concept.is_numeric
  return BundleElement(
    id=qname,
    qname=qname,
    namespace=concept.namespace or None,
    name=concept.name,
    label=concept.pref_label,
    balance_type=concept.balance,
    period_type=period_type,
    is_abstract=concept.is_abstract,
    is_monetary=is_monetary,
    element_type="concept",
    substitution_group=concept.substitution_group,
    source=source,
  )


def to_holon(model: XbrlModel, *, report_id: str | None = None) -> str:
  """Project ``model`` into the canonical dataset-form ``holon.jsonld`` string."""
  bundle = build_bundle(model, report_id=report_id)
  return serialize_to_holon_jsonld(bundle)
