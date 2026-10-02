"""Literal word groups over the unchanged projection's lexical tokens."""
import re
from app.core.search_text import normalize_search_text
from app.domains.memory.contracts.fts_recall import FtsQueryGroup, GroupedFtsQuery
from app.domains.memory.policies.lexical_terms import _lexical_terms, _is_cjk

_SPAN = re.compile(r"\w+(?:[-:./+]\w+)*", re.UNICODE)
_PARTICLE = r"(?:에서는|에서|으로|부터|까지|은|는|이|가|을|를|에|와|과|의|로|도|만)?(?!\w)"


def build_groups(text: str, *, max_groups=32) -> GroupedFtsQuery:
    if not 1 <= max_groups <= 32:
        raise ValueError("fts_group_limit_invalid")
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
        if match.end() > 1000 or len(groups) >= max_groups or len(tokens | set(terms)) > 128 or size + rendered_size + (4 if groups else 0) > 8192:
            return GroupedFtsQuery(tuple(groups), True)
        if terms:
            groups.append(FtsQueryGroup(value, terms))
            seen.add(value)
            tokens.update(terms)
            size += rendered_size + (4 if len(groups) > 1 else 0)
    return GroupedFtsQuery(tuple(groups))


def build_image_groups(base: str, hint: str) -> GroupedFtsQuery:
    base_all, hint_all = build_groups(base), build_groups(hint)
    # Unused groups are shared while each side keeps its reserved initial budget.
    first_limit = min(32, 24 + max(0, 8 - len(hint_all.groups)))
    second_limit = min(32, 8 + max(0, 24 - len(base_all.groups)))
    first, second = build_groups(base, max_groups=first_limit), build_groups(hint, max_groups=second_limit)
    groups, tokens, size, seen = [], set(), 0, set()
    truncated = first.truncated or second.truncated
    for group in (*first.groups, *second.groups):
        if group.text in seen:
            continue
        rendered = len(('(' + ' AND '.join('"' + t.replace('"', '""') + '"' for t in group.tokens) + ')').encode())
        if len(tokens | set(group.tokens)) > 128 or size + rendered + (4 if groups else 0) > 8192:
            truncated = True
            break
        groups.append(group); seen.add(group.text); tokens.update(group.tokens)
        size += rendered + (4 if len(groups) > 1 else 0)
    return GroupedFtsQuery(tuple(groups), truncated)


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
