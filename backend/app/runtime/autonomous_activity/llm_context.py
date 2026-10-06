"""Credential resolution and safe call identity for autonomous SNS requests."""
from app.credentials import CredentialPurpose, CredentialResolutionError, CredentialResolver
from app.domains.social.contracts.feed_execution import WorldFeedContext
from app.integrations.direct_llm import DirectLlmCallContext, DirectLlmError
from app.runtime.world_credential_binding import resolve


def world_material(ctx):
    binding = (getattr(ctx, "input_snapshot", None) or {}).get("_world_credential")
    if not binding:
        if (getattr(ctx, "input_snapshot", None) or {}).get("_world_configuration"):
            raise DirectLlmError("world_credential_binding_missing")
        return None
    try:
        return resolve(ctx.db, binding, owner_id=ctx.user_id, world_id=binding["world_id"],
            actor_id=binding["actor_id"], purpose="sns")
    except CredentialResolutionError as exc:
        raise DirectLlmError("world_credential_binding_changed") from exc

def _api_key(ctx: WorldFeedContext) -> str:
    try:
        material = world_material(ctx)
        if material is not None:
            return material.reveal()
        if ctx.credential is None:
            raise DirectLlmError("world_credential_binding_missing")
        return CredentialResolver.resolve_llm_credential(
            ctx.credential,
            purpose=CredentialPurpose.RESIDENT_LLM,
        ).reveal()
    except CredentialResolutionError as exc:
        raise DirectLlmError("credential key cannot be decrypted") from exc


def _llm_context(
    ctx: WorldFeedContext, *, node: str, lane: str
) -> DirectLlmCallContext:
    material = world_material(ctx)
    binding = (getattr(ctx, "input_snapshot", None) or {}).get("_world_credential")
    if material is not None:
        return DirectLlmCallContext(credential_id=binding["credential_id"], character_id=ctx.character.id,
            agent_run_id=ctx.run_id, node=node, lane=lane, provider=material.provider,
            model=ctx.generation_model, key_fingerprint=None)
    if ctx.credential is None:
        raise DirectLlmError("world_credential_binding_missing")
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
