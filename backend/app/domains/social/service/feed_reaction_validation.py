"""Validate the selected server candidate, its permitted action and writer evidence."""

from app.domains.social.schemas import feed as schemas
from app.domains.social.exceptions import FeedReactionValidationError


def validate_reaction_decision(
    payload: object,
    *,
    candidates: tuple[schemas.WorldFeedCandidateRead, ...],
    proposal_eligible_indices: frozenset[int] = frozenset(),
) -> schemas.FeedReactionDecision:
    decision = schemas.FeedReactionDecision.model_validate(payload)
    if decision.selected_action is None:
        return decision
    index = decision.selected_candidate_index
    if index is None or index >= len(candidates):
        raise FeedReactionValidationError(
            "selected candidate is outside server context"
        )
    candidate = candidates[index]
    if decision.selected_action not in candidate.allowed_actions:
        raise FeedReactionValidationError(
            "selected action is not allowed for candidate"
        )
    if (
        decision.interaction_intent == "joint_activity_proposal"
        and int(decision.selected_candidate_index or 0) not in proposal_eligible_indices
    ):
        raise FeedReactionValidationError("proposal eligibility is unavailable")
    return decision


def validate_comment_draft(
    payload: object,
    *,
    candidate: schemas.WorldFeedCandidateRead,
    decision: schemas.FeedReactionDecision,
) -> schemas.FeedCommentDraft | schemas.JointActivityProposalPreview:
    if decision.interaction_intent == "ordinary_comment":
        draft = schemas.FeedCommentDraft.model_validate(payload)
        if (
            draft.source_post_id != candidate.post_id
            or draft.interaction_intent != decision.interaction_intent
            or draft.comment_purpose != decision.comment_purpose
        ):
            raise FeedReactionValidationError("comment evidence mismatch")
        return draft
    preview = schemas.JointActivityProposalPreview.model_validate(payload)
    if (
        preview.source_post_id != candidate.post_id
        or preview.target_world_character_id != candidate.author_world_character_id
    ):
        raise FeedReactionValidationError("proposal evidence mismatch")
    return preview
