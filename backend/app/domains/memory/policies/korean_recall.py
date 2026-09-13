"""Conservative spacing-only matching; no concept dropping or synonyms."""
import re

_HANGUL = re.compile(r"[가-힣]{4,}")
_HANGUL_WORD = re.compile(r"[가-힣]+")
# Permit a closed set of trailing particles at the original word boundary.
# This is not stemming: the query group itself is never shortened.
_PARTICLE_END = r"(?=(?:에서는|에서|으로|부터|까지|은|는|이|가|을|를|에|와|과|의|로|도|만)?(?!\w))"


def spacing_groups(normalized_query: str) -> tuple[str, ...]:
    groups = tuple(dict.fromkeys(normalized_query.split()))
    # One broad term cannot disambiguate a spacing collision.
    if (not 2 <= len(groups) <= 12 or any(len(group) > 64 for group in groups)
            or not any(_HANGUL.fullmatch(group) for group in groups)):
        return ()
    return groups


def spacing_matches(groups: tuple[str, ...], normalized_document: str) -> bool:
    """Keep every query group; only join spaces *within* a Hangul group.

    A newly joined match must begin/end at an existing word boundary. Thus
    '아버지가' cannot end inside '가방에'. Punctuation, numbers, Latin words
    and field separators are not joined. Unchanged groups retain substring
    matching, as in the strict fallback.
    """
    changed = False
    for group in groups:
        if re.search(r"(?<![\w.])" + re.escape(group) + r"(?![\w.])", normalized_document):
            continue
        if _HANGUL_WORD.fullmatch(group):
            if group in normalized_document:
                continue
            pattern = r"(?<!\w)" + " *".join(map(re.escape, group)) + _PARTICLE_END
            if re.search(pattern, normalized_document):
                changed = True
                continue
        return False
    return changed
