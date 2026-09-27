"""Capped, isolated real-provider probe for description-first character settings.

No application DB writes, scheduler, retrieval, publication, or graph projection.
The canonical Docker data root is opened read-only only to resolve one existing
Gemini credential. Results belong in an untracked diagnostics directory.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, replace
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.characters import models, schemas
from app.domains.characters.service import card_import, drafts
from app.domains.chat.contracts.character_response_generator import CharacterResponseGeneratorRequest
from app.domains.chat.service.profiles import _response_profile
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.models import InstallationIdentity, User
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.world_characters import client as setup_client
from app.domains.world_characters.models import WorldCharacter
from app.domains.world_characters.service import setup_validation
from app.domains.worlds.models import World
from app.domains.worlds.service import build_world_generation_context
from app.integrations import direct_llm
from app.integrations.llm.character_response_generator import DirectLlmCharacterResponseGenerator
from app.runtime.characters.creator import build_creator_workflows
from app.runtime.persistence.model_registration import register_models
from scripts.evaluate_creator_cards import empty_evidence
from scripts.evaluate_four_call_activity import evaluate, resolve_credential


MODEL = "gemini-3.1-flash-lite"
CAP = 60
THINKING = "high"
FIELDS = ("name", "one_liner", "personality", "speech_style", "worldview",
          "character_background", "topic_preferences", "safety_rules")
BASE = "민서는 작은 서점을 운영하며 손님을 존중한다."
SPEECH = "평소 한국어 존댓말로 짧게 말하며 책 이야기는 자세하게 설명한다."
BACKGROUND = "바닷가 마을에서 자랐고 오래된 지도 한 장을 간직한다."
INTEREST = "고서, 항구의 역사, 오래된 지도에 관심이 많다."
AVOID = "확인하지 못한 소문을 사실처럼 전하지 않는다."
CASES = (
    ("synthetic-description", None, {"name": "민서", "worldview": "\n".join((BASE, SPEECH, BACKGROUND, INTEREST, AVOID))}),
    ("synthetic-separated", None, {"name": "민서", "worldview": BASE,
        "speech_style": SPEECH, "character_background": BACKGROUND,
        "topic_preferences": INTEREST, "safety_rules": AVOID}),
    ("Seraphina", "Seraphina.png", None),
    ("Sakana", "Sakana.png", None),
    ("FluxTheCat", "FluxTheCat.png", None),
)
EDGE_CASES = (
    ("separate-background-conflict", {"name": "아린",
        "worldview": "아린은 옛 항구 도시 출신이며 차분하게 존댓말로 말한다.",
        "character_background": "아린은 산속 기록소에서 태어나고 자랐다."},
        "어디에서 태어나고 자랐어?"),
    ("description-and-background-tail", {"name": "지오",
        "worldview": "지오는 관찰 기록가이다. " + "기록을 정리한다. " * 450
            + "대화에서는 짧은 존댓말을 쓰고 확인되지 않은 소문은 전하지 않는다.",
        "character_background": "여러 곳을 다녔다. " + "낡은 장부를 보관한다. " * 400
            + "현재 World에 오기 전에는 바닷가 마을에서 살았다."},
        "말투와 이전 거주지를 간단히 알려줘."),
    ("fictional-history-boundary", {"name": "리안",
        "worldview": "리안은 다른 이야기 속에서 용을 만났다는 설정을 가진 인물이다. 현재 World에서 실제로 만난 적은 없다.",
        "character_background": "옛 이야기의 숲에 살았다는 카드 설정이 있다."},
        "이곳에서 실제로 용을 만난 적이 있어?"),
    ("quiet-character", {"name": "토리",
        "worldview": "토리는 조용하고 말을 아끼는 인물이다. 물음에는 짧게 대답한다."},
        "오늘 무슨 생각을 하고 있어?"),
)


def write_json(path: Path, value: object) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2,
        default=lambda item: item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item)), encoding="utf-8")
    os.replace(temp, path)


class DurableBudget:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            old = json.loads(path.read_text(encoding="utf-8"))
            if old["cap"] != CAP:
                raise ValueError("evaluation_cap_changed")
            self.used = int(old["reserved_physical_requests"])
        else:
            self.used = 0
            write_json(path, {"cap": CAP, "reserved_physical_requests": 0})

    def reserve(self) -> None:
        if self.used >= CAP:
            raise direct_llm.DirectLlmMaxCallsExceeded("evaluation_request_cap_reached")
        self.used += 1
        write_json(self.path, {"cap": CAP, "reserved_physical_requests": self.used})


class OneSdkAttempt:
    """Force one SDK HTTP attempt so the tracker accounts for every request."""

    def __init__(self, adapter):
        self.adapter = adapter
        self.capabilities = adapter.capabilities

    async def generate_json(self, request):
        return await self.adapter.generate_json(replace(request, sdk_attempts=1))

    async def generate_text(self, request):
        return await self.adapter.generate_text(replace(request, sdk_attempts=1))

    def normalize_error(self, *args, **kwargs):
        return self.adapter.normalize_error(*args, **kwargs)


def _error(exc: Exception) -> dict[str, object]:
    return {"status": "failed", "class": type(exc).__name__,
            "reason_code": getattr(exc, "reason_code", None),
            "failure_class": getattr(exc, "failure_class", None)}


async def _case(name: str, card_name: str | None, edits: dict[str, str] | None,
                *, cards: Path, material, credential, edge_question: str | None = None) -> dict[str, object]:
    engine = create_engine("sqlite://")
    register_models().create_all(engine)
    row: dict[str, object] = {"case": name, "stages": {}}
    settings.MEDIA_ROOT = str(cards.parent / "isolated-description-eval-media")
    try:
        with Session(engine, expire_on_commit=False) as db:
            owner = User(id="evaluation-owner", display_name="Evaluation")
            db.add(owner)
            db.flush()
            db.add(InstallationIdentity(singleton_key="local-installation", installation_id="description-evaluation",
                owner_user_id=owner.id, bootstrap_state="claimed", claimed_at=datetime.now(UTC)))
            db.commit()
            workflows = build_creator_workflows()
            draft = await drafts.create_draft(db, owner, schemas.AgentCreationDraftCreate(), workflows=workflows)
            if card_name:
                imported = card_import.import_card(db, owner, draft.id, revision=draft.revision,
                    content=(cards / card_name).read_bytes(), workflows=workflows)
                current = imported["draft"]
                row["card_review"] = imported["review"]
                row["card_version"] = imported["card_version"]
            else:
                current = drafts.update_draft(db, owner, draft.id,
                    schemas.AgentCreationDraftUpdate(revision=draft.revision, **(edits or {})), workflows=workflows)
            if not current.worldview.strip():
                row["stages"]["registration"] = {"status": "description_required"}
                return row
            detail = drafts.complete_draft(db, owner, draft.id,
                schemas.AgentCreationDraftComplete(revision=current.revision), workflows=workflows)
            character = db.get(models.Character, detail.character.id)
            actor = db.scalar(select(WorldCharacter).where(WorldCharacter.character_id == character.id))
            world = db.get(World, actor.world_id)
            row["stages"]["registration"] = {"status": "valid", "autonomous_enabled": actor.autonomous_enabled,
                "description_chars": len(character.worldview), "background_chars": len(character.character_background),
                "personality_chars": len(character.personality)}
            setting = {key: getattr(character, key) for key in FIELDS}
            context = build_world_generation_context(db, world)
            generation_input = setup_validation.build_world_character_generation_input(
                character=character, world_character=actor, world_context=context)
            provider = setup_client.DirectLlmWorldCharacterSetupProvider()
            try:
                profile = await provider.generate_community_profile(material=material,
                    character_id=character.id, generation_input=generation_input)
                row["stages"]["profile"] = {"status": "valid", "result": asdict(profile)}
                if edge_question is None:
                    try:
                        repertoire = await provider.generate_repertoire(material=material,
                            character_id=character.id, generation_input=generation_input,
                            community_profile=profile.payload,
                            validator=lambda value: setup_validation.validate_activity_repertoire(
                                value, world_context=context, world_character=actor))
                        row["stages"]["repertoire"] = {"status": "valid", "result": asdict(repertoire)}
                    except Exception as exc:
                        row["stages"]["repertoire"] = _error(exc)
            except Exception as exc:
                row["stages"]["profile"] = _error(exc)
            if edge_question is None:
                try:
                    social = await evaluate(("ordinary", "오늘 오래된 책을 정리하고 있어. 관심 있는 이야기가 있니?", ""),
                        0, 2, credential, SimpleNamespace(reserve=lambda: None), character_settings=setting)
                    row["stages"]["sns"] = social
                except Exception as exc:
                    row["stages"]["sns"] = _error(exc)
            try:
                chat = DirectLlmCharacterResponseGenerator(replace(material, purpose=CredentialPurpose.MESSAGE_LLM))
                answer = await chat.generate(CharacterResponseGeneratorRequest(
                    user_message=edge_question or "안녕! 요즘 관심 있는 일은 무엇이야?",
                    profile=_response_profile(character), recent_context=(), evidence=empty_evidence()))
                row["stages"]["chat"] = {"status": "valid", "result": asdict(answer)}
            except Exception as exc:
                row["stages"]["chat"] = _error(exc)
            return row
    finally:
        engine.dispose()


async def run(args) -> None:
    args.output.mkdir(parents=True, exist_ok=True)
    budget = DurableBudget(args.output / "budget.json")
    lock = args.output / "active.lock"
    lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(lock_fd)
    original_next = direct_llm.RunLlmTracker.next_provider_call_order
    original_adapter = direct_llm.get_provider_adapter
    trackers: list[direct_llm.RunLlmTracker] = []
    usage_path = args.output / "usage.json"
    previous_usage = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else {"calls": []}
    def counted(tracker):
        budget.reserve()
        if not any(existing is tracker for existing in trackers):
            trackers.append(tracker)
        return original_next(tracker)
    direct_llm.RunLlmTracker.next_provider_call_order = counted
    direct_llm.get_provider_adapter = lambda provider, model: OneSdkAttempt(original_adapter(provider, model))
    try:
        cards = [{"name": name, "sha256": hashlib.sha256((args.cards / name).read_bytes()).hexdigest()}
                 for name in ("Seraphina.png", "Sakana.png", "FluxTheCat.png")]
        manifest = {"run_id": args.output.name, "model": MODEL, "thinking": THINKING,
            "max_physical_requests": CAP, "main_evaluation_target": 48, "recovery_reserve": 12,
            "sdk_attempts": 1, "cards": cards,
            "cases": ([{"id": name, "planned_stages": ["registration:0", "profile:1-2", "repertoire:2-4", "sns:0-15", "chat:1-2"]}
                       for name, _, _ in CASES]
                      + [{"id": name, "planned_stages": ["registration:0", "profile:1-2", "chat:1-2"]}
                         for name, _, _ in EDGE_CASES]),
            "same_information_pair": ["synthetic-description", "synthetic-separated"],
            "operational_writes": False, "canonical_database_mode": "read-only credential lookup",
            "limitations": ["Synthetic World, inbox, feed, routine and chat evidence; no live publication or retrieval.",
                "The three card cases use mapped fields as imported, without personality, speech or interest edits."]}
        manifest_path = args.output / "manifest.json"
        if manifest_path.exists():
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            if prior != manifest:
                raise ValueError("evaluation_manifest_changed")
        else:
            write_json(manifest_path, manifest)
        credential = resolve_credential(args.credentials)
        if credential.model != MODEL:
            raise ValueError("evaluation_model_unavailable")
        credential.thinking_level = THINKING
        material = CredentialResolver.resolve_llm_credential(
            credential, purpose=CredentialPurpose.WORLD_CHARACTER_SETUP_LLM)
        results_path = args.output / "results.json"
        results = json.loads(results_path.read_text(encoding="utf-8")) if results_path.exists() else []
        completed = {item["case"] for item in results}
        planned = [(name, card_name, edits, None) for name, card_name, edits in CASES]
        planned.extend((name, None, edits, question) for name, edits, question in EDGE_CASES)
        if args.recheck is not None:
            planned = [(f"recheck:{name}", card_name, edits, question)
                       for name, card_name, edits, question in planned if name == args.recheck]
        for name, card_name, edits, edge_question in planned:
            if name in completed or budget.used >= CAP or (
                args.recheck is None and edge_question is not None and budget.used >= 48
            ):
                continue
            before = budget.used
            try:
                row = await _case(name, card_name, edits, cards=args.cards,
                                  material=material, credential=credential, edge_question=edge_question)
            except Exception as exc:
                row = {"case": name, "stages": {"setup": _error(exc)}}
            row["physical_requests_reserved"] = budget.used - before
            results.append(row)
            write_json(results_path, results)
            print(json.dumps({"case": name, "requests": row["physical_requests_reserved"],
                "total_reserved": budget.used,
                "statuses": {key: value.get("status") for key, value in row["stages"].items()}},
                ensure_ascii=False), flush=True)
    finally:
        direct_llm.RunLlmTracker.next_provider_call_order = original_next
        direct_llm.get_provider_adapter = original_adapter
        allowed = {"node", "lane", "status", "duration_ms", "usage", "thinking_level",
                   "max_output_tokens", "finish_reason", "failure_class", "estimated_cost_usd"}
        write_json(usage_path, {"physical_requests_reserved": budget.used,
            "calls": previous_usage["calls"] + [
                {key: value for key, value in call.items() if key in allowed}
                for tracker in trackers for call in tracker.calls
            ]})
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--recheck", choices=[name for name, _, _ in CASES]
                        + [name for name, _, _ in EDGE_CASES])
    asyncio.run(run(parser.parse_args()))
