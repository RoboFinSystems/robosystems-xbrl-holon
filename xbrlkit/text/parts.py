"""Split a long section into parts at paragraph boundaries.

A filing section — an MD&A, a risk-factors item, a commitments note — is
often 100K+ characters. A search document that long is matched by an average
of itself, and a hard cap loses the tail: 3M's FY2024 commitments note is
129,645 characters, of which a 50,000-character cap keeps 39%. Parts keep
every character and give each a document of a size a retriever can rank.

Parts are balanced rather than greedy: the part count is fixed up front from
the target size, and every cut lands on the paragraph break nearest its ideal
position, so a 130K section becomes six ~22K parts instead of five 25K parts
and a 5K tail.
"""

from __future__ import annotations

import math
import re

# Target size of one part, in characters. Chosen so a part is a few pages of
# a filing; a retriever's embedding window (~2,000 chars) sees a meaningful
# fraction of each part, and a section of ordinary length stays one part.
DEFAULT_PART_SIZE = 25_000

# How far from the ideal boundary a cut may move to land on a break, as a
# fraction of the ideal part length.
_WINDOW = 0.25

_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_LINE_RE = re.compile(r"\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s")


def split_text(text: str, part_size: int | None = DEFAULT_PART_SIZE) -> list[str]:
  """Split ``text`` into roughly equal parts of about ``part_size`` characters.

  Returns ``[text]`` when it fits or when ``part_size`` is ``None``. Otherwise
  the part count is ``ceil(len(text) / part_size)`` and each cut is placed at
  the paragraph break nearest the ideal boundary, within a window of a quarter
  of a part; failing that, the nearest line break, then sentence end, then a
  hard cut. Parts are stripped of surrounding whitespace; nothing else is
  lost, so the parts joined with whitespace carry every word of the input.
  """
  if part_size is None or part_size <= 0 or len(text) <= part_size:
    return [text]

  count = math.ceil(len(text) / part_size)
  ideal = len(text) / count
  window = int(ideal * _WINDOW)

  parts: list[str] = []
  start = 0
  for i in range(1, count):
    target = round(i * ideal)
    lo = max(start + 1, target - window)
    hi = min(len(text) - 1, target + window)
    cut = _best_cut(text, lo, hi, target)
    parts.append(text[start:cut].strip())
    start = cut
  parts.append(text[start:].strip())

  return [part for part in parts if part]


def _best_cut(text: str, lo: int, hi: int, target: int) -> int:
  """The cut position in ``[lo, hi]`` nearest ``target``, preferring a
  paragraph break, then a line break, then a sentence end, else ``target``.
  The cut sits after the break, so the next part starts on its first word."""
  if hi <= lo:
    return target
  for pattern in (_PARAGRAPH_RE, _LINE_RE, _SENTENCE_RE):
    best: int | None = None
    for m in pattern.finditer(text, lo, hi):
      if best is None or abs(m.end() - target) < abs(best - target):
        best = m.end()
    if best is not None:
      return best
  return target


def part_label(label: str, part: int, part_count: int) -> str:
  """``"MD&A (2/6)"`` for a part of a split section; the label alone otherwise."""
  if part_count <= 1:
    return label
  return f"{label} ({part}/{part_count})"
