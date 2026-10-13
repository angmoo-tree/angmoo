"""Bounded advisory interpretation; never a person lookup or authority grant."""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import unicodedata

from app.domains.chat.contracts.person_roles import PERSON_ROLES

PERSON_HINT_REVISION = "person-hints.v1"
MAX_REVIEWED_HINTS = 32
MAX_DELIVERED_HINTS = 4
MAX_HINT_NAME = 160


@dataclass(frozen=True, slots=True)
class PersonHint:
    mention: str
    role: str | None = None
    status: str = "not_checked"

    def __post_init__(self):
        if (type(self.mention) is not str or not self.mention or self.mention != self.mention.strip()
            or len(self.mention) > MAX_HINT_NAME
            or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in self.mention)
            or self.role is not None and (type(self.role) is not str or self.role not in PERSON_ROLES)
            or type(self.status) is not str or self.status not in {"confirmed", "ambiguous", "not_checked"}):
            raise ValueError("person_hint_invalid")

    def payload(self):
        return {"mention": self.mention, "role": self.role, "status": self.status}


@dataclass(frozen=True, slots=True)
class PersonHints:
    hints: tuple[PersonHint, ...]
    state: str
    reviewed: int
    excluded: int
    input_digest: str
    revision: str = PERSON_HINT_REVISION

    def __post_init__(self):
        if (type(self.hints) is not tuple or len(self.hints) > MAX_DELIVERED_HINTS
            or any(not isinstance(row, PersonHint) for row in self.hints)
            or type(self.state) is not str or self.state not in {"absent", "usable", "partial", "ignored"}
            or type(self.reviewed) is not int or not 0 <= self.reviewed <= MAX_REVIEWED_HINTS
            or type(self.excluded) is not int or self.excluded < 0
            or self.revision != PERSON_HINT_REVISION
            or type(self.input_digest) is not str or len(self.input_digest) != 64
            or any(c not in "0123456789abcdef" for c in self.input_digest)):
            raise ValueError("person_hints_invalid")

    def payload(self):
        return {"revision": self.revision, "hints": [row.payload() for row in self.hints],
            "state": self.state, "reviewed": self.reviewed, "excluded": self.excluded,
            "input_digest": self.input_digest}

    def confirm_participants(self, identity):
        # Frozen Chat identity currently supplies names, not handles. Compare
        # only supplied participant values; do not invent aliases or read SQL.
        participants = () if identity is None else (identity.requester, identity.responder)
        return replace(self, hints=tuple(replace(row, status=(
            "confirmed" if count == 1 else "ambiguous" if count > 1 else "not_checked"))
            for row in self.hints for count in [sum(p.name == row.mention for p in participants)]))


def normalize_person_hints(value=None):
    reviewed = value[:MAX_REVIEWED_HINTS] if type(value) is list else []
    # The provider's existing bounded JSON transport owns total response size.
    # Review/fingerprint at most 32 entries; never copy an unbounded list.
    material = {"kind": type(value).__name__, "count": len(value) if type(value) is list else None,
        "reviewed": reviewed}
    digest = sha256(json.dumps(material, ensure_ascii=True, sort_keys=True,
        default=lambda item: type(item).__name__).encode()).hexdigest()
    if type(value) is not list:
        return PersonHints((), "absent" if value is None else "ignored", 0, 0, digest)
    names, excluded, altered = {}, max(0, len(value) - MAX_REVIEWED_HINTS), False
    for item in reviewed:
        name = item.get("mention") if type(item) is dict else None
        if (type(name) is not str or not name.strip() or len(name) > MAX_HINT_NAME
            or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in name)):
            excluded += 1
            continue
        name = name.strip()
        raw_role = item.get("role")
        role = raw_role if type(raw_role) is str and raw_role in PERSON_ROLES else None
        altered |= role is None or bool(set(item) - {"mention", "role"})
        if name in names:
            excluded += 1
            if names[name].role is None and role is not None:
                names[name] = replace(names[name], role=role)
        elif len(names) < MAX_DELIVERED_HINTS:
            names[name] = PersonHint(name, role)
        else:
            excluded += 1
    state = "absent" if not value else "ignored" if not names else "partial" if excluded or altered else "usable"
    return PersonHints(tuple(names.values()), state, len(reviewed), excluded, digest)
