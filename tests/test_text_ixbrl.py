"""Tests for the iXBRL disclosure parser (``xbrlkit.text.ixbrl``).

Covers:
- TextBlock extraction from ix:nonNumeric elements, nested ones included
- Continuation chain resolution, nested continuations included
- Element extraction from nested ix:nonFraction tags
- Label derivation from element qnames
- Filtering (DEI/ECD skip, min word count, dedup)
- Splitting a long section into parts
"""

import pytest

from xbrlkit.text import iXBRLParser
from xbrlkit.text.ixbrl import (
  _extract_elements_from_block,
  _label_from_element_name,
  _scan_blocks,
  _strip_html,
)

_FILLER = " ".join(["disclosure"] * 25)


@pytest.mark.unit
class TestLabelFromElementName:
  def test_strips_namespace_and_textblock_suffix(self):
    assert (
      _label_from_element_name("us-gaap:GoodwillDisclosureTextBlock")
      == "Goodwill Disclosure"
    )

  def test_strips_table_textblock_suffix(self):
    assert (
      _label_from_element_name("us-gaap:DebtSecuritiesAvailableForSaleTableTextBlock")
      == "Debt Securities Available For Sale Table"
    )

  def test_splits_camel_case(self):
    assert (
      _label_from_element_name("us-gaap:RevenueFromContractWithCustomerPolicyTextBlock")
      == "Revenue From Contract With Customer Policy"
    )

  def test_handles_company_namespace(self):
    assert (
      _label_from_element_name("nvda:NatureOfOperationsPolicyTextBlock")
      == "Nature Of Operations Policy"
    )

  def test_handles_no_namespace(self):
    assert (
      _label_from_element_name("GoodwillDisclosureTextBlock") == "Goodwill Disclosure"
    )

  def test_handles_no_suffix(self):
    assert _label_from_element_name("us-gaap:Revenue") == "Revenue"


@pytest.mark.unit
class TestStripHtml:
  def test_strips_tags(self):
    assert "Hello world" in _strip_html("<p>Hello <b>world</b></p>")

  def test_removes_style_tags(self):
    result = _strip_html("<style>.hidden{}</style><p>Visible</p>")
    assert "hidden" not in result
    assert "Visible" in result

  def test_removes_script_tags(self):
    result = _strip_html("<script>alert('x')</script><p>Content</p>")
    assert "alert" not in result
    assert "Content" in result

  def test_normalizes_whitespace(self):
    result = _strip_html("<p>Hello</p>   <p>World</p>")
    assert "  " not in result

  def test_handles_html_entities(self):
    result = _strip_html("<p>A&amp;B&nbsp;C</p>")
    assert "A&B" in result

  def test_converts_tables_to_markdown(self):
    html = (
      "<table>"
      "<tr><th>Period</th><th>Revenue</th></tr>"
      "<tr><td>Q1</td><td>1000</td></tr>"
      "<tr><td>Q2</td><td>2000</td></tr>"
      "</table>"
    )
    result = _strip_html(html)
    assert "Period" in result
    assert "Revenue" in result
    assert "1000" in result
    assert "|" in result


@pytest.mark.unit
class TestExtractElementsFromBlock:
  def test_extracts_nonFraction_elements(self):
    html = """
    <ix:nonFraction name="us-gaap:Goodwill" contextRef="c1">32431</ix:nonFraction>
    <ix:nonFraction name="us-gaap:GoodwillImpairmentLoss" contextRef="c2">0</ix:nonFraction>
    """
    elements = _extract_elements_from_block(html)
    assert "us-gaap:Goodwill" in elements
    assert "us-gaap:GoodwillImpairmentLoss" in elements

  def test_extracts_nonNumeric_non_textblock_elements(self):
    html = """
    <ix:nonNumeric name="us-gaap:FiscalPeriod" contextRef="c1">FY</ix:nonNumeric>
    """
    assert "us-gaap:FiscalPeriod" in _extract_elements_from_block(html)

  def test_skips_textblock_elements(self):
    html = """
    <ix:nonNumeric name="us-gaap:GoodwillDisclosureTextBlock" contextRef="c1">text</ix:nonNumeric>
    """
    assert "us-gaap:GoodwillDisclosureTextBlock" not in _extract_elements_from_block(
      html
    )

  def test_skips_dei_elements(self):
    html = """
    <ix:nonNumeric name="dei:EntityRegistrantName" contextRef="c1">NVIDIA</ix:nonNumeric>
    """
    assert _extract_elements_from_block(html) == []

  def test_deduplicates_elements(self):
    html = """
    <ix:nonFraction name="us-gaap:Goodwill" contextRef="c1">100</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Goodwill" contextRef="c2">200</ix:nonFraction>
    """
    assert _extract_elements_from_block(html).count("us-gaap:Goodwill") == 1

  def test_returns_sorted(self):
    html = """
    <ix:nonFraction name="us-gaap:Revenue" contextRef="c1">100</ix:nonFraction>
    <ix:nonFraction name="us-gaap:Assets" contextRef="c2">200</ix:nonFraction>
    """
    elements = _extract_elements_from_block(html)
    assert elements == sorted(elements)

  def test_empty_block(self):
    assert _extract_elements_from_block("<p>No XBRL tags here</p>") == []


@pytest.mark.unit
class TestScanBlocks:
  def test_registers_every_block_with_its_depth(self):
    html = (
      '<ix:continuation id="a">A1'
      '<ix:continuation id="b">B'
      '<ix:continuation id="c">C</ix:continuation>'
      "</ix:continuation>A2</ix:continuation>"
      '<ix:continuation id="d">D</ix:continuation>'
    )
    blocks = _scan_blocks(html, "ix:continuation")
    by_id = {b.attrs.strip(): (b.depth, b.content(html)) for b in blocks}
    assert by_id['id="a"'] == (
      0,
      'A1<ix:continuation id="b">B<ix:continuation id="c">C</ix:continuation></ix:continuation>A2',
    )
    assert by_id['id="b"'] == (1, 'B<ix:continuation id="c">C</ix:continuation>')
    assert by_id['id="c"'] == (2, "C")
    assert by_id['id="d"'] == (0, "D")

  def test_is_case_insensitive_and_ignores_longer_tag_names(self):
    html = '<IX:NONNUMERIC name="x">upper</IX:NONNUMERIC><ix:nonNumericExtra>no</ix:nonNumericExtra>'
    blocks = _scan_blocks(html, "ix:nonNumeric")
    assert [b.content(html) for b in blocks] == ["upper"]

  def test_self_closing_and_unmatched_tags(self):
    html = '<ix:continuation id="a"/><ix:continuation id="b">B</ix:continuation><ix:continuation id="c">open'
    blocks = _scan_blocks(html, "ix:continuation")
    assert [b.content(html) for b in blocks] == ["B"]


@pytest.mark.unit
class TestiXBRLParser:
  def test_extracts_simple_textblock(self):
    html = """
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:GoodwillDisclosureTextBlock" id="f-1">
      <p>The following table summarizes goodwill by segment.
      <ix:nonFraction name="us-gaap:Goodwill" contextRef="c1">32431</ix:nonFraction>
      million in total goodwill was recorded during the period.
      Additional goodwill details are provided below with impairment analysis.</p>
    </ix:nonNumeric>
    </body></html>
    """
    sections = iXBRLParser().parse(html)

    assert len(sections) == 1
    assert sections[0].section_id == "us-gaap:GoodwillDisclosureTextBlock"
    assert sections[0].section_label == "Goodwill Disclosure"
    assert sections[0].label == "Goodwill Disclosure"
    assert "goodwill" in sections[0].content.lower()
    assert "us-gaap:Goodwill" in sections[0].xbrl_elements
    assert sections[0].element_count == 1
    assert (sections[0].part, sections[0].part_count) == (1, 1)

  def test_resolves_continuation_chain(self):
    html = """
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:DebtDisclosureTextBlock" id="f-1" continuedAt="f-1-cont">
      Debt Overview
    </ix:nonNumeric>
    <ix:continuation id="f-1-cont">
      <p>The company has outstanding debt of
      <ix:nonFraction name="us-gaap:DebtInstrumentCarryingAmount" contextRef="c1">5000</ix:nonFraction>
      million. The weighted average interest rate is
      <ix:nonFraction name="us-gaap:DebtInstrumentInterestRateStatedPercentage" contextRef="c2">3.5</ix:nonFraction>
      percent. These debt instruments mature over the next ten years with various covenants and restrictions.</p>
    </ix:continuation>
    </body></html>
    """
    sections = iXBRLParser().parse(html)

    assert len(sections) == 1
    s = sections[0]
    assert s.section_id == "us-gaap:DebtDisclosureTextBlock"
    assert "5000" in s.content
    assert "us-gaap:DebtInstrumentCarryingAmount" in s.xbrl_elements
    assert "us-gaap:DebtInstrumentInterestRateStatedPercentage" in s.xbrl_elements
    assert s.element_count == 2

  def test_skips_dei_and_ecd_textblocks(self):
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="dei:DocumentsIncorporatedByReferenceTextBlock" id="f-1">
      {_FILLER}
    </ix:nonNumeric>
    <ix:nonNumeric contextRef="c-1" name="ecd:MtrlTermsOfTrdArrTextBlock" id="f-2">
      {_FILLER}
    </ix:nonNumeric>
    </body></html>
    """
    assert iXBRLParser().parse(html) == []

  def test_skips_trivial_sections(self):
    html = """
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:ShortTextBlock" id="f-1">
      Too short.
    </ix:nonNumeric>
    </body></html>
    """
    assert iXBRLParser().parse(html) == []

  def test_deduplicates_same_element(self):
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:RevenueTextBlock" id="f-1">
      First occurrence {_FILLER}
    </ix:nonNumeric>
    <ix:nonNumeric contextRef="c-2" name="us-gaap:RevenueTextBlock" id="f-2">
      Second occurrence {_FILLER}
    </ix:nonNumeric>
    </body></html>
    """
    sections = iXBRLParser().parse(html)
    assert len(sections) == 1
    assert "First occurrence" in sections[0].content

  def test_multiple_sections(self):
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:GoodwillDisclosureTextBlock" id="f-1">
      <p>{_FILLER}</p>
    </ix:nonNumeric>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:DebtDisclosureTextBlock" id="f-2">
      <p>{_FILLER}</p>
    </ix:nonNumeric>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:IncomeTaxDisclosureTextBlock" id="f-3">
      <p>{_FILLER}</p>
    </ix:nonNumeric>
    </body></html>
    """
    sections = iXBRLParser().parse(html)
    assert [s.section_id for s in sections] == [
      "us-gaap:GoodwillDisclosureTextBlock",
      "us-gaap:DebtDisclosureTextBlock",
      "us-gaap:IncomeTaxDisclosureTextBlock",
    ]

  def test_continuation_chain_with_cycle_protection(self):
    """Ensure visited set prevents infinite loops from malformed data."""
    html = """
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:TestTextBlock" id="f-1" continuedAt="f-1-a">
      Start content with enough words to pass the minimum word count filter easily.
    </ix:nonNumeric>
    <ix:continuation id="f-1-a" continuedAt="f-1-a">
      Continuation that references itself with circular chain which should be handled gracefully.
    </ix:continuation>
    </body></html>
    """
    sections = iXBRLParser().parse(html)
    assert len(sections) == 1

  def test_resolves_multi_hop_continuation_chain(self):
    """A note that spans pages is a chain: nonNumeric → continuation →
    continuation → …, each link pointing to the next via its own
    ``continuedAt`` attribute. Every link's text and elements must land in
    the section. (3M FY2024 Note 6 once lost the PFAS exit-actions
    paragraph; Note 19 kept 570 of 129,803 characters.)
    """
    html = """
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:RestructuringAndRelatedActivitiesDisclosureTextBlock" id="f-1" continuedAt="f-1-a">
      <p>Restructuring overview with enough words to clear the minimum word count filter for a section.</p>
    </ix:nonNumeric>
    <p>Page footer text that is not part of the note.</p>
    <ix:continuation id="f-1-a" continuedAt="f-1-b">
      <p>SECOND HOP: charges of
      <ix:nonFraction name="us-gaap:RestructuringCharges" contextRef="c1">300</ix:nonFraction>
      million were recorded.</p>
    </ix:continuation>
    <ix:continuation id="f-1-b" continuedAt="f-1-c">
      <p>THIRD HOP: the reserve balance was
      <ix:nonFraction name="us-gaap:RestructuringReserve" contextRef="c2">120</ix:nonFraction>
      million.</p>
    </ix:continuation>
    <ix:continuation id="f-1-c">
      <p>FOURTH HOP: PFAS Exit Actions paragraph with
      <ix:nonFraction name="us-gaap:BusinessExitCosts1" contextRef="c3">45</ix:nonFraction>
      million.</p>
    </ix:continuation>
    </body></html>
    """
    sections = iXBRLParser().parse(html)

    assert len(sections) == 1
    s = sections[0]
    for marker in ("SECOND HOP", "THIRD HOP", "FOURTH HOP", "PFAS Exit Actions"):
      assert marker in s.content
    assert "Page footer" not in s.content
    assert s.xbrl_elements == [
      "us-gaap:BusinessExitCosts1",
      "us-gaap:RestructuringCharges",
      "us-gaap:RestructuringReserve",
    ]

  def test_chain_pointer_is_read_from_the_tag_not_the_content(self):
    """A continuation may wrap an element that itself continues elsewhere.
    That nested pointer belongs to the nested element's chain, not to the
    enclosing note: following it would splice another note's text into
    this one. The chain ends where the continuation's own tag says it ends.
    """
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:DebtDisclosureTextBlock" id="f-1" continuedAt="f-1-a">
      <p>Debt overview with enough words to clear the minimum word count filter for a section.</p>
    </ix:nonNumeric>
    <ix:continuation id="f-1-a">
      <p>Debt detail, and a nested policy that continues on its own:
      <ix:nonNumeric name="us-gaap:DebtPolicyTextBlock" contextRef="c-1" id="f-2" continuedAt="f-2-a">policy start {_FILLER}</ix:nonNumeric>
      </p>
    </ix:continuation>
    <ix:continuation id="f-2-a">
      <p>OTHER NOTE TEXT that belongs to the nested policy, not to the debt note.</p>
    </ix:continuation>
    </body></html>
    """
    sections = {s.section_id: s for s in iXBRLParser().parse(html)}

    debt = sections["us-gaap:DebtDisclosureTextBlock"]
    assert "Debt detail" in debt.content
    assert "OTHER NOTE TEXT" not in debt.content
    policy = sections["us-gaap:DebtPolicyTextBlock"]
    assert "policy start" in policy.content
    assert "OTHER NOTE TEXT" in policy.content

  def test_nested_continuation_is_registered(self):
    """A continuation physically nested inside another continuation is the
    next link of *its* chain. A map of outermost continuations only ends
    that chain after one hop: on 3M FY2024, 39 of 149 continuations are
    nested and the revenue disaggregation table resolved to its heading
    alone (163 of 1,291 characters).
    """
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:RevenueFromContractWithCustomerTextBlock" id="f-576" continuedAt="f-576-1">
      <p>REVENUE NOTE START {_FILLER}</p>
    </ix:nonNumeric>
    <ix:continuation id="f-576-1">
      <p>Disaggregated Revenue Information:</p>
      <ix:nonNumeric contextRef="c-1" name="us-gaap:DisaggregationOfRevenueTableTextBlock" id="f-577" continuedAt="f-577-1">
        <p>TABLE START {_FILLER}</p>
      </ix:nonNumeric>
      <ix:continuation id="f-577-1" continuedAt="f-577-2">
        <p>TABLE MIDDLE, nested in the note's continuation.</p>
      </ix:continuation>
      <p>NOTE TEXT AFTER THE TABLE.</p>
    </ix:continuation>
    <ix:continuation id="f-577-2">
      <p>TABLE END after the page break.</p>
    </ix:continuation>
    </body></html>
    """
    sections = {s.section_id: s for s in iXBRLParser().parse(html)}

    table = sections["us-gaap:DisaggregationOfRevenueTableTextBlock"]
    for marker in ("TABLE START", "TABLE MIDDLE", "TABLE END"):
      assert marker in table.content
    note = sections["us-gaap:RevenueFromContractWithCustomerTextBlock"]
    for marker in ("REVENUE NOTE START", "TABLE START", "NOTE TEXT AFTER THE TABLE"):
      assert marker in note.content
    assert "TABLE END" not in note.content

  def test_chain_link_inside_an_appended_link_is_not_appended_twice(self):
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:DebtDisclosureTextBlock" id="f-1" continuedAt="c-1">
      <p>START {_FILLER}</p>
    </ix:nonNumeric>
    <ix:continuation id="c-1" continuedAt="c-2">
      <p>OUTER TEXT</p>
      <ix:continuation id="c-2" continuedAt="c-3"><p>INNER TEXT</p></ix:continuation>
    </ix:continuation>
    <ix:continuation id="c-3"><p>TAIL TEXT</p></ix:continuation>
    </body></html>
    """
    (section,) = iXBRLParser().parse(html)
    assert section.content.count("OUTER TEXT") == 1
    assert section.content.count("INNER TEXT") == 1
    assert section.content.count("TAIL TEXT") == 1
    assert section.content.index("INNER TEXT") < section.content.index("TAIL TEXT")

  def test_nested_textblock_is_its_own_section(self):
    """A policy block nested inside the accounting-policies note is a
    section in its own right (its continued tail belongs to its own chain)
    and its inline text is also part of the note's."""
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:SignificantAccountingPoliciesTextBlock" id="p">
      <p>POLICIES INTRO {_FILLER}</p>
      <ix:nonNumeric contextRef="c-1" name="us-gaap:GoodwillAndIntangibleAssetsPolicyTextBlock" id="g">
        <p>GOODWILL POLICY {_FILLER}
        <ix:nonFraction name="us-gaap:Goodwill" contextRef="c1">100</ix:nonFraction></p>
      </ix:nonNumeric>
    </ix:nonNumeric>
    </body></html>
    """
    sections = {s.section_id: s for s in iXBRLParser().parse(html)}

    assert set(sections) == {
      "us-gaap:SignificantAccountingPoliciesTextBlock",
      "us-gaap:GoodwillAndIntangibleAssetsPolicyTextBlock",
    }
    note = sections["us-gaap:SignificantAccountingPoliciesTextBlock"]
    assert "POLICIES INTRO" in note.content and "GOODWILL POLICY" in note.content
    assert note.xbrl_elements == ["us-gaap:Goodwill"]
    policy = sections["us-gaap:GoodwillAndIntangibleAssetsPolicyTextBlock"]
    assert "POLICIES INTRO" not in policy.content
    assert policy.xbrl_elements == ["us-gaap:Goodwill"]

  def test_long_section_is_split_into_parts(self):
    paragraphs = "".join(
      f"<p>Paragraph {i} " + " ".join(["word"] * 60) + "</p>" for i in range(40)
    )
    html = f"""
    <html><body>
    <ix:nonNumeric contextRef="c-1" name="us-gaap:CommitmentsAndContingenciesDisclosureTextBlock" id="f-1">
      {paragraphs}
      <ix:nonFraction name="us-gaap:LossContingencyAccrualAtCarryingValue" contextRef="c1">1</ix:nonFraction>
    </ix:nonNumeric>
    </body></html>
    """
    whole = iXBRLParser(part_size=None).parse(html)
    assert len(whole) == 1

    parts = iXBRLParser(part_size=3_000).parse(html)
    assert len(parts) > 1
    assert [p.part for p in parts] == list(range(1, len(parts) + 1))
    assert {p.part_count for p in parts} == {len(parts)}
    assert {p.section_id for p in parts} == {whole[0].section_id}
    assert (
      parts[1].label == f"Commitments And Contingencies Disclosure (2/{len(parts)})"
    )
    assert " ".join(p.content for p in parts).split() == whole[0].content.split()
    assert sum(p.word_count for p in parts) == whole[0].word_count
    # the element list is the section's, carried by every part
    assert all(p.xbrl_elements == whole[0].xbrl_elements for p in parts)
    for p in parts:
      assert p.content.startswith("Paragraph")
