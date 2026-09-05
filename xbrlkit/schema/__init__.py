"""The XBRL property-graph schema: the node and relationship tables a filing
projects into, and their LadybugDB DDL.

One asset, two consumers. ``xbrlkit build --format lpg`` creates these tables
in a single-filing database, and the RoboSystems platform creates the same
tables in its shared ``sec`` graph, so Cypher written against either runs on
the other. Property order is load-bearing — LadybugDB's ``COPY FROM`` is
positional — so every table is an ordered tuple and nothing here is sorted.

Two tables (``FactSet``, ``Classification``) and their relationships are
filled by the platform's enrichment, never by the projection; they are
declared so the schema is whole and a query that names them parses.
"""

from __future__ import annotations

from dataclasses import dataclass

STRING = "STRING"
INT32 = "INT32"
INT64 = "INT64"
DOUBLE = "DOUBLE"
BOOLEAN = "BOOLEAN"


@dataclass(frozen=True)
class Property:
  """One column of a node or relationship table."""

  name: str
  type: str


@dataclass(frozen=True)
class NodeTable:
  """A node table. ``identifier`` is always the primary key."""

  name: str
  properties: tuple[Property, ...]
  primary_key: str = "identifier"

  @property
  def columns(self) -> tuple[str, ...]:
    return tuple(p.name for p in self.properties)

  def ddl(self) -> str:
    body = ",\n        ".join(f"{p.name} {p.type}" for p in self.properties)
    return (
      f"CREATE NODE TABLE IF NOT EXISTS {self.name}(\n"
      f"        {body},\n"
      f"        PRIMARY KEY({self.primary_key})\n"
      f"    )"
    )


@dataclass(frozen=True)
class RelTable:
  """A relationship table; its rows are ``from``, ``to``, then the properties."""

  name: str
  from_node: str
  to_node: str
  properties: tuple[Property, ...] = ()

  @property
  def columns(self) -> tuple[str, ...]:
    return ("from", "to", *(p.name for p in self.properties))

  def ddl(self) -> str:
    props = "".join(f",\n        {p.name} {p.type}" for p in self.properties)
    return (
      f"CREATE REL TABLE IF NOT EXISTS {self.name}"
      f"(FROM {self.from_node} TO {self.to_node}{props})"
    )


def _p(name: str, type_: str = STRING) -> Property:
  return Property(name, type_)


NODE_TABLES: tuple[NodeTable, ...] = (
  NodeTable(
    "Entity",
    (
      _p("identifier"),
      _p("uri"),
      _p("scheme"),
      _p("cik"),
      _p("ticker"),
      _p("exchange"),
      _p("name"),
      _p("legal_name"),
      _p("industry"),
      _p("entity_type"),
      _p("sic"),
      _p("sic_description"),
      _p("category"),
      _p("state_of_incorporation"),
      _p("fiscal_year_end"),
      _p("tax_id"),
      _p("lei"),
      _p("phone"),
      _p("website"),
      _p("status"),
      _p("is_parent", BOOLEAN),
      _p("parent_entity_id"),
      _p("created_at"),
      _p("updated_at"),
    ),
  ),
  NodeTable(
    "Period",
    (
      _p("identifier"),
      _p("uri"),
      _p("start_date"),
      _p("end_date"),
      _p("calendar_year", INT32),
      _p("calendar_quarter"),
      _p("days_in_period", INT32),
      _p("period_type"),
      _p("duration_type"),
      _p("calendar_period_key"),
    ),
  ),
  NodeTable(
    "Unit",
    (
      _p("identifier"),
      _p("uri"),
      _p("measure"),
      _p("value"),
      _p("numerator_uri"),
      _p("denominator_uri"),
    ),
  ),
  NodeTable(
    "Element",
    (
      _p("identifier"),
      _p("uri"),
      _p("qname"),
      _p("name"),
      _p("period_type"),
      _p("type"),
      _p("balance"),
      _p("is_abstract", BOOLEAN),
      _p("is_dimension_item", BOOLEAN),
      _p("is_domain_member", BOOLEAN),
      _p("is_hypercube_item", BOOLEAN),
      _p("is_integer", BOOLEAN),
      _p("is_numeric", BOOLEAN),
      _p("is_shares", BOOLEAN),
      _p("is_fraction", BOOLEAN),
      _p("is_textblock", BOOLEAN),
      _p("substitution_group"),
      _p("item_type"),
      _p("canonical_concept"),
      _p("canonical_confidence", DOUBLE),
    ),
  ),
  NodeTable(
    "Label",
    (_p("identifier"), _p("value"), _p("type"), _p("language")),
  ),
  NodeTable("Reference", (_p("identifier"), _p("value"), _p("type"))),
  NodeTable(
    "Taxonomy",
    (
      _p("identifier"),
      _p("uri"),
      _p("name"),
      _p("version"),
      _p("namespace"),
      _p("description"),
      _p("taxonomy_type"),
    ),
  ),
  NodeTable(
    "Dimension",
    (
      _p("identifier"),
      _p("axis"),
      _p("member"),
      _p("dimension_type"),
      _p("axis_uri"),
      _p("member_uri"),
      _p("type"),
      _p("is_explicit", BOOLEAN),
      _p("is_typed", BOOLEAN),
    ),
  ),
  NodeTable(
    "Structure",
    (
      _p("identifier"),
      _p("uri"),
      _p("network_uri"),
      _p("definition"),
      _p("number"),
      _p("type"),
      _p("name"),
      _p("canonical_type"),
      _p("canonical_confidence", DOUBLE),
    ),
  ),
  NodeTable(
    "Association",
    (
      _p("identifier"),
      _p("arcrole"),
      _p("order_value", DOUBLE),
      _p("association_type"),
      _p("weight", DOUBLE),
      _p("root"),
      _p("preferred_label"),
    ),
  ),
  NodeTable(
    "Classification",
    (
      _p("identifier"),
      _p("category"),
      _p("type"),
      _p("source"),
      _p("confidence", DOUBLE),
    ),
  ),
  NodeTable(
    "Report",
    (
      _p("identifier"),
      _p("uri"),
      _p("name"),
      _p("accession_number"),
      _p("form"),
      _p("filing_date"),
      _p("report_date"),
      _p("acceptance_date"),
      _p("is_inline_xbrl", BOOLEAN),
      _p("xbrl_processor_version"),
      _p("processed", BOOLEAN),
      _p("failed", BOOLEAN),
      _p("updated_at"),
      _p("fiscal_year_focus", INT32),
      _p("fiscal_period_focus"),
      _p("fiscal_year_end_month", INT32),
    ),
  ),
  NodeTable(
    "Fact",
    (
      _p("identifier"),
      _p("uri"),
      _p("value"),
      _p("numeric_value", DOUBLE),
      _p("fact_type"),
      _p("decimals"),
      _p("value_type"),
      _p("content_type"),
      _p("has_dimensions", BOOLEAN),
      _p("dimension_count", INT64),
    ),
  ),
  NodeTable(
    "FactSet",
    (_p("identifier"), _p("factset_type"), _p("provenance")),
  ),
)

REL_TABLES: tuple[RelTable, ...] = (
  RelTable("ELEMENT_HAS_LABEL", "Element", "Label"),
  RelTable("ELEMENT_HAS_REFERENCE", "Element", "Reference"),
  RelTable("TAXONOMY_HAS_LABEL", "Taxonomy", "Label", (_p("element_uri"),)),
  RelTable("TAXONOMY_HAS_REFERENCE", "Taxonomy", "Reference"),
  RelTable("DIMENSION_HAS_AXIS_ELEMENT", "Dimension", "Element"),
  RelTable("DIMENSION_HAS_MEMBER_ELEMENT", "Dimension", "Element"),
  RelTable("STRUCTURE_HAS_TAXONOMY", "Structure", "Taxonomy"),
  RelTable("STRUCTURE_HAS_ASSOCIATION", "Structure", "Association"),
  RelTable("ASSOCIATION_HAS_FROM_ELEMENT", "Association", "Element"),
  RelTable("ASSOCIATION_HAS_TO_ELEMENT", "Association", "Element"),
  RelTable("ASSOCIATION_HAS_CLASSIFICATION", "Association", "Classification"),
  RelTable("ENTITY_HAS_REPORT", "Entity", "Report"),
  RelTable("REPORT_HAS_FACT", "Report", "Fact"),
  RelTable("FACT_HAS_ELEMENT", "Fact", "Element"),
  RelTable("FACT_HAS_ENTITY", "Fact", "Entity"),
  RelTable("FACT_HAS_PERIOD", "Fact", "Period"),
  RelTable("FACT_HAS_UNIT", "Fact", "Unit"),
  RelTable("FACT_HAS_DIMENSION", "Fact", "Dimension"),
  RelTable("FACT_SET_CONTAINS_FACT", "FactSet", "Fact"),
  RelTable("STRUCTURE_HAS_FACT_SET", "Structure", "FactSet"),
  RelTable("REPORT_HAS_FACT_SET", "Report", "FactSet"),
  RelTable("REPORT_USES_TAXONOMY", "Report", "Taxonomy"),
)

# Tables the projection never writes rows into: the platform's enrichment does.
ENRICHMENT_TABLES: frozenset[str] = frozenset(
  {
    "FactSet",
    "Classification",
    "FACT_SET_CONTAINS_FACT",
    "STRUCTURE_HAS_FACT_SET",
    "REPORT_HAS_FACT_SET",
    "ASSOCIATION_HAS_CLASSIFICATION",
  }
)

_NODES_BY_NAME = {t.name: t for t in NODE_TABLES}
_RELS_BY_NAME = {t.name: t for t in REL_TABLES}


def node_table(name: str) -> NodeTable:
  return _NODES_BY_NAME[name]


def rel_table(name: str) -> RelTable:
  return _RELS_BY_NAME[name]


def ddl() -> list[str]:
  """The ``CREATE … TABLE IF NOT EXISTS`` statements, nodes before relationships."""
  return [t.ddl() for t in NODE_TABLES] + [t.ddl() for t in REL_TABLES]


def type_default(type_: str) -> object:
  """The value the platform writes for a column a row does not carry.

  Not null: the RoboSystems parquet writer fills an absent STRING with ``""``,
  an integer with ``0``, a DOUBLE with ``0.0`` and a BOOLEAN with ``False``.
  The projection mirrors it so a filing's rows read the same in both graphs.
  """
  if type_ == STRING:
    return ""
  if type_ in (INT32, INT64):
    return 0
  if type_ == DOUBLE:
    return 0.0
  if type_ == BOOLEAN:
    return False
  return None


__all__ = (
  "BOOLEAN",
  "DOUBLE",
  "ENRICHMENT_TABLES",
  "INT32",
  "INT64",
  "NODE_TABLES",
  "NodeTable",
  "Property",
  "REL_TABLES",
  "RelTable",
  "STRING",
  "ddl",
  "node_table",
  "rel_table",
  "type_default",
)
