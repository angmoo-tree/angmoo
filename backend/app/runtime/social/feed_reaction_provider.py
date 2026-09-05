"""Existing credential, provider schema and direct LLM transport for feed reactions."""

from __future__ import annotations
from app.domains.social.service.feed_reaction_prompts import (
    build_reaction_prompts,
    build_comment_prompts,
)

from app.domains.social.contracts.feed_execution import FeedReactionProvider
from app.domains.social.exceptions import FeedReactionValidationError
from app.domains.social.service.feed_reaction_validation import (
    validate_reaction_decision,
    validate_comment_draft,
)


from pydantic import ValidationError

from app.domains.social.schemas import feed as schemas
from app.credentials import (
    CredentialPurpose,
    CredentialResolutionError,
    CredentialResolver,
)
from app.providers.gemini import build_gemini_developer_response_schema
from app.integrations.direct_llm import (
    DirectLlmCallContext,
    DirectLlmError,
    RunLlmTracker,
    generate_json,
)
from app.runtime.resident.context import LangGraphResidentContext
from app.domains.social.contracts.world_feed import ReadySearchProfile


GEMINI_FEED_REACTION_RESPONSE_SCHEMA = build_gemini_developer_response_schema(
    schemas.FeedReactionDecision
)
GEMINI_FEED_COMMENT_RESPONSE_SCHEMA = build_gemini_developer_response_schema(
    schemas.FeedCommentDraft
)
GEMINI_PROPOSAL_PREVIEW_RESPONSE_SCHEMA = build_gemini_developer_response_schema(
    schemas.JointActivityProposalPreview
)


def _api_key(ctx: LangGraphResidentContext) -> str:
    try:
        return CredentialResolver.resolve_llm_credential(
            ctx.credential,
            purpose=CredentialPurpose.RESIDENT_LLM,
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("credential key cannot be decrypted") from exc


def _llm_context(
    ctx: LangGraphResidentContext, *, node: str, lane: str
) -> DirectLlmCallContext:
    return DirectLlmCallContext(
        credential_id=ctx.credential.id,
        character_id=ctx.character.id,
        agent_run_id=ctx.run_id,
        node=node,
        lane=lane,
        provider=ctx.credential.provider,
        model=ctx.credential.model,
        key_fingerprint=ctx.credential.key_fingerprint,
    )


class DirectFeedReactionProvider:
    async def plan(
        self,
        *,
        resident_context: LangGraphResidentContext,
        profile: ReadySearchProfile,
        candidates: tuple[schemas.WorldFeedCandidateRead, ...],
        tracker: RunLlmTracker,
        proposal_eligible_indices: frozenset[int] = frozenset(),
    ) -> schemas.FeedReactionDecision:
        api_key = _api_key(resident_context)
        system_prompt, user_prompt = build_reaction_prompts(
            profile=profile,
            candidates=candidates,
            proposal_eligible_indices=proposal_eligible_indices,
        )

        def validator(payload: dict[str, object]) -> schemas.FeedReactionDecision:
            return validate_reaction_decision(
                payload,
                candidates=candidates,
                proposal_eligible_indices=proposal_eligible_indices,
            )

        try:
            result = await generate_json(
                api_key=api_key,
                context=_llm_context(
                    resident_context,
                    node="FeedReactionPlanner",
                    lane="world_keyword_feed",
                ),
                tracker=tracker,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=GEMINI_FEED_REACTION_RESPONSE_SCHEMA,
                validator=validator,
                max_output_tokens=900,
                thinking_level="medium",
                on_rate_limit_wait=resident_context.on_rate_limit_wait,
                should_retry_json_error=lambda *_args: False,
            )
        except (DirectLlmError, ValidationError, ValueError) as exc:
            setattr(exc, "node", "FeedReactionPlanner")
            setattr(exc, "lane", "world_keyword_feed")
            raise
        return (
            result
            if isinstance(result, schemas.FeedReactionDecision)
            else validator(result)
        )

    async def write_comment(
        self,
        *,
        resident_context: LangGraphResidentContext,
        profile: ReadySearchProfile,
        candidate: schemas.WorldFeedCandidateRead,
        decision: schemas.FeedReactionDecision,
        tracker: RunLlmTracker,
    ) -> schemas.FeedCommentDraft | schemas.JointActivityProposalPreview:
        api_key = _api_key(resident_context)
        is_proposal = decision.interaction_intent == "joint_activity_proposal"
        system_prompt, user_prompt = build_comment_prompts(
            profile=profile,
            candidate=candidate,
            decision=decision,
            is_proposal=is_proposal,
        )

        def validator(
            payload: dict[str, object],
        ) -> schemas.FeedCommentDraft | schemas.JointActivityProposalPreview:
            result = validate_comment_draft(
                payload,
                candidate=candidate,
                decision=decision,
            )
            if not is_proposal and not isinstance(result, schemas.FeedCommentDraft):
                raise FeedReactionValidationError("ordinary writer returned proposal")
            if is_proposal and not isinstance(
                result, schemas.JointActivityProposalPreview
            ):
                raise FeedReactionValidationError("proposal writer returned comment")
            return result

        try:
            result = await generate_json(
                api_key=api_key,
                context=_llm_context(
                    resident_context,
                    node="ReplyWriter",
                    lane=(
                        "world_keyword_feed_proposal_preview"
                        if is_proposal
                        else "world_keyword_feed_comment"
                    ),
                ),
                tracker=tracker,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=(
                    GEMINI_PROPOSAL_PREVIEW_RESPONSE_SCHEMA
                    if is_proposal
                    else GEMINI_FEED_COMMENT_RESPONSE_SCHEMA
                ),
                validator=validator,
                max_output_tokens=1_000,
                thinking_level="medium",
                on_rate_limit_wait=resident_context.on_rate_limit_wait,
            )
        except (DirectLlmError, ValidationError, ValueError) as exc:
            setattr(exc, "node", "ReplyWriter")
            setattr(
                exc,
                "lane",
                "world_keyword_feed_proposal_preview"
                if is_proposal
                else "world_keyword_feed_comment",
            )
            raise
        if isinstance(
            result,
            (schemas.FeedCommentDraft, schemas.JointActivityProposalPreview),
        ):
            return result
        return validator(result)
