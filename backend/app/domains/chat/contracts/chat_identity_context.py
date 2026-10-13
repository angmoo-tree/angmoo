"""Request-frozen Chat presentation identities, separate from name-binding.v1."""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json
import unicodedata

from app.contracts.name_binding import NameBindingError, NameBindingSnapshot

IDENTITY_KEY = "chat_identity_context.v1"


def presentation_name(value: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 80:
        raise NameBindingError("chat_identity_name_invalid")
    # Controls cannot introduce another speaker line. Unicode letters and emoji,
    # including their joiners, remain ordinary JSON data.
    result = "".join(c for c in value if unicodedata.category(c) not in {"Cc", "Cs", "Zl", "Zp"}).strip()
    if not result:
        raise NameBindingError("chat_identity_name_invalid")
    return result


@dataclass(frozen=True, slots=True)
class ChatPerson:
    identifier: str
    name: str

    def __post_init__(self):
        if type(self.identifier) is not str or not self.identifier or len(self.identifier) > 128:
            raise NameBindingError("chat_identity_invalid")
        if self.name != presentation_name(self.name):
            raise NameBindingError("chat_identity_name_invalid")


@dataclass(frozen=True, slots=True)
class ChatIdentityContext:
    owner_id: str
    world_id: str
    thread_id: str
    requester: ChatPerson
    responder: ChatPerson
    people: tuple[ChatPerson, ...] = ()
    revision: str = IDENTITY_KEY

    def __post_init__(self):
        if self.revision != IDENTITY_KEY or any(type(v) is not str or not v for v in
                (self.owner_id, self.world_id, self.thread_id)) or any(len(v) > 128 for v in (self.owner_id, self.world_id, self.thread_id)):
            raise NameBindingError("chat_identity_invalid")
        ids = [self.requester.identifier, self.responder.identifier, *(p.identifier for p in self.people)]
        # Router-selected Today authors and final selected memory authors can be
        # disjoint; retain both bounded batches without exporting the ID map.
        if len(set(ids)) != len(ids) or len(self.people) > 256:
            raise NameBindingError("chat_identity_invalid")

    @classmethod
    def from_binding(cls, binding: NameBindingSnapshot, thread_id: str):
        if binding.user_world_character_id is None or binding.user_display_name is None:
            raise NameBindingError("chat_identity_requester_required")
        return cls(binding.owner_id, binding.world_id, thread_id,
            ChatPerson(binding.user_world_character_id, presentation_name(binding.user_display_name)),
            ChatPerson(binding.actor_world_character_id, presentation_name(binding.actor_display_name)))

    def assert_scope(self, owner_id, world_id, thread_id, requester_id, responder_id):
        if (self.owner_id, self.world_id, self.thread_id, self.requester.identifier, self.responder.identifier) != (
                owner_id, world_id, thread_id, requester_id, responder_id):
            raise NameBindingError("chat_identity_scope_invalid")

    @property
    def names(self):
        return {p.identifier: p.name for p in (self.requester, self.responder, *self.people)}

    def extend(self, labels):
        known = self.names
        new = tuple(ChatPerson(identifier, presentation_name(name)) for identifier, name in labels.items()
            if identifier not in known)
        return replace(self, people=(*self.people, *new))

    def reference(self, identifier):
        if identifier == self.requester.identifier:
            return "requester_character"
        if identifier == self.responder.identifier:
            return "responding_character"
        return next((f"context_person_{i + 1}" for i, person in enumerate(self.people)
            if person.identifier == identifier), None)

    def participants(self):
        return {role: {"ref": self.reference(person.identifier), "name": person.name}
            for role, person in (("user", self.requester), ("assistant", self.responder))}

    def to_dict(self):
        value = asdict(self)
        value["people"] = list(value["people"])
        return {**value, "digest": _digest(value)}

    @classmethod
    def read(cls, metadata):
        if IDENTITY_KEY not in metadata:
            return None
        try:
            raw = metadata[IDENTITY_KEY]
            if type(raw) is not dict or set(raw) != {*cls.__dataclass_fields__, "digest"}:
                raise ValueError()
            value = {k: v for k, v in raw.items() if k != "digest"}
            if _digest(value) != raw["digest"] or type(value["people"]) is not list:
                raise ValueError()
            return cls(**{**value, "requester": ChatPerson(**value["requester"]),
                "responder": ChatPerson(**value["responder"]), "people": tuple(ChatPerson(**p) for p in value["people"])})
        except (TypeError, ValueError, KeyError, AttributeError) as exc:
            raise NameBindingError("chat_identity_invalid") from exc


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        allow_nan=False, separators=(",", ":")).encode()).hexdigest()
