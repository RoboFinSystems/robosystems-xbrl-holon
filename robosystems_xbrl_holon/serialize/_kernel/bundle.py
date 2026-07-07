"""``StatementBundle`` envelope — XBRL-aligned shape (v1.0).

The bundle is the design unit shared by both encoder families and
(eventually) both producers (Report + LiveSnapshot). v1.0 of the
serialization ontology treats the bundle as **XBRL expressed in RDF,
plus our extensions**:

* The schema portion (``schema_concepts``) maps 1:1 to XBRL
  ``<xs:element>`` declarations with ``xbrli:`` attributes.
* The linkbases portion (``linkbases.presentation_links`` /
  ``calculation_links`` / ``definition_links``) maps to XBRL
  ``<link:presentationLink>`` / ``<link:calculationLink>`` /
  ``<link:definitionLink>`` containers, grouped by ``xlink:role``
  (the Extended Link Role).
* The instance portion is XBRL-native: dedupe'd ``contexts`` (one per
  distinct entity+period combo), dedupe'd ``units``, and ``facts``
  that reference contexts/units by id via ``xbrli:contextRef`` /
  ``xbrli:unitRef``. Facts carry the concept qname as their type
  (``@type: rs-gaap:Assets``) and the value as ``rdf:value`` — matching
  XBRL's "the element name IS the type tag" pattern.

The ``rs:`` extension surface (IB envelopes, reporting style,
verification, provenance) carries everything XBRL has no standard
for. The XBRL 2.1 emitter walks the same bundle, ignores the ``rs:``
extensions when projecting to XML, and produces a valid XBRL instance
+ linkbase set.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Metadata sub-shapes ────────────────────────────────────────────────────


class EntityMeta(BaseModel):
  """Reporting entity identity carried in the bundle header.

  This is the org-level entity, not the instance-level
  ``xbrli:entity`` (which lives on contexts). Customers usually have
  one entity per graph, so the header carries the canonical identity
  and contexts reference it via their ``identifier`` field.
  """

  id: str
  name: str
  legal_name: str | None = None
  ein: str | None = None
  country: str | None = None


class PeriodMeta(BaseModel):
  """One reporting period column in the bundle.

  Both instant and duration periods serialize through this shape;
  encoders interpret ``period_type`` to pick the XBRL context shape
  (``<xbrli:instant>`` vs ``<xbrli:startDate>/<xbrli:endDate>``).
  """

  start: date
  end: date
  label: str
  period_type: Literal["duration", "instant"] = "duration"


class ReportMeta(BaseModel):
  """Mode-specific metadata for ``mode='report'`` bundles.

  Carries the filing-lifecycle + restatement-chain + share-provenance
  fields that distinguish a stamped Report from an ephemeral live
  snapshot. A future importer uses these to drive cross-tenant
  identity reconstruction.
  """

  report_id: str
  generation_count: int
  filing_status: Literal["draft", "under_review", "filed", "archived"]
  filed_at: datetime | None = None
  supersedes_id: str | None = None
  source_graph_id: str | None = None
  source_report_id: str | None = None
  shared_at: datetime | None = None


class LiveMeta(BaseModel):
  """Mode-specific metadata for ``mode='live'`` bundles.

  ``non_authoritative`` is a constant ``True`` — the type itself
  carries the "cannot be imported as a Report" invariant; this field
  exists so consumers reading raw JSON-LD see the flag without needing
  to inspect the ``@type``.
  """

  snapshot_at: datetime
  non_authoritative: Literal[True] = True


class FrameworkPin(BaseModel):
  """One framework version pin carried in the bundle header.

  Replaces the flat ``dict[str, str]`` so the JSON-LD output renders
  as ``[{framework, version}]`` — friendlier to RDF consumers than a
  bare object map.
  """

  framework: str
  version: str


# ── Schema concepts (XBRL concept declarations) ────────────────────────────


class BundleElement(BaseModel):
  """An XBRL concept declaration carried in the bundle's schema slice.

  Maps 1:1 to an ``<xs:element>`` declaration in the XBRL emitter.
  Attributes use XBRL's vocabulary: ``xbrli:substitutionGroup``,
  ``xbrli:periodType``, ``xbrli:balance``, ``xsd:type`` (resolved to
  ``xbrli:monetaryItemType`` or ``xbrli:stringItemType`` based on
  ``is_monetary``).
  """

  id: str
  qname: str
  namespace: str | None = None
  name: str
  label: str | None = None
  balance_type: Literal["debit", "credit"] | None = None
  period_type: Literal["duration", "instant"]
  is_abstract: bool = False
  is_monetary: bool = True
  element_type: Literal["concept", "abstract", "axis", "member", "hypercube"] = (
    "concept"
  )
  substitution_group: str | None = None
  source: str


# ── Linkbases (XBRL linkbase content) ──────────────────────────────────────


class BundleArc(BaseModel):
  """A single linkbase arc — presentation / calculation / definition.

  ``arcrole`` carries the XBRL arcrole URI (e.g.
  ``http://www.xbrl.org/2003/arcrole/parent-child``). ``arc_type``
  is the discriminator the XBRL emitter uses to pick the right
  ``<link:presentationArc>`` / ``<link:calculationArc>`` /
  ``<link:definitionArc>`` element. ``weight`` is only meaningful on
  calculation arcs; null elsewhere.
  """

  arc_type: Literal["presentationArc", "calculationArc", "definitionArc"]
  arcrole: str
  from_qname: str
  to_qname: str
  order_value: float | None = None
  weight: float | None = None


class BundleLinkbaseLink(BaseModel):
  """A ``<link:X>`` link wrapping arcs scoped to one Extended Link Role.

  Mirrors XBRL XML where each link element wraps arcs for one ELR
  (``xlink:role``). The JSON-LD encoder emits this as a node with
  ``@type: link:presentationLink`` (or calc/def). Carries the
  Structure identity + name + block_type as ``rs:`` extensions so
  consumers can recover the Network identity.
  """

  link_type: Literal["presentationLink", "calculationLink", "definitionLink"]
  role_uri: str
  structure_id: str
  structure_name: str
  block_type: str | None = None
  arcs: list[BundleArc] = Field(default_factory=list)


class BundleLinkbases(BaseModel):
  """The bundle's linkbase content, grouped by link type.

  v1.0 carries presentation / calculation / definition; label and
  reference linkbases are not yet carried here (labels live on
  ``BundleElement.label`` for now). Each list is a sequence of
  link-per-ELR groupings; the XBRL emitter walks each in order.
  """

  presentation_links: list[BundleLinkbaseLink] = Field(default_factory=list)
  calculation_links: list[BundleLinkbaseLink] = Field(default_factory=list)
  definition_links: list[BundleLinkbaseLink] = Field(default_factory=list)


# ── Instance: contexts, units, facts ───────────────────────────────────────


class BundlePeriod(BaseModel):
  """An ``rs:Period`` node — one per distinct period a fact references.

  The bundle collapses the XBRL ``<context>`` (entity + period bundled): a Fact
  references its Period directly (mirroring the graph's ``FACT_HAS_PERIOD``
  edge). The XBRL encoder re-derives ``<xbrli:context>`` from these +
  the bundle entity at emit time (XBRL 2.1 requires shared contexts).

  ``period_start`` is null for instant periods (the period IS ``period_end``).
  """

  id: str
  period_start: date | None = None
  period_end: date
  period_type: Literal["duration", "instant"]


class BundleContext(BaseModel):
  """An ``<xbrli:context>`` — entity + period, one per distinct combo.

  **Not stored on the bundle** (the graph-native bundle collapses contexts onto facts). The
  XBRL 2.1 encoder *derives* these from the bundle's entity + ``period_nodes``
  at emit time, because XBRL requires shared ``<context>`` elements with
  ``contextRef``. The JSON-LD encoder never produces them.
  """

  id: str
  entity_identifier: str
  entity_scheme: str = "http://robosystems.ai/entity"
  period_start: date | None = None
  period_end: date
  period_type: Literal["duration", "instant"]


class BundleUnit(BaseModel):
  """An ``rs:Unit`` node — one per distinct measure.

  The bundle carries simple-measure units only (e.g., ``iso4217:USD``). Complex
  units (per-share with divide, ratios) are deferred until a customer
  needs them. The XBRL encoder emits these as ``<xbrli:unit>``.
  """

  id: str
  measure: str


class BundleFact(BaseModel):
  """A single ``rs:Fact`` node — aspects referenced directly (no context).

  Mirrors the graph's Fact + ``FACT_HAS_*`` edges: a Fact references its
  ``period`` (``BundlePeriod`` id), ``unit`` (``BundleUnit`` id), and
  ``entity`` (the bundle entity id) directly — there is no XBRL context
  node. The fidelity bar: every Fact emits with matching (concept,
  period → dates, unit, value, decimals).
  """

  id: str
  element_id: str
  element_qname: str
  value: float
  period_ref: str
  unit_ref: str
  entity_ref: str
  decimals: str = "INF"
  fact_set_id: str | None = None
  structure_id: str | None = None


# ── Bundle root ────────────────────────────────────────────────────────────


class StatementBundle(BaseModel):
  """The portable Report (or live snapshot) artifact.

  Mode-tagged: ``mode='report'`` bundles carry ``report_meta`` and are
  S3-stamped at publish; ``mode='live'`` bundles carry ``live_meta``,
  are response-body-only, and are rejected by the (future) importer
  by construction. The mode discriminator is a first-class JSON-LD
  type, not a flag, which enforces the report/live split structurally.

  ``ib_envelopes`` reuses :class:`InformationBlockEnvelope` from
  ``models/api/information_block.py`` directly. This is intentional
  coupling: the IB envelope is the canonical shape the read APIs
  already serve.
  """

  model_config = ConfigDict(arbitrary_types_allowed=True)

  # Header
  entity: EntityMeta
  periods: list[PeriodMeta]
  reporting_style: str
  framework_pins: list[FrameworkPin]

  # Schema — Element (concept) declarations
  schema_concepts: list[BundleElement]

  # Linkbases — reified Structure/Association content, grouped by type + ELR
  linkbases: BundleLinkbases

  # Instance — graph-native: facts reference period/unit/entity directly.
  # Period nodes replace XBRL contexts (the XBRL encoder re-derives contexts).
  period_nodes: list[BundlePeriod]
  units: list[BundleUnit]
  facts: list[BundleFact]

  # IB envelopes (RS extension — no XBRL equivalent)
  ib_envelopes: list[Any] = Field(
    default_factory=list,
    description=(
      "Per-Network InformationBlockEnvelope payloads. Typed as Any to "
      "avoid a circular import from operations → models.api; the encoder "
      "consumes each as a Pydantic-dumpable mapping."
    ),
  )

  # Mode discriminator + arm
  mode: Literal["report", "live"]
  report_meta: ReportMeta | None = None
  live_meta: LiveMeta | None = None


