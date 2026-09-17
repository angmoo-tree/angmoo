"""Literal word groups over the unchanged projection's lexical tokens."""
import re
from app.core.search_text import normalize_search_text
from app.domains.memory.contracts.fts_recall import FtsQueryGroup, GroupedFtsQuery
from app.domains.memory.policies.lexical_terms import _lexical_terms, _is_cjk

_SPAN = re.compile(r"\w+(?:[-:./+]\w+)*", re.UNICODE)
_PARTICLE = r"(?:에서는|에서|으로|부터|까지|은|는|이|가|을|를|에|와|과|의|로|도|만)?(?!\w)"


def build_groups(text: str) -> GroupedFtsQuery:
    normalized = normalize_search_text(text, max_chars=4000)
    groups, seen, tokens = [], set(), set()
    size = 0
    for match in _SPAN.finditer(normalized):
        value = match.group()
        if value in seen:
            continue
        terms = _lexical_terms(value, query_mode=True)
        # Account for escaped literals, internal AND, outer parentheses and OR.
        rendered_size = len(('(' + ' AND '.join('"' + t.replace('"', '""') + '"' for t in terms) + ')').encode())
        if match.end() > 1000 or len(groups) >= 32 or len(tokens | set(terms)) > 128 or size + rendered_size + (4 if groups else 0) > 8192:
            return GroupedFtsQuery(tuple(groups), True)
        if terms:
            groups.append(FtsQueryGroup(value, terms))
            seen.add(value)
            tokens.update(terms)
            size += rendered_size + (4 if len(groups) > 1 else 0)
    return GroupedFtsQuery(tuple(groups))


def match_groups(groups: tuple[FtsQueryGroup, ...], document: str) -> tuple[int, ...]:
    matched = []
    for index, group in enumerate(groups):
        value = group.text
        if len(value) >= 2 and all(_is_cjk(c) for c in value):
            hit = value in document
        elif len(value) == 1 and _is_cjk(value):
            hit = re.search(r'(?<!\w)' + re.escape(value) + _PARTICLE, document) is not None
        else:
            # Numeric runs and structured identifiers cannot match substrings.
            left = r'(?<![\w.:/+\-])' if not value[0].isdigit() else r'(?<![0-9A-Za-z_.:/+\-])'
            right = r'(?![0-9A-Za-z_.:/+\-])'
            if _is_cjk(value[-1]):
                right = ''
            hit = re.search(left + re.escape(value) + right, document) is not None
        if hit:
            matched.append(index)
    return tuple(matched)
