"""Exact codepoint spans for bounded excerpts and permitted name rendering."""
from difflib import SequenceMatcher


def delivered_ranges(original: str, delivered: str):
    offset = original.find(delivered)
    if offset >= 0:
        return ((offset, offset + len(delivered)),), ((0, len(delivered)),)
    # Inputs already obey their owner budgets. Auto-junk prevents pathological
    # repeated text from turning provenance assembly into quadratic matching.
    # Unmatched inserted delimiters/names never authorize original hydration.
    blocks = SequenceMatcher(None, original, delivered, autojunk=True).get_matching_blocks()
    blocks = [block for block in blocks if block.size >= 8]
    return (tuple((block.a, block.a + block.size) for block in blocks),
        tuple((block.b, block.b + block.size) for block in blocks))
