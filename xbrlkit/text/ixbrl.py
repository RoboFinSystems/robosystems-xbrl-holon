"""iXBRL disclosure parser — the filing's text blocks as sections, with the
XBRL elements each one contains.

An inline-XBRL document tags its notes and policies as ``ix:nonNumeric``
facts whose element names end in ``TextBlock``. Those tags *are* the
disclosure sections: they wrap the narrative and contain the nested
``ix:nonFraction`` numeric facts. Extracting the text and the element names
together lets a search hit lead to the graph fact and a graph fact lead to
its filing context.

A note that spans a page break is a chain, and each link's pointer to the
next is an attribute on its own tag::

  <ix:nonNumeric name="us-gaap:GoodwillDisclosureTextBlock" continuedAt="f-571-1">
    Goodwill
  </ix:nonNumeric>
  <ix:continuation id="f-571-1" continuedAt="f-571-2">
    <p>The following table summarizes changes in goodwill...</p>
    <ix:nonFraction name="us-gaap:Goodwill">32,431</ix:nonFraction>
  </ix:continuation>
  <ix:continuation id="f-571-2">
    <p>...and the rest of the note after the page break.</p>
  </ix:continuation>

Continuations nest: a table text block inside a revenue note continues in a
``ix:continuation`` that sits physically inside the note's own continuation.
Every continuation is registered with its offsets, nested or not, and a chain
appends a link only when no appended link already contains it.

A concept tagged more than once — a purchase-price table per acquisition, a
roll-forward per period — is one section holding every distinct occurrence
in document order; keeping the first alone lost the second table. Content
inside ``ix:exclude`` (the page header some filers place inside a tagged
block) is not part of the fact and is dropped, as Arelle drops it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .parts import DEFAULT_PART_SIZE, part_label, split_text
from .tables import html_tables_to_markdown

logger = logging.getLogger(__name__)


@dataclass
class iXBRLSection:  # noqa: N801 — the established name across consumers
  """A disclosure section extracted from iXBRL, or one part of a long one."""

  section_id: str  # the element qname, e.g. "us-gaap:GoodwillDisclosureTextBlock"
  section_label: str  # e.g. "Goodwill Disclosure"
  content: str  # plain text, tables as markdown
  word_count: int  # of this part
  xbrl_elements: list[str]  # element qnames in the whole section, sorted
  element_count: int
  part: int = 1  # 1-based
  part_count: int = 1

  @property
  def label(self) -> str:
    """The label with the part suffix when the section was split: "MD&A (2/6)"."""
    return part_label(self.section_label, self.part, self.part_count)


# Minimum word count to keep a section (skip trivial/empty blocks)
MIN_SECTION_WORDS = 20


def _label_from_element_name(name: str) -> str:
  """Derive a readable label from an XBRL element qname.

  Examples:
    'us-gaap:GoodwillDisclosureTextBlock' → 'Goodwill Disclosure'
    'us-gaap:RevenueFromContractWithCustomerPolicyTextBlock' → 'Revenue From Contract With Customer Policy'
  """
  local = name.split(":")[-1] if ":" in name else name

  for suffix in ["TextBlock", "TableTextBlock"]:
    if local.endswith(suffix):
      local = local[: -len(suffix)]

  label = re.sub(r"([a-z])([A-Z])", r"\1 \2", local)
  label = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", label)

  return label.strip()


def _strip_html(html: str) -> str:
  """Strip HTML tags and normalize whitespace.

  Tables are converted to markdown pipe tables before tag stripping,
  preserving column structure for financial data. Block-level tags are
  replaced with newlines to maintain paragraph structure.
  """
  if "<table" in html or "<TABLE" in html:
    html = html_tables_to_markdown(html)
  text = re.sub(
    r"<style[^>]*>.*?</\s*style\b[^>]*>", " ", html, flags=re.DOTALL | re.IGNORECASE
  )
  text = re.sub(
    r"<script[^>]*>.*?</\s*script\b[^>]*>", " ", text, flags=re.DOTALL | re.IGNORECASE
  )
  # Replace block-level tags with newlines to preserve paragraph structure
  text = re.sub(
    r"</?(?:p|div|br|tr|li|h[1-6]|ul|ol|blockquote)[^>]*>",
    "\n",
    text,
    flags=re.IGNORECASE,
  )
  # Replace remaining inline tags with spaces
  text = re.sub(r"<[^>]+>", " ", text)
  text = re.sub(r"&nbsp;?", " ", text)
  text = re.sub(r"&amp;?", "&", text)
  text = re.sub(r"&#\d+;", " ", text)
  # Collapse horizontal whitespace only (preserve newlines for tables/paragraphs)
  text = re.sub(r"[^\S\n]+", " ", text)
  # Collapse multiple blank lines
  text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
  return text.strip()


def _extract_elements_from_block(html_block: str) -> list[str]:
  """Extract unique XBRL element qnames from ix:nonFraction tags in a block."""
  elements = set()
  for match in re.finditer(
    r"<ix:nonFraction[^>]*name=\"([^\"]+)\"", html_block, re.IGNORECASE
  ):
    elements.add(match.group(1))
  # Also capture ix:nonNumeric elements nested inside (sub-blocks)
  for match in re.finditer(
    r"<ix:nonNumeric[^>]*name=\"([^\"]+)\"", html_block, re.IGNORECASE
  ):
    name = match.group(1)
    # Skip the parent text block itself and DEI metadata
    if not name.endswith("TextBlock") and not name.startswith("dei:"):
      elements.add(name)
  return sorted(elements)


@dataclass(frozen=True)
class _Block:
  """One ``<tag …>…</tag>`` occurrence: its attributes and content offsets."""

  attrs: str
  start: int  # offset of the first content character
  end: int  # offset of the closing tag
  depth: int  # 0 for an outermost block of its tag

  def content(self, html: str) -> str:
    return html[self.start : self.end]

  def contains(self, other: _Block) -> bool:
    return self.start <= other.start and other.end <= self.end


_TAG_NAME_END = " \t\r\n/>"

# Content a filer marks as not part of the fact: page headers and footers
# inside a tagged block. Applied to one section's HTML, never the document.
_EXCLUDE_RE = re.compile(
  r"<ix:exclude\b[^>]*>.*?</ix:exclude\s*>", re.IGNORECASE | re.DOTALL
)


def _scan_blocks(html: str, tag: str) -> list[_Block]:
  """Every ``<tag>`` block in document order, nested blocks included.

  Uses ``str.find`` rather than a lazy regex (``.*?``), which allocates
  catastrophically on large files — multiple GB on a 5 MB input. ``tag`` is
  matched case-insensitively (``ix:nonNumeric`` and ``ix:nonnumeric`` both
  occur in the wild). Unmatched tags are dropped.
  """
  open_tag = f"<{tag.lower()}"
  close_tag = f"</{tag.lower()}"
  html_lower = html.lower()

  blocks: list[_Block] = []
  stack: list[tuple[str, int]] = []
  pos = 0
  while True:
    next_open = html_lower.find(open_tag, pos)
    next_close = html_lower.find(close_tag, pos)
    if next_open == -1 and next_close == -1:
      break

    if next_open != -1 and (next_close == -1 or next_open < next_close):
      after = next_open + len(open_tag)
      if after < len(html_lower) and html_lower[after] not in _TAG_NAME_END:
        pos = after  # a longer tag name that merely starts with ours
        continue
      tag_end = html.find(">", next_open)
      if tag_end == -1:
        break
      attrs = html[after:tag_end]
      pos = tag_end + 1
      if attrs.rstrip().endswith("/"):
        continue  # self-closing: no content, nothing to register
      stack.append((attrs, pos))
    else:
      if stack:
        attrs, content_start = stack.pop()
        blocks.append(_Block(attrs, content_start, next_close, len(stack)))
      close_end = html.find(">", next_close)
      pos = close_end + 1 if close_end != -1 else next_close + len(close_tag)

  blocks.sort(key=lambda b: b.start)
  return blocks


def _continued_at(attrs: str) -> str | None:
  m = re.search(r'continuedAt="([^"]+)"', attrs)
  return m.group(1) if m else None


class iXBRLParser:  # noqa: N801 — the established name across consumers
  """Parse iXBRL HTML into disclosure sections with XBRL element metadata.

  ``part_size`` is the target length of one part in characters; a section
  longer than that is split at paragraph boundaries into balanced parts
  (see :func:`xbrlkit.text.parts.split_text`). ``None`` keeps every section
  whole.
  """

  def __init__(self, part_size: int | None = DEFAULT_PART_SIZE) -> None:
    self.part_size = part_size

  def parse(self, html: str) -> list[iXBRLSection]:
    """Parse an iXBRL document into disclosure sections.

    Every ``ix:nonNumeric`` TextBlock becomes a section, its
    ``ix:continuation`` chain resolved, its numeric facts listed — nested
    ones included: a policy block inside an accounting-policies note is its
    own section as well as part of the note's text, because its continued
    tail belongs to its own chain and to no other. A concept tagged more
    than once is one section holding every distinct occurrence in document
    order (the same table tagged twice with different markup counts once);
    ``ix:exclude`` content is dropped. A section over ``part_size`` is
    returned as consecutive parts that share the ``section_id`` and carry
    ``part``/``part_count``.
    """
    continuations = self._build_continuation_map(html)

    # Per element name, in document order: each distinct occurrence's HTML
    # and text, the blocks already taken, and the texts already seen.
    htmls: dict[str, list[str]] = {}
    texts: dict[str, list[str]] = {}
    taken: dict[str, list[_Block]] = {}
    seen: dict[str, set[str]] = {}

    for block in _scan_blocks(html, "ix:nonNumeric"):
      name_match = re.search(
        r'name="([^"]*TextBlock[^"]*)"', block.attrs, re.IGNORECASE
      )
      if not name_match:
        continue
      element_name = name_match.group(1)

      # Skip DEI and ECD metadata text blocks
      if element_name.startswith(("dei:", "ecd:")):
        continue

      # A block nested in an earlier block of the same name is already in it
      if any(outer.contains(block) for outer in taken.get(element_name, ())):
        continue

      full_html = block.content(html)
      continued_at = _continued_at(block.attrs)
      if continued_at:
        full_html += self._resolve_continuation_chain(
          continued_at, continuations, html, covered=[block]
        )
      full_html = _EXCLUDE_RE.sub(" ", full_html)
      content = _strip_html(full_html)

      key = " ".join(content.split())
      if key in seen.setdefault(element_name, set()):
        continue
      seen[element_name].add(key)
      taken.setdefault(element_name, []).append(block)
      htmls.setdefault(element_name, []).append(full_html)
      texts.setdefault(element_name, []).append(content)

    sections: list[iXBRLSection] = []
    for element_name, occurrences in texts.items():
      content = "\n\n".join(occurrences)
      word_count = len(content.split())
      if word_count < MIN_SECTION_WORDS:
        continue

      xbrl_elements = _extract_elements_from_block("".join(htmls[element_name]))
      section_label = _label_from_element_name(element_name)
      parts = split_text(content, self.part_size)
      for index, part_text in enumerate(parts, start=1):
        sections.append(
          iXBRLSection(
            section_id=element_name,
            section_label=section_label,
            content=part_text,
            word_count=len(part_text.split()),
            xbrl_elements=xbrl_elements,
            element_count=len(xbrl_elements),
            part=index,
            part_count=len(parts),
          )
        )

    logger.debug(
      "iXBRL parsed: %d disclosure documents (%d sections), %d elements",
      len(sections),
      len(texts),
      sum(s.element_count for s in sections if s.part == 1),
    )
    return sections

  def _build_continuation_map(self, html: str) -> dict[str, _Block]:
    """Continuation id → block, for every ``ix:continuation`` in the document.

    Nested continuations are registered too: a continuation that sits inside
    another one (the tail of a table text block inside a note's own tail)
    is the next link of *its* chain, and a map of outermost blocks alone
    ends that chain after one hop.
    """
    continuations: dict[str, _Block] = {}
    for block in _scan_blocks(html, "ix:continuation"):
      id_match = re.search(r'\bid="([^"]+)"', block.attrs)
      if id_match:
        continuations.setdefault(id_match.group(1), block)
    return continuations

  def _resolve_continuation_chain(
    self,
    start_id: str,
    continuations: dict[str, _Block],
    html: str,
    covered: list[_Block] | None = None,
  ) -> str:
    """Follow ``continuedAt`` pointers from ``start_id`` and return the text.

    Each hop's pointer is read from the continuation's own tag attributes,
    never from its content: a pointer found inside the content belongs to
    an element nested there and would splice a different note's text into
    this one. A link already inside an appended link is followed but not
    appended again. ``covered`` seeds the appended ranges (the section's own
    block) and is extended in place.
    """
    fragments: list[str] = []
    appended: list[_Block] = list(covered or [])
    current_id: str | None = start_id
    visited: set[str] = set()

    while current_id and current_id not in visited:
      visited.add(current_id)
      block = continuations.get(current_id)
      if block is None:
        break
      if not any(parent.contains(block) for parent in appended):
        fragments.append(block.content(html))
        appended.append(block)
      current_id = _continued_at(block.attrs)

    if covered is not None:
      covered[:] = appended
    return "".join(fragments)
