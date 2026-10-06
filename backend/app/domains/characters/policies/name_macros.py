"""One pass over explicitly supplied authored text. No grammar or recursive expansion."""
from dataclasses import dataclass
import re

from app.contracts.name_binding import NameBindingError, NameBindingSnapshot

_NAME = re.compile(r"\{\{[ \t\r\n]*(user|char)[ \t\r\n]*\}\}|<(USER|CHAR|BOT)>", re.I | re.ASCII)


@dataclass(frozen=True)
class RenderedText:
    text: str
    replacements: int
    protected: int
    unsupported: int

    def receipt(self) -> dict:
        return {"replacements": self.replacements, "protected": self.protected,
                "unsupported": self.unsupported}


def _segments(text: str, literal_values: tuple[str, ...] = ()):
    if not isinstance(text, str):
        raise NameBindingError("name_macro_text_invalid")
    index = 0
    size = len(text)
    while index < size:
        literal = next((value for value in literal_values if text.startswith(value, index)), None)
        if literal is not None:
            yield literal, "protected", len(_NAME.findall(literal))
            index += len(literal)
            continue
        if text[index] == "`":
            end = index
            while end < size and text[end] == "`":
                end += 1
            delimiter = text[index:end]
            close = text.find(delimiter, end)
            stop = size if close < 0 else close + len(delimiter)
            segment = text[index:stop]
            yield segment, "protected", len(_NAME.findall(segment))
            index = stop
            continue
        if text.startswith("{{", index):
            end, depth = index + 2, 1
            while end < size and depth:
                if text.startswith("{{", end):
                    depth += 1
                    end += 2
                elif text.startswith("}}", end):
                    depth -= 1
                    end += 2
                else:
                    end += 1
            segment = text[index:end]
            match = _NAME.fullmatch(segment) if depth == 0 else None
        else:
            match = _NAME.match(text, index)
            end = match.end() if match else index + 1
            segment = text[index:end]
        # An odd number of immediately preceding backslashes is an escape.
        slash, cursor = 0, index - 1
        while cursor >= 0 and text[cursor] == "\\":
            slash += 1
            cursor -= 1
        if match and slash % 2:
            yield segment, "protected", 1
        elif match:
            yield segment, (match.group(1) or match.group(2)).lower(), 1
        else:
            yield segment, "unsupported" if segment.startswith("{{") else "literal", 1
        index = end


def name_macro_review(text: str) -> dict:
    counts = {"supported": 0, "unsupported": 0, "protected": 0}
    for _segment, kind, count in _segments(text):
        if kind in {"user", "char", "bot"}:
            counts["supported"] += count
        elif kind in counts:
            counts[kind] += count
    return counts


def render_names(text: str, binding: NameBindingSnapshot, *, output: bool = False,
                 recipient_id: str | None = None, limit: int | None = None) -> RenderedText:
    """Backticks, escapes and nested expressions remain literal. Insertions are never scanned."""
    parts, replacements, protected, unsupported = [], 0, 0, 0
    # A display name may itself contain macro-like characters. Its complete
    # literal value must remain a value on later boundaries as well.
    literal_values = tuple(sorted({value for value in (
        binding.actor_display_name, binding.user_display_name
    ) if value and ("{{" in value or _NAME.search(value))}, key=len, reverse=True))
    for segment, token, count in _segments(text, literal_values):
        if token in {"user", "char", "bot"}:
            if token == "user":
                if binding.user_display_name is None:
                    raise NameBindingError("name_binding_missing")
                if output and recipient_id is not None and recipient_id != binding.user_world_character_id:
                    raise NameBindingError("name_macro_addressee_ambiguous")
                value = binding.user_display_name
            else:
                value = binding.actor_display_name
            parts.append(value)
            replacements += 1
        else:
            if token == "unsupported":
                unsupported += count
                if output:
                    raise NameBindingError("name_macro_unsupported")
            elif token == "protected":
                protected += count
            parts.append(segment)
    result = "".join(parts)
    if limit is not None and len(result) > limit:
        raise NameBindingError("name_macro_rendered_limit", rendered_chars=len(result), limit=limit)
    return RenderedText(result, replacements, protected, unsupported)


NAME_INPUT_GUIDANCE = (
    "Persona name slots refer to the bound World user and the acting character. "
    "The actual reply recipient is supplied separately; never address another "
    "character as the bound user. Do not copy unresolved name macros from history "
    "into new authored text. Preserve explicit code literals and quoted source records."
)
