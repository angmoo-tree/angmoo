"""Literal word groups over the unchanged projection's lexical tokens."""
import re
from app.core.search_text import normalize_search_text, word_spans, literal_boundary
from app.domains.memory.contracts.fts_recall import FtsQueryGroup, GroupedFtsQuery
from app.domains.memory.policies.lexical_terms import _lexical_terms, _is_cjk

_SPAN = re.compile(r"\w+(?:[-:./+]\w+)*", re.UNICODE)
_PARTICLE = r"(?:에서는|에서|으로|부터|까지|은|는|이|가|을|를|에|와|과|의|로|도|만)?(?!\w)"


def strict_literal_groups(normalized: str) -> tuple[FtsQueryGroup, ...]:
    """Exact non-CJK atoms for legacy AND queries; keep CJK spacing policy.

    FTS splits ID punctuation. Postchecks must use the original structured atom
    rather than treating a digit prefix as a match of a different identifier.
    The caller has already bounded normalized input to 1,000 characters.
    """
    return tuple(FtsQueryGroup(value, ()) for _, _, value in word_spans(normalized, structured=True)
                 if not any(_is_cjk(character) for character in value))


def build_groups(text: str, *, max_groups=32) -> GroupedFtsQuery:
    if not 1 <= max_groups <= 32:
        raise ValueError("fts_group_limit_invalid")
    normalized = normalize_search_text(text, max_chars=4000)
    groups, seen, tokens = [], set(), set()
    size = 0
    for start, end, value in word_spans(normalized, structured=True):
        if value in seen:
            continue
        terms = _lexical_terms(value, query_mode=True)
        # Account for escaped literals, internal AND, outer parentheses and OR.
        rendered_size = len(('(' + ' AND '.join('"' + t.replace('"', '""') + '"' for t in terms) + ')').encode())
        if end > 1000 or len(groups) >= max_groups or len(tokens | set(terms)) > 128 or size + rendered_size + (4 if groups else 0) > 8192:
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
        elif value.isdecimal():
            # Preserve bounded Korean day/count units without partial ID hits.
            hit = re.search(r'(?<!\w)' + re.escape(value) + r'(?:년|월|일|시|분|초|개|명|회)' + _PARTICLE, document) is not None
            hit = hit or any(literal_boundary(document, match.start(), match.end())
                for match in re.finditer(re.escape(value), document))
        else:
            # Numeric runs and structured identifiers cannot match substrings.
            hit = any(literal_boundary(document, match.start(), match.end())
                for match in re.finditer(re.escape(value), document))
        if hit:
            matched.append(index)
    return tuple(matched)
