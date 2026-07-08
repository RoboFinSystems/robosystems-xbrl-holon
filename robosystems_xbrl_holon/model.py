"""XbrlModel — the neutral, lossless, single-filing in-memory model.

One parse produces this; each serializer consumes it. Today there is one
serializer (the holon / RDF projection); a second (the LPG / parquet
projection) is planned. The point of this model is that both hang off one
parse.

Fidelity loss is a *projection* choice, never a limitation of this model. The
parse captures the full XBRL — text facts, dimensions, every network — and each
serializer decides what to shed (the holon MVP drops text facts and
dimensions; the LPG projection keeps them).

Stateless and single-filing by design: an ``XbrlModel`` describes exactly one
filing and knows nothing about any other. All cross-filing / corpus concerns
(dedup, aggregation) live in the caller, not here.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

PeriodType = Literal["instant", "duration", "forever"]
BalanceType = Literal["debit", "credit"]
NetworkKind = Literal["presentation", "calculation", "definition"]
ValueKind = Literal["numeric", "text"]
DurationType = Literal["annual", "quarterly", "semi_annual", "nine_months", "other"]
AxisType = Literal["segment", "scenario"]


class FilingMeta(BaseModel):
  """Identity + fiscal context of the one filing this model describes."""

  accession: str
  cik: str  # zero-padded 10-digit
  form: str | None = None
  filing_date: date | None = None
  fiscal_year_focus: str | None = None
  fiscal_period_focus: str | None = None
  fiscal_year_end_month: str | None = None
  taxonomy_namespaces: list[str] = Field(default_factory=list)


class EntityIdentity(BaseModel):
  """The reporting entity (the XBRL context entity, resolved to the filer)."""

  cik: str
  scheme: str = "http://www.sec.gov/CIK"
  name: str | None = None
  legal_name: str | None = None
  ein: str | None = None
  ticker: str | None = None


class Label(BaseModel):
  """One label-linkbase entry for a concept (role selects standard/terse/…)."""

  value: str
  role: str | None = None
  language: str | None = None


class Concept(BaseModel):
  """An XBRL concept (``<xs:element>``) as walked from the DTS.

  Coverage is DTS-wide, not fact-driven: a ``Concept`` exists for every qname
  the slice touches — reported facts, presentation/calculation/definition arc
  endpoints (abstract headers, subtotals), and dimension axes/members/domains/
  hypercubes — so labels and structural flags are available for all of them.
  """

  qname: str
  namespace: str
  name: str
  period_type: PeriodType | None = None
  balance: BalanceType | None = None
  is_abstract: bool = False
  is_numeric: bool = False
  is_textblock: bool = False
  is_hypercube_item: bool = False
  is_dimension_item: bool = False
  is_domain_member: bool = False
  is_shares: bool = False
  is_integer: bool = False
  substitution_group: str | None = None
  item_type: str | None = None
  pref_label: str | None = None
  labels: list[Label] = Field(default_factory=list)


class Period(BaseModel):
  """A reporting period. ``end`` carries the instant date for instant periods.

  ``id`` is a content-derived, cross-filing-stable identifier so periods
  dedupe. Dates are already normalized (Arelle's exclusive next-midnight has
  been rolled back by one day at parse time). The calendar fields are a
  deterministic enrichment derived from the dates (not raw XBRL) — they place a
  period on a common calendar axis so "which quarter/year is this" is legible
  without re-deriving it: ``duration_type`` buckets the day span,
  ``calendar_year``/``calendar_quarter`` normalize by the end date, and
  ``calendar_period_key`` is a compact label (``2026Q1`` / ``2026`` / a date).
  """

  id: str
  period_type: PeriodType
  start: date | None = None
  end: date | None = None
  duration_type: DurationType | None = None
  calendar_year: int | None = None
  calendar_quarter: str | None = None
  calendar_period_key: str | None = None


class Unit(BaseModel):
  """A unit of measure. ``measure`` is the resolved token (e.g. ``iso4217:USD``)."""

  id: str
  measure: str
  numerator_uri: str | None = None
  denominator_uri: str | None = None


class DimQualifier(BaseModel):
  """One dimensional coordinate on a fact's context (segment/scenario member).

  ``axis_type`` records whether the coordinate came from the context's
  ``<segment>`` or ``<scenario>`` (resolved per-dimension, not per-context).
  """

  axis_qname: str
  member_qname: str | None = None
  typed_value: str | None = None
  is_explicit: bool = True
  axis_type: AxisType | None = None


class XbrlFact(BaseModel):
  """One reported fact. Numeric ⇔ the fact carries a unit (XBRL convention)."""

  id: str
  concept_qname: str
  period_id: str
  unit_id: str | None = None
  entity_cik: str
  dims: list[DimQualifier] = Field(default_factory=list)
  value_str: str | None = None
  numeric_value: float | None = None
  decimals: str | None = None
  value_kind: ValueKind = "numeric"


class Arc(BaseModel):
  """One linkbase relationship (parent → child), qname-addressed.

  ``arcrole`` is the full arcrole URI. For presentation/calculation it is the
  parent-child / summation-item role; for definition networks it distinguishes
  the XBRL-dimensions wiring (all / hypercube-dimension / dimension-domain /
  domain-member / dimension-default), which ``Network.kind`` alone collapses.
  """

  from_qname: str
  to_qname: str
  arcrole: str | None = None
  order: float | None = None
  weight: float | None = None
  preferred_label: str | None = None
  is_root: bool = False


class Network(BaseModel):
  """One extended-link-role network (a statement or disclosure), one linkbase kind."""

  role_uri: str
  definition: str | None = None
  kind: NetworkKind
  arcs: list[Arc] = Field(default_factory=list)


class XbrlModel(BaseModel):
  """The whole filing as neutral objects — the contract between parse and serialize."""

  filing: FilingMeta
  entity: EntityIdentity
  concepts: dict[str, Concept] = Field(default_factory=dict)
  periods: list[Period] = Field(default_factory=list)
  units: list[Unit] = Field(default_factory=list)
  facts: list[XbrlFact] = Field(default_factory=list)
  networks: list[Network] = Field(default_factory=list)
