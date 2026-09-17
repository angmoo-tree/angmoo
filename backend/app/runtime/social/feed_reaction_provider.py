"""Existing credential, provider schema and direct LLM transport for feed reactions."""

from __future__ import annotations
from app.config import settings
from app.contracts.activity_thought import THOUGHT_PROMPT
from app.contracts.activity_thought_output import thought_response_schema, extract_activity_thought, without_legacy_self_view_prompt
from app.domains.relationships.contracts.social_consumption import social_prompt
from app.domains.social.service.feed_reaction_prompts import (
    build_reaction_prompts,
    build_comment_prompts,
)

from app.domains.social.contracts.feed_execution import FeedReactionProvider, WorldFeedContext
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


def _api_key(ctx: WorldFeedContext) -> str:
    try:
        return CredentialResolver.resolve_llm_credential(
            ctx.credential,
            purpose=CredentialPurpose.RESIDENT_LLM,
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("credential key cannot be decrypted") from exc


def _llm_context(
    ctx: WorldFeedContext, *, node: str, lane: str
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
    def __init__(self, *, thinking_level: str = "medium", thought_enabled: bool | None = None):
        if thinking_level not in {"minimal", "low", "medium", "high"}:
            raise ValueError("feed_thinking_level_invalid")
        self._thinking_level = thinking_level
        self._thought_enabled = settings.ACTIVITY_THOUGHT_POLICY == "thought_v1" if thought_enabled is None else thought_enabled

    async def plan(
        self,
        *,
        resident_context: WorldFeedContext,
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

        if self._thought_enabled:
            system_prompt, user_prompt = without_legacy_self_view_prompt(system_prompt, user_prompt)
            system_prompt += "\n" + THOUGHT_PROMPT + "\nFor comment or NO_ACTION return empty thought; the final comment writer owns its thought."

        def validator(payload: dict[str, object]) -> schemas.FeedReactionDecision:
            thought = None
            if self._thought_enabled:
                payload, thought = extract_activity_thought(payload, include_thought=True)
            result = validate_reaction_decision(
                payload,
                candidates=candidates,
                proposal_eligible_indices=proposal_eligible_indices,
            )
            if self._thought_enabled and result.selected_action not in {None, "comment"}:
                result._activity_thought = thought
            return result

        try:
            result = await generate_json(
                api_key=api_key,
                context=_llm_context(
                    resident_context,
                    node="FeedReactionPlanner",
                    lane="world_keyword_feed",
                ),
                tracker=tracker,
                system_prompt=system_prompt + social_prompt(resident_context, "feed_reaction_planner"),
                user_prompt=user_prompt,
                response_schema=thought_response_schema(GEMINI_FEED_REACTION_RESPONSE_SCHEMA, include_thought=True) if self._thought_enabled else GEMINI_FEED_REACTION_RESPONSE_SCHEMA,
                validator=validator,
                max_output_tokens=4096 if self._thinking_level == "high" else 900,
                thinking_level=self._thinking_level,
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
        resident_context: WorldFeedContext,
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
        if reader := getattr(resident_context, "episode_memory_reader", None):
            user_prompt += reader(candidate.post_id)

        if self._thought_enabled:
            system_prompt, user_prompt = without_legacy_self_view_prompt(system_prompt, user_prompt)
            system_prompt += "\n" + THOUGHT_PROMPT
        writer_schema = GEMINI_PROPOSAL_PREVIEW_RESPONSE_SCHEMA if is_proposal else GEMINI_FEED_COMMENT_RESPONSE_SCHEMA
        if self._thought_enabled:
            writer_schema = thought_response_schema(writer_schema, include_thought=True)

        def validator(
            payload: dict[str, object],
        ) -> schemas.FeedCommentDraft | schemas.JointActivityProposalPreview:
            thought = None
            if self._thought_enabled:
                payload, thought = extract_activity_thought(payload, include_thought=True)
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
            result._activity_thought = thought
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
                system_prompt=system_prompt + social_prompt(resident_context, "feed_comment_writer"),
                user_prompt=user_prompt,
                response_schema=writer_schema,
                validator=validator,
                max_output_tokens=4096 if self._thinking_level == "high" else 1_000,
                thinking_level=self._thinking_level,
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
