"""Opt-in card component probe; cap all physical direct-LLM requests at sixty.

Run in an isolated container with code/card inputs and credential volume read-only.
Only synthetic SQLite sessions and the explicit output directory are written.
This is not an end-to-end scheduler, recall or long-running relationship test.
"""
import argparse
import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations import direct_llm
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.models import User, InstallationIdentity
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.characters import models, schemas
from app.domains.characters.service import drafts, card_import
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters import client as setup_client
from app.domains.world_characters.service import setup_validation
from app.domains.worlds.models import World
from app.domains.worlds.service import build_world_generation_context
from app.domains.chat.service.profiles import _response_profile
from app.domains.chat.contracts.character_response_generator import CharacterResponseGeneratorRequest
from app.domains.chat.contracts.evidence_bundle import EvidenceBundle, compute_evidence_hash
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.chat.contracts.response_request import RetrievalOutcome
from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator
from app.runtime.characters.creator import build_creator_workflows
from app.runtime.persistence.model_registration import register_models
from scripts.evaluate_four_call_activity import Budget, resolve_credential, evaluate

FIELDS = ("name", "one_liner", "personality", "speech_style", "worldview", "topic_preferences", "safety_rules")
EDITS = {
    "Seraphina": "따뜻하고 호기심이 많은 엘프. 상대의 선택을 존중한다.",
    "Sakana": "유쾌하고 친절하며 질문에 실용적으로 도움을 주려는 조수.",
    "FluxTheCat": "호기심 많고 장난스럽지만 무례하지 않은 고양이.",
}


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        default=lambda item: item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item)), encoding="utf-8")


def empty_evidence():
    values = dict(request_id="isolated-card-chat", request_scope_hash="a" * 64,
        route=RetrievalRoute.CURRENT_CONTEXT, retrieval_outcome=RetrievalOutcome.CURRENT_CONTEXT,
        items=(), partial_axes=(), degraded_reason=None, clarification_slot=None)
    return EvidenceBundle(**values, evidence_hash=compute_evidence_hash(**values))


async def run(args):
    if args.output.exists() and not args.retry_preparation:
        raise ValueError("evaluation_output_exists")
    if args.retry_preparation and not (args.output / "budget.json").exists():
        raise ValueError("existing_evaluation_budget_required")
    args.output.mkdir(parents=True, exist_ok=True)
    suffix = "-place-recheck" if args.final_preparation else "-recheck" if args.retry_preparation else ""
    if args.retry_preparation and (args.output / f"results{suffix}.json").exists():
        raise ValueError("recheck_already_performed")
    settings.MEDIA_ROOT = str(args.output / "isolated-media")
    manifest = {"model": "gemini-3.1-flash-lite", "thinking": "high", "max_physical_requests": 60,
        "cards": [{"name": name, "sha256": hashlib.sha256((args.cards / f"{name}.png").read_bytes()).hexdigest()}
                  for name in EDITS], "edits": EDITS, "speech_edit": "한국어 존댓말로 간결하게 말한다. 별빛쉼터에서 차를 마시는 것을 좋아한다.",
        "scenarios": ["prepare profile and forty activity candidates", "SNS ordinary and correction", "Chat greeting and edited preference"],
        "limitations": ["Provider components on isolated final edited values; no live World mutation.",
            "SNS uses frozen synthetic source/memory/routine fixtures; no real hybrid retrieval or publication.",
            "Chat measures final response generator only; no router/embedding/memory writes.",
            "Not a statistical failure-rate or long-running quality claim."], "operational_writes": False}
    manifest["recheck"] = args.retry_preparation
    manifest["profile_output_budget"] = setup_client.PROFILE_MAX_OUTPUT_TOKENS
    manifest["manual_review_edits"] = ({"Sakana": "Replace unsupported {{user}} in background with 대화 상대",
        "FluxTheCat": "Replace conflicting nonverbal background with an explicitly speaking cat description"} if args.retry_preparation else {})
    write(args.output / f"manifest{suffix}.json", manifest)
    budget = Budget(args.output / "budget.json", 60)
    original = direct_llm.RunLlmTracker.next_provider_call_order
    trackers = []
    def counted(tracker):
        budget.reserve()
        if not any(item is tracker for item in trackers):
            trackers.append(tracker)
        return original(tracker)
    direct_llm.RunLlmTracker.next_provider_call_order = counted
    cred = material = None
    if not args.offline:
        cred = resolve_credential(args.credentials)
        if cred.model != manifest["model"]:
            raise ValueError("wrong_evaluation_model")
        cred.thinking_level = "high"
        material = CredentialResolver.resolve_llm_credential(cred, purpose=CredentialPurpose.WORLD_CHARACTER_SETUP_LLM)
    results = []
    try:
        for name, personality in EDITS.items():
            engine = create_engine("sqlite://")
            register_models().create_all(engine)
            with Session(engine, expire_on_commit=False) as db:
                owner = User(id="evaluation-owner", display_name="Evaluation")
                db.add(owner); db.flush()
                db.add(InstallationIdentity(singleton_key="local-installation", installation_id="evaluation",
                    owner_user_id=owner.id, bootstrap_state="claimed", claimed_at=datetime.now(UTC)))
                db.commit()
                workflows = build_creator_workflows()
                draft = await drafts.create_draft(db, owner, schemas.AgentCreationDraftCreate(), workflows=workflows)
                imported = card_import.import_card(db, owner, draft.id, revision=1,
                    content=(args.cards / f"{name}.png").read_bytes(), workflows=workflows)["draft"]
                background = imported.worldview
                if args.retry_preparation and name == "Sakana":
                    background = background.replace("{{user}}", "대화 상대")
                if args.retry_preparation and name == "FluxTheCat":
                    background = "Flux는 별빛쉼터에서 지내며 룸바 타기와 새 구경을 좋아하는 고양이다. 사람과 한국어 존댓말로 대화할 수 있고 차를 마시며 쉰다."
                edited = drafts.update_draft(db, owner, draft.id, schemas.AgentCreationDraftUpdate(
                    revision=imported.revision, personality=personality, speech_style=manifest["speech_edit"],
                    worldview=background, topic_preferences="차, 일상, 친구"), workflows=workflows)
                detail = drafts.complete_draft(db, owner, draft.id,
                    schemas.AgentCreationDraftComplete(revision=edited.revision), workflows=workflows)
                character = db.get(models.Character, detail.character.id)
                actor = db.scalar(select(WorldCharacter).where(WorldCharacter.character_id == character.id))
                world = db.get(World, actor.world_id)
                final = {key: getattr(character, key) for key in FIELDS}
                write(args.output / f"{name}-final-settings{suffix}.json", final)
                if args.offline:
                    empty_evidence()
                    results.append({"card": name, "registered": True, "autonomous_enabled": actor.autonomous_enabled})
                    write(args.output / "results.json", results)
                    continue
                world_context = build_world_generation_context(db, world)
                generation_input = setup_validation.build_world_character_generation_input(
                    character=character, world_character=actor, world_context=world_context)
                provider = setup_client.DirectLlmWorldCharacterSetupProvider()
                row = {"card": name, "stages": {}}
                try:
                    profile = await provider.generate_community_profile(material=material,
                        character_id=character.id, generation_input=generation_input)
                    repertoire = await provider.generate_repertoire(material=material, character_id=character.id,
                        generation_input=generation_input, community_profile=profile.payload,
                        validator=lambda value: setup_validation.validate_activity_repertoire(value, world_context=world_context, world_character=actor))
                    row["stages"]["preparation"] = {"status": "valid", "profile": asdict(profile), "repertoire": asdict(repertoire)}
                except Exception as exc:
                    row["stages"]["preparation"] = {"status": "failed", "error": type(exc).__name__,
                        **{key: getattr(exc, key, None) for key in ("reason_code", "failure_class", "parse_error_type", "validation_code", "field_path", "json_error_diagnostics")}}
                cases = () if args.retry_preparation else (("ordinary", "별빛쉼터에서 차를 마시며 쉬고 있어. 좋아하는 차가 있어?", ""),
                    ("correction", "내가 물건을 망가뜨렸다는 말은 정정됐어. 낡아서 부서진 거였어.", "물건 파손은 사용자의 잘못이 아니라고 확인됐다."))
                for index, case in enumerate(cases):
                    outcome = await evaluate(case, index, 2, cred, SimpleNamespace(reserve=lambda: None), character_settings=final)
                    row["stages"]["sns_" + case[0]] = outcome
                chat = DirectLlmCharacterResponseGenerator(replace(material, purpose=CredentialPurpose.MESSAGE_LLM))
                questions = () if args.final_preparation or (args.retry_preparation and name == "Seraphina") else ("안녕! 어떤 것을 좋아해?", "별빛쉼터에서 무엇을 하면서 쉬고 싶어?")
                for index, question in enumerate(questions):
                    try:
                        response = await chat.generate(CharacterResponseGeneratorRequest(user_message=question,
                            profile=_response_profile(character), recent_context=(), evidence=empty_evidence()))
                        row["stages"][f"chat_{index}"] = {"status": "valid", **asdict(response)}
                    except Exception as exc:
                        row["stages"][f"chat_{index}"] = {"status": "failed", "error": type(exc).__name__}
                results.append(row)
                write(args.output / f"results{suffix}.json", results)
                print(json.dumps({"card": name, "physical_requests": budget.used,
                    "statuses": {key: value.get("status") for key, value in row["stages"].items()}}, ensure_ascii=False), flush=True)
            engine.dispose()
    finally:
        direct_llm.RunLlmTracker.next_provider_call_order = original
        allowed = {"node", "lane", "status", "duration_ms", "usage", "thinking_level", "max_output_tokens", "finish_reason", "failure_class", "estimated_cost_usd"}
        write(args.output / f"usage{suffix}.json", {"physical_requests": budget.used,
            "calls": [{key:value for key,value in call.items() if key in allowed} for tracker in trackers for call in tracker.calls]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline", action="store_true", help="Check registration without credentials or AI calls")
    parser.add_argument("--retry-preparation", action="store_true", help="Use the SAME 60-call budget for targeted rechecks")
    parser.add_argument("--final-preparation", action="store_true", help="One final place-identifier recheck, no additional Chat")
    asyncio.run(run(parser.parse_args()))
