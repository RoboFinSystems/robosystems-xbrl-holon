"""Classify a presentation network into a primary-statement block type.

The holon MVP keeps only the four primary financial statements; everything
else (disclosures, document/entity info, parentheticals, detail schedules) is
skipped. Classification is a case-insensitive keyword heuristic over the
network's human definition, falling back to the role URI when no definition is
present or the definition does not classify.
"""

from __future__ import annotations

import re

# Deterministic block order — also the priority used when a definition could
# plausibly match more than one statement family.
BLOCK_TYPES: tuple[str, ...] = (
  "balance_sheet",
  "income_statement",
  "cash_flow_statement",
  "equity_statement",
)


def _match(text: str) -> str | None:
  """Return the block type for pre-normalized (lowercased) statement text."""
  if "cash flow" in text:
    return "cash_flow_statement"
  if "balance sheet" in text or "financial position" in text:
    return "balance_sheet"
  if (
    "stockholders' equity" in text
    or "shareholders' equity" in text
    or "changes in equity" in text
  ):
    return "equity_statement"
  if (
    "comprehensive income" in text
    or "operations" in text
    or "income" in text
    or "earnings" in text
  ):
    return "income_statement"
  return None


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _normalize(value: str | None) -> str:
  # Fold curly apostrophes to ASCII so "stockholders’ equity" matches.
  return (value or "").replace("’", "'").lower()


def _normalize_uri(value: str | None) -> str:
  """Normalize a role URI's local name for phrase matching.

  Role URIs carry the statement name as a camelCase / hyphenated segment
  (``.../BalanceSheet``, ``.../StatementOfCashFlows``) rather than prose, so
  split camelCase and separators back into words before matching.
  """
  if not value:
    return ""
  local = re.split(r"[/#]", value)[-1] or value
  spaced = _CAMEL_BOUNDARY.sub(" ", local)
  spaced = re.sub(r"[-_.]+", " ", spaced)
  return spaced.replace("’", "'").lower()


def classify_network(role_uri: str, definition: str | None) -> str | None:
  """Map a presentation network to a primary ``block_type`` (or ``None``).

  Returns one of ``balance_sheet`` / ``income_statement`` /
  ``cash_flow_statement`` / ``equity_statement`` for a primary statement, else
  ``None`` (the MVP skips disclosures and detail networks). Parenthetical /
  detail networks are always excluded. The definition text is matched first;
  the role URI is a fallback when it is absent or does not classify.
  """
  definition_text = _normalize(definition)
  if "parenthetical" in definition_text:
    return None
  result = _match(definition_text) if definition_text else None
  if result is not None:
    return result
  role_text = _normalize_uri(role_uri)
  if "parenthetical" in role_text:
    return None
  return _match(role_text)
