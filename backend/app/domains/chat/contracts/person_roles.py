"""One immutable meaning definition for Supervisor and CRG person roles."""
PERSON_ROLE_MEANINGS = (
    ("subject", "The person the question is mainly about."),
    ("actor", "The person performing the action referred to in the question."),
    ("target", "The person the action is directed at."),
    ("counterpart", "The other participant in the interaction referred to in the question."),
    ("mentioned_third_party", "A person mentioned in context who is not a main subject or participant in the action being asked about."),
)
PERSON_ROLES = frozenset(role for role, _ in PERSON_ROLE_MEANINGS)


def person_role_description():
    return "Person roles: " + " ".join(f"{role}: {meaning}" for role, meaning in PERSON_ROLE_MEANINGS)
