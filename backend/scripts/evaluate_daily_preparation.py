"""Opt-in, durable 60-wire-call preparation/SNS comparison; no live writes.

Run inside an isolated container with credentials volume mounted read-only.
Synthetic component SNS probes do not assert publication/retrieval quality.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.characters import models, schemas
from app.domains.characters.service import card_import, drafts
from app.domains.characters.service.prompt_persona import model_persona, PERSONA_INTERPRETATION
from app.domains.identity.models import User, InstallationIdentity
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.world_characters import client as setup_client
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service import setup_validation
from app.domains.worlds.models import World
from app.domains.worlds.service.generation_context import build_world_generation_context
from app.domains.routines.client import generate_daily_preparation
from app.domains.routines.schemas.daily_generation import GeneratedDailyPlan
from app.integrations import direct_llm
from app.runtime.characters.creator import build_creator_workflows
from app.runtime.persistence.model_registration import register_models
from app.runtime.social.topic_preparation import generate_topics
from scripts.evaluate_description_centric import DurableBudget, OneSdkAttempt, write_json, FIELDS
from scripts.evaluate_four_call_activity import evaluate
from scripts.evaluate_personalized_activity import credential

CARDS = ("Seraphina.png", "Sakana.png", "FluxTheCat.png")


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    budget = DurableBudget(args.output / "budget.json")
    lock = args.output / "active.lock"
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    original_next, original_adapter = direct_llm.RunLlmTracker.next_provider_call_order, direct_llm.get_provider_adapter
    trackers = []
    def counted(tracker):
        budget.reserve()
        if not any(t is tracker for t in trackers): trackers.append(tracker)
        return original_next(tracker)
    direct_llm.RunLlmTracker.next_provider_call_order = counted
    direct_llm.get_provider_adapter = lambda provider, model: OneSdkAttempt(original_adapter(provider, model))
    manifest = dict(model="gemini-3.1-flash-lite", thinking="high", cap=60,
        credential_character_id=args.character_id, operational_writes=False, sdk_attempts=1,
        cases=[dict(card=card, sha256=hashlib.sha256((args.cards/card).read_bytes()).hexdigest()) for card in CARDS],
        normal_budget=42, reserve_budget=18,
        comparison="Per card: old profile+40, old SNS4, initial daily+topics, new SNS4, next daily, manual topics.",
        quality_rubric=["persona", "memory/relationship", "local time", "continuity", "no invented completed events", "topic groundedness"],
        limitations=["Frozen synthetic social sources and memories; no live retrieval/publication.",
                     "One paired sample per card is not long-run quality proof.",
                     "Daily continuation includes supplied actual-history fixture; storage contracts tested separately."])
    path = args.output / "manifest.json"
    if path.exists() and json.loads(path.read_text(encoding="utf-8")) != manifest:
        raise ValueError("evaluation_manifest_changed")
    write_json(path, manifest)
    try:
        cred = credential(args.credentials, args.character_id)
        # Only the isolated credential view changes model/thinking; live row is read-only.
        cred.model, cred.thinking_level = manifest["model"], "high"
        material = CredentialResolver.resolve_llm_credential(cred, purpose=CredentialPurpose.WORLD_CHARACTER_SETUP_LLM,
            owner_id=cred.owner_id, character_id=cred.character_id)
        for card in CARDS:
            result_path = args.output / (Path(card).stem + ".json")
            if result_path.exists(): continue
            row = {"card": card, "stages": {}}
            async def stage(name, operation):
                before, started = budget.used, monotonic()
                try:
                    value = await operation()
                    result = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
                    row["stages"][name] = {"status": result.get("status", "valid") if isinstance(result, dict) else "valid", "result": result}
                    return value
                except Exception as exc:
                    row["stages"][name] = {"status": "failed", "error_type": type(exc).__name__,
                        "failure_class": getattr(exc, "failure_class", None), "validation_code": getattr(exc, "validation_code", None)}
                    return None
                finally:
                    row["stages"][name].update(wire_calls=budget.used-before, duration_ms=round((monotonic()-started)*1000))
                    write_json(args.output / "progress.json", row)
                    print(json.dumps({"card": card, "stage": name, "used": budget.used, "status": row["stages"][name]["status"]}), flush=True)
            engine = create_engine("sqlite://")
            register_models().create_all(engine)
            settings.MEDIA_ROOT = str(args.output / "media")
            with Session(engine, expire_on_commit=False) as db:
                owner = User(id="evaluation-owner", display_name="Evaluation")
                db.add(owner); db.flush()
                db.add(InstallationIdentity(singleton_key="local-installation", installation_id="daily-evaluation", owner_user_id=owner.id,
                    bootstrap_state="claimed", claimed_at=datetime.now(UTC))); db.commit()
                flows = build_creator_workflows()
                draft = await drafts.create_draft(db, owner, schemas.AgentCreationDraftCreate(), workflows=flows)
                current = card_import.import_card(db, owner, draft.id, revision=draft.revision, content=(args.cards/card).read_bytes(), workflows=flows)["draft"]
                detail = drafts.complete_draft(db, owner, draft.id, schemas.AgentCreationDraftComplete(revision=current.revision), workflows=flows)
                character = db.get(models.Character, detail.character.id)
                actor = db.scalar(select(WorldCharacter).where(WorldCharacter.character_id == character.id))
                world = db.get(World, actor.world_id)
                context = build_world_generation_context(db, world)
                char_settings = {key: getattr(character, key) for key in FIELDS}
                generation_input = setup_validation.build_world_character_generation_input(character=character, world_character=actor, world_context=context)
                provider = setup_client.DirectLlmWorldCharacterSetupProvider()
                async def old_profile():
                    return (await provider.generate_community_profile(material=material, character_id=character.id, generation_input=generation_input)).payload
                settings.DAILY_PREPARATION_ENABLED = False
                profile = await stage("old_profile", old_profile)
                if profile:
                    async def old_repertoire():
                        response = await provider.generate_repertoire(material=material, character_id=character.id,
                            generation_input=generation_input, community_profile=profile,
                            validator=lambda value: setup_validation.validate_activity_repertoire(value, world_context=context, world_character=actor))
                        return asdict(response.payload)
                    await stage("old_repertoire", old_repertoire)
                case = (Path(card).stem, "아까 한 말은 정정할게. 자료는 잃어버리지 않았어. 그리고 오늘은 무리하지 말고 쉬자.", "상대와 이미 인사를 나누었고, 자료 분실 여부는 확인되지 않았었다.")
                await stage("old_sns", lambda: evaluate(case, 0, 2, cred, SimpleNamespace(reserve=lambda:None),
                    character_settings=char_settings, community_profile=profile.model_dump() if profile else None))
                source = {"persona": {**model_persona(character), "interpretation": PERSONA_INTERPRETATION},
                    "world": context.model_dump(mode="json"), "local_date": "2026-08-10", "local_now": "2026-08-10T10:05:00+09:00",
                    "timezone": "Asia/Seoul", "allowed_places": {part: [] for part in ("dawn","morning","afternoon","evening")},
                    "fixed_items": [], "confirmed_reservations": [], "recent_activity": {"records": []}, "current_state": {"mood":"calm"}}
                # Null places make the synthetic SNS fixture portable. Place validation is tested separately.
                async def generate(initial):
                    return (await generate_daily_preparation(material=material, character_id=character.id, source=source,
                        initial=initial, reserve=lambda:None, reserve_json_retry=lambda:None))[0]
                settings.DAILY_PREPARATION_ENABLED = True
                initial = await stage("new_initial", lambda: generate(True))
                if initial:
                    await stage("new_sns", lambda: evaluate(case, 0, 2, cred, SimpleNamespace(reserve=lambda:None),
                        character_settings=char_settings, daily_plan=initial.daily_plan))
                source["local_date"], source["local_now"] = "2026-08-11", "2026-08-11T00:05:00+09:00"
                source["recent_activity"] = {"records": [{"occurred_at":"2026-08-10T10:20:00+09:00", "summary":"상대가 자료를 잃어버리지 않았다고 정정했고, 당분간 조용히 쉬고 싶다고 말했다."}]}
                source["current_state"] = {"mood":"calm", "state_note":"상대의 정정을 확인했다. 아직 오늘의 활동은 시작하지 않았다."}
                await stage("new_next_date", lambda: generate(False))
                await stage("manual_topics", lambda: generate_topics(material, character.id, {"persona":model_persona(character), "world":source["world"]}))
            engine.dispose()
            write_json(result_path, row)
            allowed = {"node", "lane", "status", "duration_ms", "usage", "thinking_level", "max_output_tokens", "finish_reason", "failure_class"}
            write_json(args.output / "usage.json", {"calls": [{k:v for k,v in call.items() if k in allowed} for t in trackers for call in t.calls]})
    finally:
        direct_llm.RunLlmTracker.next_provider_call_order, direct_llm.get_provider_adapter = original_next, original_adapter
        lock.unlink(missing_ok=True)


async def sns_probe(args):
    """Repair the synthetic missing-role fixture; retain original failures and budget."""
    from app.domains.characters.service.card_mapping import map_card
    from app.integrations.character_cards.parser import parse_card
    budget = DurableBudget(args.output / "budget.json")
    lock = args.output / "active.lock"
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    original_next, original_adapter = direct_llm.RunLlmTracker.next_provider_call_order, direct_llm.get_provider_adapter
    def counted(tracker):
        budget.reserve()
        return original_next(tracker)
    direct_llm.RunLlmTracker.next_provider_call_order = counted
    direct_llm.get_provider_adapter = lambda provider, model: OneSdkAttempt(original_adapter(provider, model))
    manifest_path = args.output / "sns-probe-manifest.json"
    if not manifest_path.exists():
        write_json(manifest_path, {"reason": "Synthetic WorldRole missing in original Routine probe; no provider request was made for those lanes.",
            "correction": "Supply the fixture role and generated plan in both item and episode snapshots.",
            "remaining_at_start": 60-budget.used, "operational_writes": False,
            "scope": "Repeat all new SNS lanes on the same card/plan/correction; preserve initial results."})
    try:
        cred = credential(args.credentials, args.character_id)
        cred.model, cred.thinking_level = "gemini-3.1-flash-lite", "high"
        settings.DAILY_PREPARATION_ENABLED = True
        for card in CARDS:
            path = args.output / (Path(card).stem + "-sns-probe.json")
            if path.exists(): continue
            previous = json.loads((args.output / (Path(card).stem + ".json")).read_text(encoding="utf-8"))
            plan = GeneratedDailyPlan.model_validate(previous["stages"]["new_initial"]["result"]["daily_plan"])
            fields = map_card(parse_card((args.cards/card).read_bytes())).fields
            persona = {key: fields.get(key) or "" for key in FIELDS}
            case = (Path(card).stem, "아까 한 말은 정정할게. 자료는 잃어버리지 않았어. 그리고 오늘은 무리하지 말고 쉬자.", "상대와 이미 인사를 나누었고, 자료 분실 여부는 확인되지 않았었다.")
            before = budget.used
            result = await evaluate(case, 0, 2, cred, SimpleNamespace(reserve=lambda:None),
                                    character_settings=persona, daily_plan=plan)
            write_json(path, {"card":card, "wire_calls":budget.used-before, "result":result})
            print(json.dumps({"card":card, "used":budget.used, "status":result["status"], "stages":{k:v["status"] for k,v in result["stages"].items()}}), flush=True)
    finally:
        direct_llm.RunLlmTracker.next_provider_call_order, direct_llm.get_provider_adapter = original_next, original_adapter
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sns-probe", action="store_true")
    args = parser.parse_args()
    asyncio.run(sns_probe(args) if args.sns_probe else run(args))
