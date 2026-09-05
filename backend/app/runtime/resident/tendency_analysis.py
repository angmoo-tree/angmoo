"""Direct/OpenClaw tendency generation, profile IO and original failure compensation."""
from __future__ import annotations
from typing import Any
from uuid import uuid4
from sqlalchemy.orm import Session
from app.config import settings
from app.core.redaction import redact_secret_text
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.routines.contracts.activity_management import ActivityOwner
from app.domains.routines.contracts.tendency_analysis import TendencyAnalysisWorkflows, DetailT
from app.domains.routines.constants import TENDENCY_ANALYSIS_MAX_OUTPUT_TOKENS, TENDENCY_LLM_TOOLS_ALLOW
from app.domains.routines.exceptions import OpenClawNotConfiguredError, AgentSlotUnavailableError
from app.domains.routines.schemas.tendency import _TendencyAnalysisPayload
from app.domains.routines.service import slot_pool
from app.domains.routines.service.tendency_analysis import prepare_tendency_analysis, store_tendency_analysis
from app.domains.routines.service.tendency import _normalize_tendency_payload, _build_tendency_analysis_prompt, _extract_gateway_result_text, _parse_tendency_json
from app.domains.routines.service.tendency_settings import _mark_tendency_error
from app.domains.characters.exceptions import CredentialRequiredError, CredentialSyncError
from app.domains.routines.exceptions import LlmCredentialInvalidError
from app.domains.characters.service.creator import llm_credential_error_message
from app.integrations.direct_llm import RunLlmTracker, DirectLlmCallContext, DirectLlmError, generate_json
from app.services.runtime_boundary import OpenClawGatewayClient, OpenClawGatewayError

async def analyze_tendency(
    db: Session, user: ActivityOwner, character_id: str,
    *, workflows: TendencyAnalysisWorkflows[DetailT],
) -> DetailT:
    character, setting, credential = prepare_tendency_analysis(
        db, user, character_id, workflows=workflows
    )

    if settings.server_llm_engine == "direct":
        run_id = str(uuid4())
        try:
            material = CredentialResolver.resolve_llm_credential(
                credential,
                purpose=CredentialPurpose.RESIDENT_LLM,
                owner_id=user.id,
                character_id=character.id,
            )
            api_key = material.reveal()
            tracker = RunLlmTracker()

            def _validator(payload: dict[str, Any]) -> dict[str, Any]:
                return _TendencyAnalysisPayload.model_validate(payload).model_dump()

            payload = await generate_json(
                api_key=api_key,
                context=DirectLlmCallContext(
                    credential_id=credential.id,
                    character_id=character.id,
                    agent_run_id=run_id,
                    node="TendencyAnalysis",
                    lane="server_llm",
                    provider=credential.provider,
                    model=credential.model,
                    key_fingerprint=credential.key_fingerprint,
                ),
                tracker=tracker,
                system_prompt=_build_tendency_analysis_prompt(character=character),
                user_prompt=(
                    "Analyze this Angmoo persona for community activity. "
                    "Return only the requested JSON object."
                ),
                response_schema=_TendencyAnalysisPayload,
                validator=_validator,
                max_output_tokens=TENDENCY_ANALYSIS_MAX_OUTPUT_TOKENS,
                thinking_level=settings.tendency_analysis_thinking_level,
            )
            summary, action_ranges, planner_profile = _normalize_tendency_payload(payload)
            store_tendency_analysis(
                db, setting, user=user, character=character,
                summary=summary, action_ranges=action_ranges, planner_profile=planner_profile,
                reason="user_requested_tendency_analysis_direct",
                result_factory=lambda: "Community activity tendency was analyzed with direct LLM; "
                    f"llm_call_count={tracker.summary().get('call_count', 0)}.",
            )
            db.refresh(character)
            return workflows.build_detail(db, character)
        except ValueError as exc:
            message = "Agent credential key cannot be decrypted"
            _mark_tendency_error(db, setting, message)
            raise CredentialRequiredError(message) from exc
        except DirectLlmError as exc:
            message = redact_secret_text(str(exc))[:1000]
            _mark_tendency_error(db, setting, message)
            raise

    token = settings.openclaw_gateway_token
    if token is None:
        _mark_tendency_error(db, setting, "OPENCLAW_GATEWAY_TOKEN is missing")
        raise OpenClawNotConfiguredError(
            "OPENCLAW_GATEWAY_TOKEN is missing"
        )

    run_id = str(uuid4())
    timeout_seconds = settings.openclaw_timeout_seconds
    slot = slot_pool.claim_agent_slot(
        db,
        run_id=run_id,
        agent_ids=settings.openclaw_agent_ids,
        lease_seconds=timeout_seconds + 90,
    )
    if slot is None:
        raise AgentSlotUnavailableError(
            f"No OpenClaw slot is available for {', '.join(settings.openclaw_agent_ids)}"
        )

    bound_profile = False
    last_error: str | None = None
    client = OpenClawGatewayClient(
        url=settings.openclaw_gateway_url,
        token=token,
        timeout_seconds=timeout_seconds,
    )
    try:
        workflows.bind_profile(
            slot, user_id=user.id, character=character, credential=credential
        )
        bound_profile = True
        await client.reload_secrets()
        gateway_result = await client.run_agent(
            message="Analyze this Angmoo persona for community activity. Return only JSON.",
            agent_id=slot.agent_id,
            session_key=(
                f"agent:{slot.agent_id}:angmoo:tendency:{user.id}:{character.id}:{run_id}"
            ),
            provider=credential.provider,
            model=credential.model,
            auth_profile_id=credential.auth_profile_id,
            tool_choice="none",
            tools_allow=TENDENCY_LLM_TOOLS_ALLOW,
            prompt_mode="minimal",
            bootstrap_context_mode="lightweight",
            bootstrap_context_run_kind="default",
            idempotency_key=run_id,
            thinking=settings.tendency_analysis_thinking_level,
            extra_system_prompt=_build_tendency_analysis_prompt(character=character),
        )
        raw_text = _extract_gateway_result_text(gateway_result)
        payload = _parse_tendency_json(raw_text)
        summary, action_ranges, planner_profile = _normalize_tendency_payload(payload)
        store_tendency_analysis(
            db, setting, user=user, character=character,
            summary=summary, action_ranges=action_ranges, planner_profile=planner_profile,
            reason="user_requested_tendency_analysis",
            result_factory=lambda: "Community activity tendency was analyzed with the user's API key.",
        )
        db.refresh(character)
        return workflows.build_detail(db, character)
    except OpenClawGatewayError as exc:
        friendly_error = llm_credential_error_message(exc)
        if friendly_error is not None:
            last_error = friendly_error
            _mark_tendency_error(db, setting, friendly_error)
            raise LlmCredentialInvalidError(friendly_error) from exc
        last_error = redact_secret_text(str(exc))
        _mark_tendency_error(db, setting, last_error)
        raise
    except Exception as exc:
        last_error = redact_secret_text(str(exc))
        _mark_tendency_error(db, setting, last_error)
        raise
    finally:
        release_error = None
        if bound_profile:
            try:
                workflows.release_profile(
                    slot,
                    user_id=user.id,
                    character_id=character.id,
                    credential=credential,
                )
                await client.reload_secrets()
            except CredentialSyncError as exc:
                release_error = redact_secret_text(str(exc))
                if last_error is None:
                    last_error = release_error
                    _mark_tendency_error(db, setting, release_error)
            except OpenClawGatewayError as exc:
                release_error = redact_secret_text(str(exc))
                if last_error is None:
                    last_error = release_error
                    _mark_tendency_error(db, setting, release_error)
        slot_pool.release_agent_slot(
            db, agent_id=slot.agent_id, run_id=run_id, last_error=last_error
        )
        if release_error is not None and last_error == release_error:
            raise CredentialSyncError(release_error)
