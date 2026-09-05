"""Tests for section splitting (``xbrlkit.text.parts``)."""

import math

import pytest

from xbrlkit.text.parts import DEFAULT_PART_SIZE, part_label, split_text


def _paragraphs(count: int, words: int = 40) -> str:
  return "\n\n".join(" ".join(f"p{i}w{j}" for j in range(words)) for i in range(count))


@pytest.mark.unit
class TestSplitText:
  def test_short_text_is_one_part(self):
    text = _paragraphs(3)
    assert split_text(text, 10_000) == [text]

  def test_none_disables_splitting(self):
    text = _paragraphs(200)
    assert split_text(text, None) == [text]

  def test_part_count_is_ceil_of_length_over_size(self):
    text = _paragraphs(30)
    parts = split_text(text, 2_000)
    assert len(parts) == math.ceil(len(text) / 2_000)

  def test_parts_are_balanced_and_cut_at_paragraphs(self):
    text = _paragraphs(30)
    parts = split_text(text, 2_000)
    ideal = len(text) / len(parts)
    for part in parts:
      # every part starts on a paragraph's first word and ends on its last
      assert part.startswith("p") and part.split()[0].endswith("w0")
      assert part.split()[-1].endswith("w39")
      assert abs(len(part) - ideal) < ideal * 0.3

  def test_nothing_is_lost(self):
    text = _paragraphs(50)
    parts = split_text(text, 3_000)
    assert " ".join(parts).split() == text.split()

  def test_falls_back_to_line_breaks(self):
    text = "\n".join(" ".join(f"l{i}w{j}" for j in range(30)) for i in range(20))
    parts = split_text(text, 1_500)
    assert len(parts) > 1
    for part in parts:
      assert part.split()[0].endswith("w0")
    assert " ".join(parts).split() == text.split()

  def test_falls_back_to_sentences_then_hard_cut(self):
    sentences = " ".join(f"Sentence number {i} ends here." for i in range(200))
    parts = split_text(sentences, 1_000)
    assert len(parts) > 1
    for part in parts[:-1]:
      assert part.endswith(".")
    assert " ".join(parts).split() == sentences.split()

    unbroken = "x" * 5_000
    parts = split_text(unbroken, 2_000)
    assert len(parts) == 3
    assert "".join(parts) == unbroken

  def test_default_size(self):
    assert DEFAULT_PART_SIZE == 25_000


@pytest.mark.unit
def test_part_label():
  assert part_label("MD&A", 1, 1) == "MD&A"
  assert part_label("MD&A", 2, 6) == "MD&A (2/6)"
