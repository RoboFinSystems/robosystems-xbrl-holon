"""Walk an Arelle ``ModelXbrl`` into the neutral :class:`XbrlModel`.

This mirrors the ``make_*`` methods of the robosystems SEC adapter
(``adapters/sec/processors/xbrl_graph.py``) — same Arelle touch-points, same
date normalization, same numeric-vs-text convention — but writes Pydantic
objects into one in-memory model instead of a fan of parquet DataFrames.

Key conventions carried over from the adapter:

- **Numeric ⇔ the fact carries a unit** (``f.unit is not None``), *not* the
  concept's declared type.
- Arelle stores instant/end dates as the *exclusive* next midnight, so every
  instant/end date is rolled back one day (``- timedelta(1)``).
- Measures resolve to prefixed tokens (``iso4217:USD``) from the QName.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from arelle import XbrlConst

from robosystems_xbrl_holon.model import (
  Arc,
  Concept,
  DimQualifier,
  EntityIdentity,
  FilingMeta,
  Label,
  Network,
  NetworkKind,
  Period,
  Unit,
  XbrlFact,
  XbrlModel,
)
from robosystems_xbrl_holon.parse.ids import fact_id, period_id, unit_id

if TYPE_CHECKING:
  from arelle.ModelXbrl import ModelXbrl

# Content-URI stem for period ids (matches the adapter's ISO 8601 stem so the
# derived period ids are stable/portable).
ISO_8601_URI = "http://www.w3.org/2001/XMLSchema#dateTime"

# Extended-link roles that carry no statement/disclosure network — the label
# and reference linkbases (standard link role) plus the enumeration-list roles.
ROLES_FILTERED = {
  "http://www.xbrl.org/2003/role/link",
  "http://fasb.org/srt/role/srt-eedm/ExtensibleEnumerationLists",
  "http://fasb.org/us-gaap/role/eedm/ExtensibleEnumerationLists",
}

_DEI_FISCAL_YEAR = "dei:DocumentFiscalYearFocus"
_DEI_FISCAL_PERIOD = "dei:DocumentFiscalPeriodFocus"
_DEI_FISCAL_YEAR_END = "dei:CurrentFiscalYearEndDate"


def to_xbrl_model(
  mx: ModelXbrl,
  filing: FilingMeta,
  *,
  entity_name: str | None = None,
  entity_ein: str | None = None,
  entity_ticker: str | None = None,
) -> XbrlModel:
  """Convert a loaded ``ModelXbrl`` into the neutral single-filing model.

  ``entity_name`` / ``entity_ein`` / ``entity_ticker`` come from the EDGAR
  submissions header (the XBRL instance carries only the CIK); pass them when
  available so the reporting entity is fully identified.
  """
  report_uri = filing.accession
  main_cik = _normalize_cik(filing.cik)

  concepts: dict[str, Concept] = {}
  periods: dict[str, Period] = {}
  units: dict[str, Unit] = {}
  facts: list[XbrlFact] = []
  namespaces: set[str] = set()

  entity_scheme: str | None = None
  fiscal_year_focus: str | None = None
  fiscal_period_focus: str | None = None
  fiscal_year_end_month: str | None = None

  for f in mx.facts:
    if f.context is None:
      continue
    concept = f.concept
    if concept is None or concept.qname is None:
      continue

    qname_str = str(concept.qname)

    # DEI cover-page fiscal context.
    if qname_str == _DEI_FISCAL_YEAR:
      fiscal_year_focus = _text(f.value) or fiscal_year_focus
    elif qname_str == _DEI_FISCAL_PERIOD:
      fiscal_period_focus = _text(f.value) or fiscal_period_focus
    elif qname_str == _DEI_FISCAL_YEAR_END:
      month = _fiscal_year_end_month(f.value)
      if month is not None:
        fiscal_year_end_month = month

    # Concept (deduped by qname). Full DTS coverage is completed below from
    # dimension members (in _make_dims) and network endpoints (in
    # _make_networks), so abstract headers and axis/member/domain/hypercube
    # concepts also get a Concept with labels + flags.
    _ensure_concept(mx, concepts, namespaces, concept)

    # Period (deduped by content-derived id). Skip facts with invalid dates.
    period = _make_period(f.context)
    if period is None:
      continue
    if period.id not in periods:
      periods[period.id] = period

    # Unit (numeric facts only, deduped by resolved measure id).
    unit_ref: str | None = None
    if f.unit is not None:
      unit = _make_unit(f.unit)
      if unit is not None:
        if unit.id not in units:
          units[unit.id] = unit
        unit_ref = unit.id

    # Entity identity (prefer the context whose CIK is the filer's).
    scheme, raw_cik = f.context.entityIdentifier
    norm_cik = _normalize_cik(raw_cik)
    if entity_scheme is None or norm_cik == main_cik:
      entity_scheme = scheme

    is_numeric = f.unit is not None
    numeric_value: float | None = None
    if is_numeric and f.value is not None:
      try:
        numeric_value = float(str(f.value))
      except (ValueError, TypeError):
        numeric_value = None

    facts.append(
      XbrlFact(
        id=fact_id(report_uri, f.md5sum.value),
        concept_qname=qname_str,
        period_id=period.id,
        unit_id=unit_ref,
        entity_cik=norm_cik,
        dims=_make_dims(f.context, mx, concepts, namespaces),
        value_str=str(f.value) if f.value is not None else None,
        numeric_value=numeric_value,
        decimals=(str(f.decimals) if (is_numeric and f.decimals is not None) else None),
        value_kind="numeric" if is_numeric else "text",
      )
    )

  # Networks last: their arc endpoints (abstract headers, subtotals, hypercube
  # wiring) complete the concept coverage and add their namespaces.
  networks = _make_networks(mx, concepts, namespaces)

  updated_filing = filing.model_copy(
    update={
      "fiscal_year_focus": fiscal_year_focus or filing.fiscal_year_focus,
      "fiscal_period_focus": fiscal_period_focus or filing.fiscal_period_focus,
      "fiscal_year_end_month": (fiscal_year_end_month or filing.fiscal_year_end_month),
      "taxonomy_namespaces": sorted(set(filing.taxonomy_namespaces) | namespaces),
    }
  )

  entity = EntityIdentity(
    cik=main_cik,
    scheme=entity_scheme or "http://www.sec.gov/CIK",
    name=entity_name,
    legal_name=entity_name,
    ein=entity_ein,
    ticker=entity_ticker,
  )

  return XbrlModel(
    filing=updated_filing,
    entity=entity,
    concepts=concepts,
    periods=list(periods.values()),
    units=list(units.values()),
    facts=facts,
    networks=networks,
  )


def _ensure_concept(
  mx: ModelXbrl,
  concepts: dict[str, Concept],
  namespaces: set[str],
  concept: Any,
) -> None:
  """Register a concept (deduped by qname) with its namespace, if valid.

  The single collection point for every concept the slice touches — reported
  facts, dimension axes/members, and network-arc endpoints — so DTS coverage is
  complete rather than fact-driven.
  """
  if concept is None:
    return
  qname = getattr(concept, "qname", None)
  if qname is None:
    return
  qname_str = str(qname)
  if qname_str in concepts:
    return
  concepts[qname_str] = _make_concept(mx, concept)
  concept_ns = getattr(qname, "namespaceURI", None)
  if concept_ns:
    namespaces.add(concept_ns)


def _make_concept(mx: ModelXbrl, concept: Any) -> Concept:
  """Build a :class:`Concept` from an Arelle ``ModelConcept``."""
  qname = concept.qname
  document = getattr(concept, "document", None)
  namespace = getattr(qname, "namespaceURI", None) or (
    getattr(document, "targetNamespace", None) if document else None
  )

  subgroup = getattr(concept, "substitutionGroupQname", None)
  type_qname = getattr(concept, "typeQname", None)
  labels, pref_label = _make_labels(mx, concept)

  return Concept(
    qname=str(qname),
    namespace=namespace or "",
    name=qname.localName,
    period_type=_period_type(getattr(concept, "periodType", None)),
    balance=_balance(getattr(concept, "balance", None)),
    is_abstract=bool(getattr(concept, "isAbstract", False)),
    is_numeric=bool(getattr(concept, "isNumeric", False)),
    is_textblock=bool(getattr(concept, "isTextBlock", False)),
    is_hypercube_item=bool(getattr(concept, "isHypercubeItem", False)),
    is_dimension_item=bool(getattr(concept, "isDimensionItem", False)),
    is_domain_member=bool(getattr(concept, "isDomainMember", False)),
    is_shares=bool(getattr(concept, "isShares", False)),
    is_integer=bool(getattr(concept, "isInteger", False)),
    substitution_group=str(subgroup) if subgroup is not None else None,
    item_type=type_qname.localName if type_qname is not None else None,
    pref_label=pref_label,
    labels=labels,
  )


def _make_labels(mx: ModelXbrl, concept: Any) -> tuple[list[Label], str | None]:
  """Collect a concept's label-linkbase entries + its standard label."""
  labels: list[Label] = []
  pref_label: str | None = None
  rel_set = mx.relationshipSet(XbrlConst.conceptLabel)
  for rel in rel_set.fromModelObject(concept):
    label_obj = rel.toModelObject
    if label_obj is None:
      continue
    role = getattr(label_obj, "role", None)
    value = getattr(label_obj, "text", None) or ""
    labels.append(
      Label(
        value=value,
        role=role,
        language=getattr(label_obj, "xmlLang", None),
      )
    )
    if role == XbrlConst.standardLabel and pref_label is None:
      pref_label = value
  if pref_label is None and labels:
    pref_label = labels[0].value
  return labels, pref_label


def _make_period(context: Any) -> Period | None:
  """Build a :class:`Period` from a fact context, or ``None`` if invalid.

  Arelle stores instant/end datetimes as the exclusive next midnight, so both
  are rolled back one day to recover the reported date.
  """
  if context.isInstantPeriod:
    end = _to_date(context.instantDatetime - timedelta(1))
    if end is None:
      return None
    return Period(
      id=period_id(f"{ISO_8601_URI}#{end.isoformat()}"),
      period_type="instant",
      start=None,
      end=end,
    )
  if context.isStartEndPeriod:
    start = _to_date(context.startDatetime)
    end = _to_date(context.endDatetime - timedelta(1))
    if start is None or end is None:
      return None
    return Period(
      id=period_id(f"{ISO_8601_URI}#{start.isoformat()}/{end.isoformat()}"),
      period_type="duration",
      start=start,
      end=end,
      duration_type=_duration_type(start, end),
    )
  if context.isForeverPeriod:
    return Period(
      id=period_id(f"{ISO_8601_URI}#Forever"),
      period_type="forever",
      start=None,
      end=None,
    )
  return None


def _make_unit(unit: Any) -> Unit | None:
  """Build a :class:`Unit` from an Arelle ``ModelUnit``."""
  if unit.isSingleMeasure:
    token, uri = _measure_token(unit.measures[0][0])
    return Unit(id=unit_id(uri), measure=token)
  if unit.isDivide:
    num_token, num_uri = _measure_token(unit.measures[0][0])
    den_token, den_uri = _measure_token(unit.measures[1][0])
    return Unit(
      id=unit_id(f"{num_uri}/{den_uri}"),
      measure=f"{num_token}/{den_token}",
      numerator_uri=num_uri,
      denominator_uri=den_uri,
    )
  return None


def _measure_token(qname: Any) -> tuple[str, str]:
  """Resolve a measure QName to ``(prefix:localName, namespace#localName)``."""
  local = qname.localName
  namespace = getattr(qname, "namespaceURI", None) or ""
  prefix = getattr(qname, "prefix", None)
  token = f"{prefix}:{local}" if prefix else local
  uri = f"{namespace}#{local}" if namespace else local
  return token, uri


def _make_dims(
  context: Any,
  mx: ModelXbrl,
  concepts: dict[str, Concept],
  namespaces: set[str],
) -> list[DimQualifier]:
  """Extract explicit + typed dimensional qualifiers from a fact context.

  Registers each axis (and explicit member) as a full :class:`Concept` so the
  serializer can label them, and records segment-vs-scenario per dimension.
  """
  # segDimValues / scenDimValues are keyed by the *axis ModelConcept*, not the
  # QName, so segment/scenario is tested against mem.dimension (the axis concept).
  seg = set(getattr(context, "segDimValues", {}) or {})
  scen = set(getattr(context, "scenDimValues", {}) or {})
  dims: list[DimQualifier] = []
  for dim, mem in context.qnameDims.items():
    axis_concept = getattr(mem, "dimension", None)
    _ensure_concept(mx, concepts, namespaces, axis_concept)
    member_qname: str | None = None
    if mem.isExplicit:
      member = getattr(mem, "member", None)
      _ensure_concept(mx, concepts, namespaces, member)
      if member is not None and member.qname is not None:
        member_qname = str(member.qname)
    dims.append(
      DimQualifier(
        axis_qname=str(dim),
        member_qname=member_qname,
        typed_value=mem.stringValue if mem.isTyped else None,
        is_explicit=bool(mem.isExplicit),
        axis_type=(
          "segment"
          if axis_concept in seg
          else "scenario"
          if axis_concept in scen
          else None
        ),
      )
    )
  return dims


def _make_networks(
  mx: ModelXbrl,
  concepts: dict[str, Concept],
  namespaces: set[str],
) -> list[Network]:
  """Enumerate presentation/calculation/definition networks from base sets.

  Registers every arc endpoint as a :class:`Concept` (completing DTS coverage
  for abstract headers, subtotals, and dimensional wiring) and stamps each arc
  with its specific ``arcrole`` so definition networks stay distinguishable.
  """
  networks: list[Network] = []
  seen: set[tuple[str, str]] = set()

  for base_set_key in mx.baseSets.keys():
    arcrole = base_set_key[0]
    role_uri = base_set_key[1]
    if not isinstance(arcrole, str) or not isinstance(role_uri, str):
      continue
    if role_uri in ROLES_FILTERED:
      continue
    kind = _classify_arcrole(arcrole)
    if kind is None:
      continue
    key = (arcrole, role_uri)
    if key in seen:
      continue
    seen.add(key)

    rels = mx.relationshipSet(arcrole, role_uri)
    if rels is None:
      continue

    roots = set(rels.rootConcepts or [])
    is_calc = kind == "calculation"
    arcs: list[Arc] = []
    for r in rels.modelRelationships:
      frm = r.fromModelObject
      to = r.toModelObject
      if frm is None or to is None or frm.qname is None or to.qname is None:
        continue
      _ensure_concept(mx, concepts, namespaces, frm)
      _ensure_concept(mx, concepts, namespaces, to)
      weight = r.weight if is_calc else None
      arcs.append(
        Arc(
          from_qname=str(frm.qname),
          to_qname=str(to.qname),
          arcrole=arcrole,
          order=float(r.order) if r.order is not None else None,
          weight=float(weight) if weight is not None else None,
          preferred_label=getattr(r, "preferredLabel", None),
          is_root=frm in roots,
        )
      )
    if not arcs:
      continue

    networks.append(
      Network(
        role_uri=role_uri,
        definition=_role_definition(mx, role_uri),
        kind=kind,
        arcs=arcs,
      )
    )
  return networks


def _classify_arcrole(arcrole: str) -> NetworkKind | None:
  """Map an arcrole to a linkbase kind, or ``None`` to skip it."""
  if arcrole == XbrlConst.parentChild:
    return "presentation"
  if arcrole == XbrlConst.summationItem:
    return "calculation"
  if arcrole in (XbrlConst.conceptLabel, XbrlConst.conceptReference):
    return None
  return "definition"


def _role_definition(mx: ModelXbrl, role_uri: str) -> str | None:
  """Human-readable definition for an extended link role, if declared."""
  role_types = mx.roleTypes.get(role_uri)
  if not role_types:
    return None
  return getattr(role_types[0], "definition", None)


def _to_date(value: Any) -> date | None:
  """Coerce an Arelle datetime to a validated ``date`` (or ``None``)."""
  try:
    resolved = value.date() if isinstance(value, datetime) else value
  except Exception:
    return None
  if not isinstance(resolved, date):
    return None
  if resolved.year < 1900 or resolved.year > 2100:
    return None
  return resolved


def _normalize_cik(raw: Any) -> str:
  """Zero-pad a numeric CIK to 10 digits; pass non-numeric ids through."""
  text = str(raw)
  if text.isdigit():
    return text.lstrip("0").zfill(10)
  return text


def _period_type(value: Any) -> str | None:
  """Guard an Arelle period type to the model's allowed literals."""
  return value if value in ("instant", "duration", "forever") else None


def _duration_type(start: date, end: date) -> str | None:
  """Bucket a duration span into annual / quarterly (else ``None``).

  ``end`` is already the inclusive reported end (rolled back one day), so the
  span is ``end - start``. A 52/53-week fiscal year lands ~364-371 days; a
  fiscal quarter ~13 weeks. 6-/9-month year-to-date spans deliberately fall
  through to ``None`` — they are neither annual nor quarterly.
  """
  days = (end - start).days
  if 340 <= days <= 380:
    return "annual"
  if 80 <= days <= 100:
    return "quarterly"
  return None


def _balance(value: Any) -> str | None:
  """Guard an Arelle balance to the model's allowed literals."""
  return value if value in ("debit", "credit") else None


def _text(value: Any) -> str | None:
  """Return a stripped string form of a fact value, or ``None``."""
  if value is None:
    return None
  text = str(value).strip()
  return text or None


def _fiscal_year_end_month(value: Any) -> str | None:
  """Parse the two-digit month from a ``--MM-DD`` fiscal-year-end value."""
  text = str(value) if value is not None else ""
  if text.startswith("--") and len(text) >= 5:
    month = text[2:4]
    if month.isdigit():
      return month
  return None
