"""Credential resolution and safe call identity for autonomous SNS requests."""
from app.credentials import CredentialPurpose, CredentialResolutionError, CredentialResolver
from app.domains.social.contracts.feed_execution import WorldFeedContext
from app.integrations.direct_llm import DirectLlmCallContext, DirectLlmError

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
        model=getattr(ctx, "generation_model", ctx.credential.model),
        key_fingerprint=ctx.credential.key_fingerprint,
    )
