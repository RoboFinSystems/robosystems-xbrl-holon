"""Project a neutral ``XbrlModel`` into a Project Tavi compiled model.

Tavi (XBRL International, PWD 2026-09-01 — previously "OIM Taxonomy") replaces
the XML taxonomy + instance pair with one JSON object model: taxonomy objects
and report objects live in a single document, and every object is a named,
QName-addressed, referenceable thing.

This is the third projection off the one parse (see :mod:`..model`): the holon
emits RDF, ``graph`` emits the LPG/parquet shape, and this emits Tavi. Nothing
upstream changes — the ``XbrlModel`` already carries what Tavi needs, because
Tavi's fact model (``factDimensions``: concept/period/unit/entity plus taxonomy
dimensions as peers) is the same shape the parse has always produced.

We emit a **compiled model** (``documentType`` ``…/compiled``): fully resolved,
no imports, self-contained — one file per filing, so a consumer needs nothing
else to read it.

Two deliberate non-goals, both recorded rather than hidden:

- **Cubes.** Tavi's ``cubeObject`` is first-class with ``cubeDimensions``; ours
  are definition-network arcroles. The raw material is present (``Arc.arcrole``
  keeps ``all`` / ``hypercube-dimension`` / ``dimension-domain`` /
  ``domain-member`` / ``dimension-default``), so this is derivable — it is just
  a genuine transformation and lands in a second pass. Until then dimensional
  facts are emitted with their ``factDimensions`` intact but no cube declares
  their space, which a validator will flag as ``oimte:noFactSpaceForFact``.
- **Whatever Tavi has nowhere to put.** :func:`to_tavi_report` returns a
  :class:`GapReport` alongside the document. It is not a debug aid: the set of
  things a real filing carries that the model cannot express is the substantive
  output of this exercise.

Written against the prose of PWD-2026-09-01. The draft references a
``tavi-schema.json`` that is not published, so nothing here is validated
against an authoritative schema; :data:`SPEC_AMBIGUITIES` records where the
draft is unclear or self-contradictory and what this emitter chose.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from ..model import Arc, Concept, Network, Period, XbrlModel

TAVI_VERSION = "PWD-2026-09-01"
TAVI_BASE = "https://xbrl.org/PWD/2026-09-01"
DOCTYPE_COMPILED = f"{TAVI_BASE}/compiled"

# Reserved prefixes, per section 2.4. `xs` is bound to the http form used by
# every namespaces-map example in the draft, not the https form in the section
# 2.4 table — see SPEC_AMBIGUITIES.
RESERVED_NAMESPACES: dict[str, str] = {
  "xbrl": TAVI_BASE,
  "xbrlr": f"{TAVI_BASE}/report",
  "xbrla": f"{TAVI_BASE}/accounting",
  "xs": "http://www.w3.org/2001/XMLSchema",
  "iso4217": "http://www.xbrl.org/2003/iso4217",
  "utr": f"{TAVI_BASE}/utr",
}

# Namespace for the objects this emitter mints (facts, groups, the model
# object). Report-scoped so two filings never collide.
REPORT_NS_BASE = "https://robosystems.ai/tavi/report"
REPORT_PREFIX = "rpt"

# XBRL 2.1 item type -> Tavi datatype QName. Every target here was verified
# against the built-in model in Appendix E; an unverified item type is recorded
# as a gap rather than guessed, because a wrong datatype is a silent
# correctness bug that a validator would not catch.
ITEM_TYPE_DATATYPES: dict[str, str] = {
  "monetaryItemType": "xbrlr:monetary",
  "pureItemType": "xbrlr:pure",
  "percentItemType": "xbrlr:percent",
  "perShareItemType": "xbrlr:perShare",
  "textBlockItemType": "xbrlr:textBlock",
  "areaItemType": "xbrlr:area",
  "energyItemType": "xbrlr:energy",
  "flowItemType": "xbrlr:flow",
  "forceItemType": "xbrlr:force",
  "frequencyItemType": "xbrlr:frequency",
  "lengthItemType": "xbrlr:length",
  "massItemType": "xbrlr:mass",
  "memoryItemType": "xbrlr:memory",
  "planeAngleItemType": "xbrlr:planeAngle",
  "powerItemType": "xbrlr:power",
  "pressureItemType": "xbrlr:pressure",
  "speedItemType": "xbrlr:speed",
  "temperatureItemType": "xbrlr:temperature",
  "voltageItemType": "xbrlr:voltage",
  "volumeItemType": "xbrlr:volume",
  "durationItemType": "xbrlr:duration",
  "dateTimeItemType": "xbrlr:dateTime",
  "stringItemType": "xs:string",
  "normalizedStringItemType": "xs:normalizedString",
  "booleanItemType": "xs:boolean",
  "dateItemType": "xs:date",
  "gYearItemType": "xs:gYear",
  "anyURIItemType": "xs:anyURI",
  "integerItemType": "xs:integer",
  "decimalItemType": "xs:decimal",
  "QNameItemType": "xs:QName",
}

# Item types with no built-in Tavi datatype at all — a gap in the model, not in
# this emitter. Kept separate so the gap report does not blame the spec for our
# own unmapped types.
ITEM_TYPES_WITHOUT_BUILTIN: frozenset[str] = frozenset({"sharesItemType"})

# Label role URI -> Tavi label type QName. Section 14.6 keeps the XBRL 2.1 and
# Link Role Registry roles and addresses them by QName instead of URI; this map
# is transcribed from the core model's own labelTypes, using the *prose* URIs
# for the two entries where the core model contradicts itself (see
# SPEC_AMBIGUITIES: duplicate-label-uris).
LABEL_ROLE_TYPES: dict[str, str] = {
  "http://www.xbrl.org/2003/role/label": "xbrl:label",
  "http://www.xbrl.org/2003/role/terseLabel": "xbrl:terseLabel",
  "http://www.xbrl.org/2003/role/verboseLabel": "xbrl:verboseLabel",
  "http://www.xbrl.org/2003/role/totalLabel": "xbrl:totalLabel",
  "http://www.xbrl.org/2003/role/periodStartLabel": "xbrl:periodStartLabel",
  "http://www.xbrl.org/2003/role/periodEndLabel": "xbrl:periodEndLabel",
  "http://www.xbrl.org/2003/role/documentation": "xbrl:documentation",
  "http://www.xbrl.org/2003/role/negativeLabel": "xbrl:negativeLabel",
  "http://www.xbrl.org/2003/role/negativeTerseLabel": "xbrl:negativeTerseLabel",
  "http://www.xbrl.org/2003/role/negativeVerboseLabel": "xbrl:negativeVerboseLabel",
  "http://www.xbrl.org/2003/role/positiveLabel": "xbrl:positiveLabel",
  "http://www.xbrl.org/2003/role/positiveTerseLabel": "xbrl:positiveTerseLabel",
  "http://www.xbrl.org/2003/role/positiveVerboseLabel": "xbrl:positiveVerboseLabel",
  "http://www.xbrl.org/2003/role/zeroLabel": "xbrl:zeroLabel",
  "http://www.xbrl.org/2003/role/zeroTerseLabel": "xbrl:zeroTerseLabel",
  "http://www.xbrl.org/2003/role/zeroVerboseLabel": "xbrl:zeroVerboseLabel",
  "http://www.xbrl.org/2006/role/restatedLabel": "xbrl:restatedLabel",
  "http://www.xbrl.org/2009/role/negatedLabel": "xbrl:negatedLabel",
  "http://www.xbrl.org/2009/role/negatedTerseLabel": "xbrl:negatedTerseLabel",
  "http://www.xbrl.org/2009/role/negatedTotalLabel": "xbrl:negatedTotalLabel",
  "http://www.xbrl.org/2009/role/negatedNetLabel": "xbrl:negatedNetLabel",
  "http://www.xbrl.org/2009/role/negatedPeriodEndLabel": "xbrl:negatedPeriodEndLabel",
  "http://www.xbrl.org/2009/role/negatedPeriodStartLabel": "xbrl:negatedPeriodStartLabel",
  "http://www.xbrl.org/2009/role/netLabel": "xbrl:netLabel",
  "http://www.xbrl.org/2009/role/deprecatedLabel": "xbrl:deprecatedLabel",
  "http://www.xbrl.org/2009/role/deprecatedDateLabel": "xbrl:deprecatedDateLabel",
  "http://www.xbrl.org/2009/role/negativePeriodEndLabel": "xbrl:negativePeriodEndLabel",
  "http://www.xbrl.org/2009/role/negativePeriodEndTotalLabel": (
    "xbrl:negativePeriodEndTotalLabel"
  ),
  "http://www.xbrl.org/2009/role/negativePeriodStartLabel": (
    "xbrl:negativePeriodStartLabel"
  ),
  "http://www.xbrl.org/2009/role/negativePeriodStartTotalLabel": (
    "xbrl:negativePeriodStartTotalLabel"
  ),
  "http://www.xbrl.org/2009/role/positivePeriodEndLabel": "xbrl:positivePeriodEndLabel",
  "http://www.xbrl.org/2009/role/positivePeriodEndTotalLabel": (
    "xbrl:positivePeriodEndTotalLabel"
  ),
  "http://www.xbrl.org/2009/role/positivePeriodStartLabel": (
    "xbrl:positivePeriodStartLabel"
  ),
  "http://www.xbrl.org/2009/role/positivePeriodStartTotalLabel": (
    "xbrl:positivePeriodStartTotalLabel"
  ),
  "http://xbrl.us/us-gaap/role/label/negated": "xbrl:negated",
  "http://xbrl.us/us-gaap/role/label/negatedPeriodEnd": "xbrl:negatedPeriodEnd",
  "http://xbrl.us/us-gaap/role/label/negatedPeriodStart": "xbrl:negatedPeriodStart",
  "http://xbrl.us/us-gaap/role/label/negatedTotal": "xbrl:negatedTotal",
}
DEFAULT_LABEL_TYPE = "xbrl:label"

PRESENTATION_RELATIONSHIP = "xbrl:parent-child"
CALCULATION_RELATIONSHIP = "xbrl:summation-item"

# Points where PWD-2026-09-01 is unclear or contradicts itself, and the reading
# this emitter took. Carried in the output so a reviewer sees the assumptions
# rather than having to infer them from the bytes.
SPEC_AMBIGUITIES: tuple[dict[str, str], ...] = (
  {
    "id": "xs-namespace-scheme",
    "where": "section 2.4 reserved prefixes vs. every namespaces-map example",
    "issue": (
      "The reserved-prefix table binds xs to https://www.w3.org/2001/XMLSchema; "
      "all six namespaces-map examples and the built-in model bind it to the "
      "http form. Section 4.2.2 requires a reserved alias to carry exactly its "
      "prescribed URI (oimce:invalidURIForReservedAlias), so the examples are "
      "invalid against the table."
    ),
    "choice": "http form — it is XML Schema's real namespace and the examples agree.",
  },
  {
    "id": "no-shares-datatype",
    "where": "built-in datatypes (Appendix E)",
    "issue": (
      "There is no shares datatype. xbrlr:perShare exists for per-share values "
      "but nothing types a share count, which every equity filing reports. A "
      "taxonomy can define one via a datatype object with a unitType, so this "
      "is a standardisation gap rather than an impossibility — but it means "
      "each filer invents their own."
    ),
    "choice": "sharesItemType is left unmapped and recorded as a datatype gap.",
  },
  {
    "id": "xbrlr-decimal-undefined",
    "where": "section 8.2.1 unit object examples",
    "issue": (
      "The unit examples use dataType xbrlr:decimal, which is not defined in "
      "the built-in model and is not an XML Schema built-in, so those examples "
      "raise oimte:invalidQNameReference against the unit object's own "
      "constraint."
    ),
    "choice": "xs:decimal is used for unit datatypes instead.",
  },
  {
    "id": "duplicate-label-uris",
    "where": "core model label types (Appendix E)",
    "issue": (
      "Two URIs are each bound to two label types, which the model's own "
      "oimte:duplicateLabelURI forbids: "
      ".../2009/role/negativePeriodEndTotalLabel carries both "
      "xbrl:negativePeriodEndLabel and xbrl:negativePeriodEndTotalLabel, and "
      ".../2009/role/positivePeriodStartTotalLabel carries both "
      "xbrl:positivePeriodEndTotalLabel and xbrl:positivePeriodStartTotalLabel. "
      "The consequence is that .../negativePeriodEndLabel and "
      ".../positivePeriodEndTotalLabel have no binding at all, so a filing "
      "using either Link Role Registry role has nothing to map to. The prose "
      "table in section 14.6 gives each type its matching URI, so the core "
      "model is the copy that is wrong."
    ),
    "choice": "the prose URIs are used, which restores a 1:1 role/type mapping.",
  },
  {
    "id": "instant-date-only",
    "where": "section 8.5.2.2",
    "issue": (
      "A date-only instant resolves to T00:00:00 of the following day, so a "
      "bare 2024-12-31 means end-of-day 2024-12-31 — the inclusive reading a "
      "filing intends. Emitting dateTime instead would require rolling the "
      "date forward by one day."
    ),
    "choice": "date-only literals throughout, so no roll-forward is applied.",
  },
)


@dataclass
class GapReport:
  """What the filing carries that the Tavi model has nowhere to put.

  The substantive output of the exercise: each entry is a concrete thing a real
  SEC filing expresses and PWD-2026-09-01 cannot, discovered by emitting rather
  than by reading.
  """

  # Item types Tavi has no built-in datatype for. A finding against the model.
  item_types_without_builtin: dict[str, int] = field(default_factory=dict)
  # Item types this emitter has not mapped yet. A finding against us — most are
  # taxonomy-defined (dei:*) and belong in a taxonomy, not the built-in model.
  item_types_unmapped_here: dict[str, int] = field(default_factory=dict)
  unmapped_label_roles: dict[str, int] = field(default_factory=dict)
  dropped_period_semantics: list[dict[str, object]] = field(default_factory=list)
  facts_without_cube: int = 0
  dimensional_facts: int = 0
  notes: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, object]:
    return {
      "spec_version": TAVI_VERSION,
      "against_the_model": {
        "item_types_without_builtin": dict(
          sorted(self.item_types_without_builtin.items())
        ),
        "dropped_period_semantics": self.dropped_period_semantics,
        "spec_ambiguities": [dict(a) for a in SPEC_AMBIGUITIES],
      },
      "against_this_emitter": {
        "item_types_unmapped_here": dict(sorted(self.item_types_unmapped_here.items())),
        "unmapped_label_roles": dict(sorted(self.unmapped_label_roles.items())),
        "facts_without_cube": self.facts_without_cube,
        "dimensional_facts": self.dimensional_facts,
      },
      "notes": self.notes,
    }


def to_tavi(model: XbrlModel, *, report_id: str | None = None) -> str:
  """Project ``model`` into a Tavi compiled-model JSON string."""
  document, _ = to_tavi_report(model, report_id=report_id)
  return json.dumps(document, indent=2, sort_keys=False, default=str)


def to_tavi_report(
  model: XbrlModel, *, report_id: str | None = None
) -> tuple[dict[str, object], GapReport]:
  """Project ``model``, returning the document and what it could not express."""
  report_id = report_id or model.filing.accession
  gaps = GapReport()
  namespaces = _namespaces(model, report_id)

  concepts, headings = _concepts_and_headings(model, gaps)
  networks, groups, group_contents = _networks_and_groups(model, report_id)

  xbrl_model: dict[str, object] = {
    "name": f"{REPORT_PREFIX}:Report",
    "modelType": "xbrl:report",
    "properties": _model_properties(model),
    "entities": _entities(model),
    "units": _units(model),
    "concepts": concepts,
    "headings": headings,
    "labels": _labels(model, gaps),
    "networks": networks,
    "groups": groups,
    "groupContents": group_contents,
    "facts": _facts(model, gaps),
  }

  document: dict[str, object] = {
    "documentInfo": {
      "documentType": DOCTYPE_COMPILED,
      "namespaces": namespaces,
      "description": (
        f"{model.filing.form or 'filing'} {model.filing.accession} "
        f"(CIK {model.filing.cik}) projected from XBRL by robosystems-xbrl-holon"
      ),
    },
    "xbrlModel": {k: v for k, v in xbrl_model.items() if v},
  }
  return document, gaps


def _report_namespace(report_id: str) -> str:
  return f"{REPORT_NS_BASE}/{report_id}"


def _namespaces(model: XbrlModel, report_id: str) -> dict[str, str]:
  """Prefix -> URI map: reserved prefixes, the filing's taxonomies, ours.

  Section 2.4: the URI is the authoritative identity and the prefix is a
  serialisation convenience, so a generated prefix is sufficient wherever the
  source namespace does not carry one.
  """
  namespaces = dict(RESERVED_NAMESPACES)
  namespaces[REPORT_PREFIX] = _report_namespace(report_id)

  by_uri = {uri: prefix for prefix, uri in namespaces.items()}
  for concept in model.concepts.values():
    uri = concept.namespace
    if not uri or uri in by_uri:
      continue
    prefix = concept.qname.split(":", 1)[0] if ":" in concept.qname else None
    if not prefix or prefix in namespaces:
      prefix = f"ns{len(namespaces)}"
    namespaces[prefix] = uri
    by_uri[uri] = prefix
  return namespaces


def _model_properties(model: XbrlModel) -> list[dict[str, object]]:
  """Model-level properties: the report's own dates (sections 14.3.5/14.3.6)."""
  properties: list[dict[str, object]] = []
  if model.filing.filing_date:
    properties.append(
      {
        "property": "xbrl:reportFilingDate",
        "value": model.filing.filing_date.isoformat(),
      }
    )
  return properties


def _entities(model: XbrlModel) -> list[dict[str, object]]:
  """The reporting entity (section 8.1). Identity is the SQName."""
  return [{"name": _entity_qname(model.entity.cik)}]


def _entity_qname(cik: str) -> str:
  return f"{REPORT_PREFIX}:cik-{cik}"


def _units(model: XbrlModel) -> list[dict[str, object]]:
  """Unit objects (section 8.2). ISO-4217 units resolve to the reserved prefix."""
  units: list[dict[str, object]] = []
  seen: set[str] = set()
  for unit in model.units:
    qname = _unit_qname(unit.measure)
    if qname in seen:
      continue
    seen.add(qname)
    units.append({"name": qname, "dataType": "xs:decimal"})
  return units


def _unit_qname(measure: str) -> str:
  """Normalise a measure token to a Tavi unit QName."""
  if ":" in measure:
    return measure
  return f"utr:{measure}"


def _concepts_and_headings(
  model: XbrlModel, gaps: GapReport
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
  """Split concepts into concept objects and heading objects.

  Section 5.3: a heading is an object with no reportable value that is still a
  component of the concept dimension — exactly an abstract XBRL element.
  """
  concepts: list[dict[str, object]] = []
  headings: list[dict[str, object]] = []

  for qname in sorted(model.concepts):
    concept = model.concepts[qname]
    if concept.is_abstract:
      headings.append({"name": qname})
      continue

    obj: dict[str, object] = {"name": qname}
    datatype = _datatype_for(concept, gaps)
    if datatype:
      obj["dataType"] = datatype
    if concept.period_type:
      obj["periodType"] = concept.period_type
    properties = _concept_properties(concept)
    if properties:
      obj["properties"] = properties
    concepts.append(obj)

  return concepts, headings


def _datatype_for(concept: Concept, gaps: GapReport) -> str | None:
  """Map an XBRL item type to a Tavi datatype, recording anything unmapped."""
  item_type = concept.item_type
  if not item_type:
    return None
  local = item_type.split(":", 1)[-1]
  datatype = ITEM_TYPE_DATATYPES.get(local)
  if datatype is None:
    bucket = (
      gaps.item_types_without_builtin
      if local in ITEM_TYPES_WITHOUT_BUILTIN
      else gaps.item_types_unmapped_here
    )
    bucket[local] = bucket.get(local, 0) + 1
  return datatype


def _concept_properties(concept: Concept) -> list[dict[str, object]]:
  """Concept-level properties. Balance is the accounting module's (section 15.3.1)."""
  properties: list[dict[str, object]] = []
  if concept.balance:
    properties.append({"property": "xbrla:balance", "value": concept.balance})
  return properties


def _labels(model: XbrlModel, gaps: GapReport) -> list[dict[str, object]]:
  """Label objects (section 5.14): free-standing, pointing at ``forObject``."""
  labels: list[dict[str, object]] = []
  for qname in sorted(model.concepts):
    for label in model.concepts[qname].labels:
      label_type = LABEL_ROLE_TYPES.get(label.role or "", None)
      if label_type is None:
        role = label.role or "(none)"
        gaps.unmapped_label_roles[role] = gaps.unmapped_label_roles.get(role, 0) + 1
        label_type = DEFAULT_LABEL_TYPE
      entry: dict[str, object] = {
        "forObject": qname,
        "labelType": label_type,
        "value": label.value,
      }
      if label.language:
        entry["language"] = label.language
      labels.append(entry)
  return labels


def _networks_and_groups(
  model: XbrlModel, report_id: str
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
  """Networks (section 10.3) plus the groups (section 10.1) that carry them.

  An extended link role becomes a group: Tavi's group is the report section an
  ELR has always stood for. Definition networks are held back for the cube
  pass — their arcroles are the raw material for ``cubeObject``.
  """
  networks: list[dict[str, object]] = []
  groups: list[dict[str, object]] = []
  group_contents: list[dict[str, object]] = []
  group_names: dict[str, str] = {}

  for index, network in enumerate(model.networks):
    if network.kind == "definition":
      continue
    relationship_type = (
      PRESENTATION_RELATIONSHIP
      if network.kind == "presentation"
      else CALCULATION_RELATIONSHIP
    )
    name = f"{REPORT_PREFIX}:network-{network.kind}-{index}"
    roots = sorted({arc.from_qname for arc in network.arcs if arc.is_root})
    entry: dict[str, object] = {
      "name": name,
      "relationshipTypeName": relationship_type,
      "relationships": [_relationship(arc, network) for arc in network.arcs],
    }
    if roots:
      entry["roots"] = roots
    networks.append(entry)

    group_name = group_names.get(network.role_uri)
    if group_name is None:
      group_name = f"{REPORT_PREFIX}:group-{len(group_names)}"
      group_names[network.role_uri] = group_name
      group: dict[str, object] = {"name": group_name, "groupURI": network.role_uri}
      if network.definition:
        group["properties"] = [
          {"property": "xbrl:groupDescription", "value": network.definition}
        ]
      groups.append(group)
    group_contents.append({"groupName": group_name, "forObject": name})

  return networks, groups, group_contents


def _relationship(arc: Arc, network: Network) -> dict[str, object]:
  """One relationship object (section 10.4), with its link properties."""
  entry: dict[str, object] = {"source": arc.from_qname, "target": arc.to_qname}
  if arc.order is not None:
    entry["order"] = arc.order
  properties: list[dict[str, object]] = []
  if network.kind == "calculation" and arc.weight is not None:
    # Section 14.3.1: weight is required on summation-item.
    properties.append({"property": "xbrl:weight", "value": arc.weight})
    properties.append({"property": "xbrl:reconciliation", "value": True})
  if arc.preferred_label:
    label_type = LABEL_ROLE_TYPES.get(arc.preferred_label)
    if label_type:
      properties.append({"property": "xbrl:preferredLabel", "value": label_type})
  if properties:
    entry["properties"] = properties
  return entry


def _facts(model: XbrlModel, gaps: GapReport) -> list[dict[str, object]]:
  """Fact objects (section 8.3) — the near-identity mapping.

  ``factDimensions`` is a flat name/value map over concept/period/unit/entity
  plus taxonomy-defined dimensions as peers, which is the shape the parse
  already produces.
  """
  periods = {period.id: period for period in model.periods}
  units = {unit.id: unit for unit in model.units}
  entity_qname = _entity_qname(model.entity.cik)
  facts: list[dict[str, object]] = []

  for index, fact in enumerate(model.facts):
    period = periods.get(fact.period_id)
    dimensions: dict[str, object] = {"xbrl:concept": fact.concept_qname}
    if period is not None:
      dimensions["xbrl:period"] = _period_value(period)
      _record_period_semantics(period, gaps)
    dimensions["xbrl:entity"] = entity_qname
    if fact.unit_id and fact.unit_id in units:
      dimensions["xbrl:unit"] = _unit_qname(units[fact.unit_id].measure)

    for qualifier in fact.dims:
      value = qualifier.member_qname or qualifier.typed_value
      if value is not None:
        dimensions[qualifier.axis_qname] = value

    if fact.dims:
      gaps.dimensional_facts += 1
      gaps.facts_without_cube += 1

    value = fact.value_str if fact.value_kind == "text" else fact.numeric_value
    fact_value: dict[str, object] = {"value": value}
    if fact.decimals is not None:
      decimals = _decimals(fact.decimals)
      if decimals is not None:
        fact_value["decimals"] = decimals

    facts.append(
      {
        "name": f"{REPORT_PREFIX}:f-{index}",
        "factDimensions": dimensions,
        "factValues": [fact_value],
      }
    )
  return facts


def _period_value(period: Period) -> str:
  """A period as an ISO 8601 interval (section 8.5.2.2).

  Date-only literals throughout: a bare end date resolves to T00:00:00 of the
  following day, which is the inclusive reading the filing intends, so the
  parse's already-rolled-back dates are emitted unchanged.
  """
  if period.period_type == "instant":
    return _iso(period.end or period.start)
  if period.period_type == "forever":
    return "0001-01-01/9999-12-31"
  return f"{_iso(period.start)}/{_iso(period.end)}"


def _iso(value: date | None) -> str:
  return value.isoformat() if value else ""


def _record_period_semantics(period: Period, gaps: GapReport) -> None:
  """Record period meaning that Tavi's bare interval cannot carry.

  ``xbrl:period`` is an ISO 8601 interval and nothing else. The four fields the
  parse derives — the duration bucket and the calendar placement — have no home
  in the model, and neither does the YTD-vs-standalone distinction that every
  consumer has to reconstruct before it can compute a quarter from cumulative
  figures. This is the concrete form of the gap.
  """
  if period.duration_type is None and period.calendar_period_key is None:
    return
  entry = {
    "period": _period_value(period),
    "duration_type": period.duration_type,
    "calendar_year": period.calendar_year,
    "calendar_quarter": period.calendar_quarter,
    "calendar_period_key": period.calendar_period_key,
  }
  if entry not in gaps.dropped_period_semantics:
    gaps.dropped_period_semantics.append(entry)


def _decimals(value: str) -> int | None:
  """``decimals`` is an integer in Tavi; INF means infinitely precise (absent)."""
  if value.upper() in ("INF", "INFINITY"):
    return None
  try:
    return int(value)
  except ValueError:
    return None
