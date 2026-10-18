"""Role-specific language instructions, not translations of canonical content."""
from collections.abc import Mapping

from app.contracts.environment import EnvironmentSnapshot, validate_memory_search_locale


PERSONA_LANGUAGE_POLICY = (
    "Use the character's explicit language directives, formal speech examples and current context. "
    "The language used to describe a character alone is not a speech directive. "
    "When no language evidence is supplied, write in English. UI language and memory-search locale "
    "are not substitutes for the character's speaking language. A temporary Chat language request "
    "applies to that response only; it does not change the saved persona or autonomous posts. "
    "Preserve original names, quoted expressions, IDs, dates, negation and corrections."
)
MEMORY_LANGUAGE_POLICY = (
    "Write new episode summaries in environment.memory_search_locale (BCP47; English if absent). "
    "Preserve exact original names, identifiers and meaningful quotations from every source. "
    "This policy applies to new summaries only; never translate or regenerate prior memories."
)
_QUERY_LANGUAGE_RULES = (
    "Preserve original names, IDs, negation and source meaning. "
    "Do not change the character's speech language. Chat queries use the current question's language; "
    "Routine queries remain composed by the backend. Do not make an extra translation call."
)
QUERY_LANGUAGE_POLICY = (
    "For Feed and Inbox write memory_query in the admitted environment.memory_search_locale "
    "(English if absent). " + _QUERY_LANGUAGE_RULES
)
RELATIONSHIP_LANGUAGE_POLICY = (
    "Write relationship_label and perception in the subject's explicitly directed language, using "
    "formal speech examples as language evidence without imitating their voice. Without such evidence, "
    "retain the existing description's language, or use the evidence's language for a new relationship. "
    "Choose keep whenever the meaning is unchanged; a UI or detector language change is not an update."
)


PREPARATION_LANGUAGE_POLICY = "preparation-output-language.v1"


def generation_language_name(locale: str) -> str:
    """Name supported base languages; retain every other valid full tag."""
    locale = validate_memory_search_locale(locale)
    return {"ko": "Korean", "en": "English"}.get(locale.split("-")[0].lower(), locale)


def sns_query_language_instruction(locale: str) -> str:
    """Apply the admitted language only to AI-generated Feed/Inbox queries."""
    return (
        f"For Feed and Inbox write memory_query in {generation_language_name(locale)}. "
        "This names the language to write in, not text to use as the query. "
        + _QUERY_LANGUAGE_RULES
    )


class PreparationLanguageError(ValueError):
    """An admitted preparation language contract cannot be recovered safely."""


def preparation_environment(snapshot: Mapping | None) -> EnvironmentSnapshot | None:
    """Read new admitted inputs strictly; unmarked historical work keeps its policy."""
    if snapshot is None or "preparation_language_policy" not in snapshot:
        return None
    environment = snapshot.get("environment")
    if (snapshot["preparation_language_policy"] != PREPARATION_LANGUAGE_POLICY
            or not isinstance(environment, dict)
            or set(environment) != set(EnvironmentSnapshot.__dataclass_fields__)):
        raise PreparationLanguageError("preparation_language_snapshot_invalid")
    try:
        return EnvironmentSnapshot.from_dict(environment)
    except (TypeError, ValueError):
        raise PreparationLanguageError("preparation_language_snapshot_invalid") from None


def preparation_language_instruction(snapshot: Mapping, *, fields: tuple[str, ...]) -> str:
    """Name the output language without translating stored locale or persona."""
    environment = preparation_environment(snapshot)
    if environment is None:
        return ""  # Never retrofit the new policy onto an already accepted request.
    language = generation_language_name(environment.memory_search_locale)
    return (
        f"Write newly generated {', '.join(fields)} in {language}. "
        "This is the language of the planning text, not text to use as a title or topic name. "
        "It does not change the character's speaking language. "
        "Keep JSON keys, enum values, IDs, dates, times, place keys, proper names and meaningful quotations unchanged. "
        "Do not rewrite preserved activities or existing content."
    )
