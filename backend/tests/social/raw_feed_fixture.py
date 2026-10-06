"""Synthetic typed admissions for canonical Feed effects, with no old SDK.

This fixture supplies known decisions to the surviving domain workflow. It
does not reproduce the retired prompt/provider/graph and is not a transport
test. Actual V2 SDK requests are checked by the V2 provider probe separately.
"""
from app.contracts.activity_thought_output import extract_activity_thought
from app.domains.social.service.feed_reaction_validation import validate_reaction_decision, validate_comment_draft
from app.runtime.relationships.social_metrics import prepare_sources, stage_sources


class RawFeedFixture:
    def __init__(self, response, *, thought=False):
        self.response, self.thought = response, thought

    async def plan(self, *, resident_context, profile, candidates, tracker, proposal_eligible_indices=frozenset()):
        self.delivery.dispatched()
        raw = await self.response("decision")
        self.delivery.delivered()
        metrics = raw.pop("relationship_metrics", None)
        thought = None
        if self.thought:
            raw, thought = extract_activity_thought(raw, include_thought=True)
        value = validate_reaction_decision(raw, candidates=candidates, proposal_eligible_indices=proposal_eligible_indices)
        if self.thought and value.selected_action not in {None, "comment"}:
            value._activity_thought = thought
        sources = prepare_sources(resident_context.db, actor=profile.world_character,
                                  post_ids=[candidate.post_id for candidate in candidates])
        if sources and metrics is not None:
            stage_sources(resident_context.db, actor=profile.world_character, manifest=sources,
                          raw=metrics, decision_key=self.delivery.row.id, now=resident_context.run_started_at)
        return value

    async def write_comment(self, *, candidate, decision, **kwargs):
        raw = await self.response("writer")
        thought = None
        if self.thought:
            raw, thought = extract_activity_thought(raw, include_thought=True)
        result = validate_comment_draft(raw, candidate=candidate, decision=decision)
        result._activity_thought = thought
        return result
