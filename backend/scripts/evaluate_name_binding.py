"""Opt-in, isolated name-binding evaluation; one SDK attempt and durable 30-call cap.

Credential storage is read-only. Prompts use public card files and synthetic names,
Worlds and history. This checks generation, not natural activity or operational DBs.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from time import monotonic
from types import SimpleNamespace as View
from unittest.mock import patch

from app.contracts.name_binding import NameBindingSnapshot, NAME_BINDING_POLICY
from app.domains.characters.service.card_mapping import map_card
from app.domains.characters.service.prompt_persona import request_persona
from app.domains.characters.policies.authored_names import authored_routine_draft
from app.domains.characters.policies.name_macros import render_names
from app.domains.chat.contracts.character_response_generator import (
    CharacterResponseGeneratorRequest, CharacterResponseProfile, CharacterResponseContextMessage,
)
from app.domains.chat.contracts.evidence_bundle import EvidenceBundle, RetrievalOutcome, compute_evidence_hash
from app.domains.chat.contracts.retrieval_intent import RetrievalRoute
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.routine_posts.service.evidence import build_routine_prompt_context
from app.domains.routine_posts.service.original_post import validate_original_post
from app.domains.routines.client import generate_daily_preparation
from app.domains.routines.schemas.daily_generation import InitialPreparationOutput, DailyPreparationOutput
from app.domains.social.schemas.recommendation import TopicGenerationResult
from app.integrations import direct_llm
from app.integrations.character_cards.parser import parse_card
from app.integrations.llm.character_response_generator import _system_prompt, _user_prompt
from app.providers.contracts import ProviderRequest
from app.providers.diagnostics import structured_error_evidence
from app.providers.gemini import GeminiAdapter
from app.runtime.autonomous_activity.combined_provider import CombinedActivityProvider
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.generation_contracts import parse_routine_draft, parse_social_draft
from app.runtime.autonomous_activity.name_binding import social_draft_names, decision_names
from app.runtime.preparation_names import authored_preparation, authored_topics
from app.runtime.social.topic_preparation import generate_topics
from scripts.evaluate_personalized_activity import credential
from scripts.evaluate_routine_output_contract import fixture

MODEL, THINKING, CAP = "gemini-3.1-flash-lite", "high", 30


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


class Budget:
    def __init__(self, path):
        self.path = path
        self.value = json.loads(path.read_text()) if path.exists() else {"cap": CAP, "physical_requests": 0}
        if self.value["cap"] != CAP:
            raise ValueError("evaluation_budget_changed")

    def reserve(self):
        if self.value["physical_requests"] >= CAP:
            raise ValueError("evaluation_budget_exhausted")
        self.value["physical_requests"] += 1
        write_json(self.path, self.value)


class Captured(Exception):
    pass


async def capture(request):
    result = {}
    async def activity(_self, **kwargs):
        result.update(kwargs)
        raise Captured()
    async def direct(**kwargs):
        # Do not retain API key/material/context objects in evaluation artifacts.
        result.update(system=kwargs["system_prompt"], user=kwargs["user_prompt"],
            schema=kwargs["response_schema"], validator=kwargs["validator"], max_tokens=kwargs["max_output_tokens"])
        raise Captured()
    with patch.object(ActivityProvider, "call", activity), patch.object(direct_llm, "generate_json", direct):
        try:
            await request()
        except Captured:
            return result
    raise AssertionError("evaluation_capture_failed")


def cases():
    # Include unedited Sakana, all three originals, two Worlds, rename and raw history.
    routine = [("Sakana", "민식", "a"), ("Sakana", "민수", "a"),
        ("Sakana", "Alex", "b"), ("Seraphina", "민식", "a"), ("FluxTheCat", "Alex", "b")]
    for index, (card, name, world) in enumerate(routine):
        yield f"routine-{index}-{card}", "routine", card, name, world
    for lane, card, name, world in (("feed", "Sakana", "민식", "a"),
        ("inbox", "Sakana", "민수", "a"), ("feed", "FluxTheCat", "Alex", "b"),
        ("inbox", "Seraphina", "Seraphina", "b")):
        yield f"{lane}-{card}", lane, card, name, world
    for card, name, world in (("Sakana", "민식", "a"), ("Sakana", "민수", "a")):
        yield f"chat-{name}", "chat", card, name, world
    for lane, card, name in (("initial", "Sakana", "민식"), ("initial", "FluxTheCat", "Alex"),
        ("daily", "Seraphina", "민수"), ("topic", "Sakana", "민수")):
        yield f"{lane}-{card}", lane, card, name, "a"


async def prepare(case, raw, material):
    case_id, lane, card, name, world_key = case
    names = NameBindingSnapshot("evaluation-owner", "synthetic-world-" + world_key,
        "synthetic-actor", raw["name"], "synthetic-user-" + world_key, name,
        2 if name == "민수" else 1)
    persona = request_persona(raw, names)
    historical = "이전 게시글 원문: {{user}}, 오늘은 쉬는 날이야."
    actor = View(id="synthetic-actor", world_id=names.world_id)
    metadata = {"name_binding_policy": NAME_BINDING_POLICY, "name_binding": names.to_dict()}
    context, beat, common, replies = fixture("first-scene-0" if lane == "routine" else "source-2", 2, 4)
    character = View(id="synthetic-character", **raw)
    task = {"Sakana": ("업무 환경 점검", "오전 작업 공간에서 게임 장비와 오늘 업무 환경을 점검한다."),
            "Seraphina": ("식물 돌보기", "오전 정원에서 식물 상태를 조용히 살핀다."),
            "FluxTheCat": ("룸바에서 쉬기", "오전 룸바 위에서 창밖의 새를 바라보며 조용히 쉰다.")}[card]
    context.world.id = names.world_id
    context.item.title, context.item.activity_seed = task
    context.episode.effective_activity_snapshot.update(title=task[0], activity_seed=task[1])
    context = replace(context, character=character, name_binding=names,
        source_events=tuple(replace(event, excerpt=historical) for event in context.source_events))
    common.update(persona=persona, persona_interpretation="Read the full description with supplied optional details.",
        routine=build_routine_prompt_context(context, as_of_utc=context.due_tick.scheduled_for),
        current_state={"known": True, "mood": "calm", "mood_intensity": 30, "state_note": "현재는 오전이다.", "version": 1})
    # The same lookup contract used by Routine resolves the accepted frozen namespace.
    ctx = View(db=View(get=lambda *_: View(result=metadata)), run_id=beat.claim_run_id)
    provider = CombinedActivityProvider(ctx, direct_llm.RunLlmTracker(max_calls=1), ledger=None)
    if lane == "routine":
        routine = RoutineLane.__new__(RoutineLane)
        routine.ctx, routine.actor, routine.prepared, routine.provider = ctx, actor, View(context=context, beat=beat), provider
        captured = await capture(lambda: routine.plan({"decision_context": common,
            "candidates": [{"target_id": "item", "source_ids": [], "allowed_actions": ["post"]}]}))
        def validate(value):
            decision = captured["validator"](value)
            draft = parse_routine_draft(authored_routine_draft(decision["provisional_draft"], names))
            validate_original_post(title=draft["title"], body=draft["body"], completed_replies=replies)
            return {"plan": decision["plan"], "draft": draft}
    elif lane in {"feed", "inbox"}:
        candidate = {"target_id": "post-1", "counterpart_id": "other-character",
            "source_ids": ["source-0"], "allowed_actions": ["comment"],
            "text": "Seraphina가 쓴 글: 오늘 정원에 새가 왔어요. 어떻게 바라보셨나요? " + historical}
        captured = await capture(lambda: provider.plan(lane=lane, context=common, candidates=[candidate]))
        def validate(value):
            decision = decision_names(captured["validator"](value), names, candidates=[candidate])
            assignments = [{"task_id": "task-1", "source": candidate}]
            if not any(item["action"] == "comment" for item in decision["decisions"]):
                assignments = []
            draft = social_draft_names(decision["provisional_draft"], names, assignments=assignments, combined=True, lane=lane)
            return {"decisions": decision["decisions"], "draft": parse_social_draft(draft, lane=lane, assignments=assignments)}
    elif lane == "chat":
        profile = CharacterResponseProfile(name=persona["name"], handle="evaluation", worldview=persona["description"],
            **{key: persona[key] for key in ("one_liner", "personality", "speech_style", "topic_preferences", "safety_rules", "character_background")})
        evidence_values = dict(request_id=case_id, request_scope_hash="a" * 64,
            route=RetrievalRoute.CURRENT_CONTEXT, retrieval_outcome=RetrievalOutcome.NO_EVIDENCE,
            items=(), partial_axes=(), degraded_reason=None, clarification_slot=None)
        evidence = EvidenceBundle(**evidence_values, evidence_hash=compute_evidence_hash(**evidence_values))
        request = CharacterResponseGeneratorRequest("오늘 기분은 어때? 나를 이름으로 한 번 불러 줘.", profile,
            (CharacterResponseContextMessage("assistant", historical),), evidence)
        captured = {"system": _system_prompt(request), "user": _user_prompt(request), "schema": None, "max_tokens": 4096}
        def validate(value):
            return {"text": render_names(value, names, output=True, recipient_id=names.user_world_character_id, limit=16000).text}
    else:
        source = {"persona": persona, "world": {"name": "SNS", "timezone": "Asia/Seoul",
            "setting_description": "현대적인 일상 SNS", "places": []},
            "local_date": "2026-09-29", "now": "2026-09-29T10:00:00+09:00",
            "allowed_places": {part: [] for part in ("dawn", "morning", "afternoon", "evening")},
            "fixed_items": [], "recent_activity": {"records": [{"summary": historical}]},
            "current_state": common["current_state"], "confirmed_reservations": []}
        if lane == "topic":
            captured = await capture(lambda: generate_topics(material, "evaluation", source))
            validate = lambda value: authored_topics(TopicGenerationResult.model_validate(value), names).model_dump(mode="json")
        else:
            captured = await capture(lambda: generate_daily_preparation(material=material, character_id="evaluation",
                source=source, initial=lane == "initial", reserve=lambda: None, reserve_json_retry=lambda: None))
            def validate(value):
                output = captured["validator"](value)
                return authored_preparation(output, names).model_dump(mode="json")
    user = captured.get("user") or json.dumps(captured["payload"], ensure_ascii=False, default=str)
    return names, captured, user, validate


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    lock = args.output / "active.lock"
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    try:
        material = None
        if not args.dry_run:
            cred = credential(args.credentials, args.character_id)
            material = CredentialResolver.resolve_llm_credential(cred, purpose=CredentialPurpose.RESIDENT_LLM,
                owner_id=cred.owner_id, character_id=cred.character_id)
            if material.provider != "google" or material.model != MODEL or material.thinking_level != THINKING:
                raise ValueError("approved_evaluation_credential_model_mismatch")
        else:
            material = View(provider="google", model=MODEL, thinking_level=THINKING,
                credential_id="dry-run", fingerprint="dry-run", reveal=lambda: "not-a-key")
        card_fields, hashes = {}, {}
        for name in ("Sakana", "Seraphina", "FluxTheCat"):
            content = (args.cards / (name + ".png")).read_bytes()
            fields = map_card(parse_card(content)).fields
            card_fields[name] = {**fields, "character_background": "", "persona_summary": ""}
            hashes[name] = sha256(content).hexdigest()
        budget = Budget(args.output / "budget.json")
        write_json(args.output / "manifest.json", {"model": MODEL, "thinking_level": THINKING, "cap": CAP,
            "sdk_attempts": 1, "normal_cases": 15, "credential_character_id": args.character_id,
            "card_sha256": hashes, "dry_run": args.dry_run, "operational_writes": False,
            "scope": "Generation using actual prompt/schema builders; local tests separately verify lifecycle/storage."})
        with sqlite3.connect(args.output / "evaluation.sqlite3") as db:
            db.execute("CREATE TABLE IF NOT EXISTS accepted_cases (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, input_hash TEXT NOT NULL)")
            for case in cases():
                case_id, lane, card, _, _ = case
                path = args.output / (case_id + ".json")
                if not args.dry_run and path.exists() and json.loads(path.read_text()).get("status") == "valid":
                    continue
                names, captured, user, validate = await prepare(case, card_fields[card], material)
                request_hash = sha256((captured["system"] + user).encode()).hexdigest()
                existing = db.execute("SELECT snapshot,input_hash FROM accepted_cases WHERE id=?", (case_id,)).fetchone()
                accepted = (json.dumps(names.to_dict(), ensure_ascii=False, sort_keys=True), request_hash)
                if existing and existing != accepted:
                    raise ValueError("evaluation_frozen_request_changed")
                db.execute("INSERT OR IGNORE INTO accepted_cases VALUES (?,?,?)", (case_id, *accepted)); db.commit()
                record = {"case": case_id, "lane": lane, "card": card, "binding": names.to_dict(),
                    "request_hash": request_hash, "system": captured["system"], "user": user,
                    "schema": captured["schema"], "status": "dry_run"}
                if not args.dry_run:
                    budget.reserve()
                    record["physical_request"] = budget.value["physical_requests"]
                    started = monotonic()
                    try:
                        request = ProviderRequest(api_key=material.reveal(), model=MODEL,
                            system_prompt=captured["system"], user_prompt=user, response_schema=captured["schema"],
                            response_mime_type="application/json" if captured["schema"] else None,
                            thinking_level=THINKING, max_output_tokens=max(8192, captured["max_tokens"]),
                            timeout_seconds=120, sdk_attempts=1)
                        response = await (GeminiAdapter().generate_json(request) if captured["schema"] else GeminiAdapter().generate_text(request))
                        raw = response.parsed if response.parsed is not None else (json.loads(response.text) if captured["schema"] else response.text)
                        record.update(raw=raw, finish_reason=response.finish_reason, usage=asdict(response.usage))
                        record["validated"] = validate(raw)
                        record["status"] = "valid"
                    except Exception as exc:
                        record.update(status="failed", error_type=type(exc).__name__,
                            diagnostic=structured_error_evidence([("exception", getattr(exc, "response_json", None))]),
                            provider_http_status=getattr(exc, "code", None) if type(getattr(exc, "code", None)) is int else None)
                        # Fixed validation codes only; never arbitrary exception/credential text.
                        if isinstance(exc, ValueError) and str(exc).replace("_", "").isalnum() and len(str(exc)) <= 90:
                            record["reason_code"] = str(exc)
                    record["elapsed_seconds"] = round(monotonic() - started, 2)
                write_json(path, record)
                print(json.dumps({"case": case_id, "status": record["status"], "physical_requests": budget.value["physical_requests"]}), flush=True)
        records = [json.loads(path.read_text()) for path in args.output.glob("*.json") if path.name not in {"manifest.json", "budget.json", "summary.json"}]
        write_json(args.output / "summary.json", {"physical_requests": budget.value["physical_requests"],
            "valid": sum(row.get("status") == "valid" for row in records),
            "failed": sum(row.get("status") == "failed" for row in records), "cap": CAP})
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    asyncio.run(run(parser.parse_args()))
