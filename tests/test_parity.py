"""Live parity: the holon's SPARQL answers equal the SEC MCP's, to the cent.

Builds Apple's FY2025 10-K (a fixed accession, so the assertion is stable) into
a holon, then asserts every fact the SEC ``financial-statement-analysis`` tool
returns for the income statement is reproduced by :func:`fact_grid` — proving the
round trip (Arelle slice → holon.jsonld → in-memory SPARQL) is value-exact on the
consolidated slice.

Opt-in: marked ``integration`` (network + Arelle) and skipped unless
``SEC_GOV_USER_AGENT`` is set, since SEC fair-access requires an identifying
User-Agent. The golden below is captured verbatim from the MCP tool for report
``ecec9414-…`` (Apple FY2025 10-K).
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

CIK = "320193"
ACCESSION = "0000320193-25-000079"

# (qname, period end) -> value, from mcp financial-statement-analysis (AAPL, income).
GOLDEN: dict[tuple[str, str], float] = {
  ("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", "2025-09-27"): 14948500000,
  ("us-gaap:EarningsPerShareBasic", "2025-09-27"): 7.49,
  (
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "2025-09-27",
  ): 416161000000,
  ("us-gaap:SellingGeneralAndAdministrativeExpense", "2025-09-27"): 27601000000,
  ("us-gaap:OperatingExpenses", "2025-09-27"): 62151000000,
  ("us-gaap:IncomeTaxExpenseBenefit", "2025-09-27"): 20719000000,
  ("us-gaap:OperatingIncomeLoss", "2025-09-27"): 133050000000,
  ("us-gaap:EarningsPerShareDiluted", "2025-09-27"): 7.46,
  ("us-gaap:GrossProfit", "2025-09-27"): 195201000000,
  (
    "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
    "2025-09-27",
  ): 15004697000,
  ("us-gaap:NonoperatingIncomeExpense", "2025-09-27"): -321000000,
  (
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "2025-09-27",
  ): 132729000000,
  ("us-gaap:CostOfGoodsAndServicesSold", "2025-09-27"): 220960000000,
  ("us-gaap:NetIncomeLoss", "2025-09-27"): 112010000000,
  ("us-gaap:ResearchAndDevelopmentExpense", "2025-09-27"): 34550000000,
  ("us-gaap:EarningsPerShareBasic", "2024-09-28"): 6.11,
  (
    "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
    "2024-09-28",
  ): 15408095000,
  ("us-gaap:IncomeTaxExpenseBenefit", "2024-09-28"): 29749000000,
  ("us-gaap:OperatingIncomeLoss", "2024-09-28"): 123216000000,
  ("us-gaap:GrossProfit", "2024-09-28"): 180683000000,
  ("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", "2024-09-28"): 15343783000,
  (
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "2024-09-28",
  ): 391035000000,
  ("us-gaap:SellingGeneralAndAdministrativeExpense", "2024-09-28"): 26097000000,
  ("us-gaap:NonoperatingIncomeExpense", "2024-09-28"): 269000000,
  (
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "2024-09-28",
  ): 123485000000,
  ("us-gaap:OperatingExpenses", "2024-09-28"): 57467000000,
  ("us-gaap:CostOfGoodsAndServicesSold", "2024-09-28"): 210352000000,
  ("us-gaap:EarningsPerShareDiluted", "2024-09-28"): 6.08,
  ("us-gaap:NetIncomeLoss", "2024-09-28"): 93736000000,
  ("us-gaap:ResearchAndDevelopmentExpense", "2024-09-28"): 31370000000,
  ("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", "2023-09-30"): 15744231000,
  ("us-gaap:EarningsPerShareBasic", "2023-09-30"): 6.16,
  (
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "2023-09-30",
  ): 113736000000,
  ("us-gaap:OperatingExpenses", "2023-09-30"): 54847000000,
  ("us-gaap:OperatingIncomeLoss", "2023-09-30"): 114301000000,
  ("us-gaap:ResearchAndDevelopmentExpense", "2023-09-30"): 29915000000,
  (
    "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
    "2023-09-30",
  ): 383285000000,
  ("us-gaap:SellingGeneralAndAdministrativeExpense", "2023-09-30"): 24932000000,
  (
    "us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
    "2023-09-30",
  ): 15812547000,
  ("us-gaap:NonoperatingIncomeExpense", "2023-09-30"): -565000000,
  ("us-gaap:IncomeTaxExpenseBenefit", "2023-09-30"): 16741000000,
  ("us-gaap:CostOfGoodsAndServicesSold", "2023-09-30"): 214137000000,
  ("us-gaap:EarningsPerShareDiluted", "2023-09-30"): 6.13,
  ("us-gaap:NetIncomeLoss", "2023-09-30"): 96995000000,
  ("us-gaap:GrossProfit", "2023-09-30"): 169148000000,
}


@pytest.fixture(scope="module")
def aapl_graph(tmp_path_factory: pytest.TempPathFactory):
  if not os.environ.get("SEC_GOV_USER_AGENT"):
    pytest.skip("set SEC_GOV_USER_AGENT (SEC requires an identifying User-Agent)")
  from robosystems_xbrl_holon.cli import _build_one
  from robosystems_xbrl_holon.config import CONFIG
  from robosystems_xbrl_holon.edgar import EdgarClient
  from robosystems_xbrl_holon.query import load_holon

  out = tmp_path_factory.mktemp("aapl") / "aapl.holon.jsonld"
  _build_one(EdgarClient(config=CONFIG), CIK, ACCESSION, out, CONFIG.arelle_cache_dir)
  return load_holon(out)


def test_income_statement_matches_sec_mcp(aapl_graph) -> None:
  from robosystems_xbrl_holon.query import fact_grid

  qnames = sorted({q for (q, _e) in GOLDEN})
  rows = fact_grid(aapl_graph, elements=qnames, period_type="annual")
  got = {(r.qname, r.end_date): r.value for r in rows}

  missing = [k for k in GOLDEN if k not in got]
  assert not missing, f"holon missing {len(missing)} golden facts: {missing[:5]}"
  mismatched = {
    k: (want, got[k]) for k, want in GOLDEN.items() if abs(got[k] - want) > 0.005
  }
  assert not mismatched, f"value mismatch: {mismatched}"
