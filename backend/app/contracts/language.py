"""Role-specific language instructions, not translations of canonical content."""
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
QUERY_LANGUAGE_POLICY = (
    "For Feed and Inbox write memory_query in the admitted environment.memory_search_locale "
    "(English if absent). Preserve original names, IDs, negation and source meaning. "
    "Do not change the character's speech language. Chat queries use the current question's language; "
    "Routine queries remain composed by the backend. Do not make an extra translation call."
)
RELATIONSHIP_LANGUAGE_POLICY = (
    "Write relationship_label and perception in the subject's explicitly directed language, using "
    "formal speech examples as language evidence without imitating their voice. Without such evidence, "
    "retain the existing description's language, or use the evidence's language for a new relationship. "
    "Choose keep whenever the meaning is unchanged; a UI or detector language change is not an update."
)
