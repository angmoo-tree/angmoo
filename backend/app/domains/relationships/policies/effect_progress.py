"""Pure, exact chains; neither version increments nor actor equality are proof."""
from dataclasses import dataclass
from app.domains.relationships.contracts.social_context import RelationshipValidationReference

@dataclass(frozen=True, slots=True)
class RelationshipEffect:
    before: RelationshipValidationReference
    after: RelationshipValidationReference

    def __post_init__(self):
        if (self.before.relationship_state_id != self.after.relationship_state_id or
            self.before.target_world_character_id != self.after.target_world_character_id or
            self.before == self.after):
            raise ValueError("relationship_effect_invalid")


def proves(expected, current, effects):
    relevant = [effect for effect in effects if effect.before.relationship_state_id == expected.relationship_state_id]
    if not relevant:
        return False
    cursor = expected
    for effect in relevant:
        if effect.before != cursor:
            return False
        cursor = effect.after
    return cursor == current
