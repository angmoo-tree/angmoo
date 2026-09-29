"""Opt-in daily/joint evaluation: separate file DBs, approved key, 60 wire calls.

Run with tests on PYTHONPATH. Credential volume must be mounted read-only.
This script starts no server/scheduler and never writes the operational World.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.characters.service.card_mapping import map_card
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.routines.contracts.plans import PlanScope
from app.domains.routines.models.preparation import ActivityPreparationJob
from app.domains.routines.schemas.daily_generation import GENERATION_CONTRACT
from app.domains.routines.service import daily_preparation as store
from app.domains.social.models.topics import RecommendationPreparation
from app.domains.social.service.recommendation_topics import mark_new_subject, replace_source_topics
from app.integrations.character_cards.parser import parse_card
from app.integrations.direct_llm import RunLlmTracker
from app.models import Base
from app.providers import gemini
from app.runtime import daily_preparation as runtime
from app.runtime.autonomous_activity.combined_lanes import CombinedInboxLane
from app.runtime.autonomous_activity.inputs import shared_input
from app.runtime.activity_proposals import composition as proposals
from app.runtime.persistence.model_registration import register_models
from scripts.evaluate_personalized_activity import credential
from tests.routines.test_daily_activity_runtime import _seed, _utc, _add_social_event
from tests.routines.test_daily_preparation import output
from tests.relationships.test_activity_proposals import _post, _record_post_event
from tests.characters.name_binding_fixture import create_profile
from model_fixture_support import models

MODEL, THINKING, CAP = "gemini-3.1-flash-lite", "high", 60


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


class Budget:
    def __init__(self, directory):
        self.path = directory / "budget.json"
        self.lock = Lock()
        self.value = json.loads(self.path.read_text()) if self.path.exists() else {"cap": CAP, "physical_requests": 0}
        if self.value["cap"] != CAP:
            raise ValueError("evaluation_budget_changed")
        self.original = gemini._generate_content_sync
        self.case = None
        wire_path = directory / "wire-requests.json"
        self.wires = json.loads(wire_path.read_text()) if wire_path.exists() else []

    def generate(self, request):
        with self.lock:
            if self.value["physical_requests"] >= CAP:
                raise ValueError("evaluation_budget_exhausted")
            self.value["physical_requests"] += 1
            write_json(self.path, self.value)
            wire = {"order": self.value["physical_requests"], "case": self.case,
                "model": request.model, "thinking": request.thinking_level,
                "system": request.system_prompt, "user": request.user_prompt, "schema": request.response_schema,
                "sdk_attempts": 1, "status": "reserved"}
            self.wires.append(wire)
            write_json(self.path.parent / "wire-requests.json", self.wires)
        if request.model != MODEL or request.thinking_level != THINKING:
            raise ValueError("approved_evaluation_model_mismatch")
        try:
            response = self.original(replace(request, sdk_attempts=1))
            wire.update(status="responded", raw=response.parsed if response.parsed is not None else response.text,
                usage=asdict(response.usage), finish_reason=response.finish_reason)
            return response
        except Exception as exc:
            wire.update(status="failed", error_type=type(exc).__name__,
                http_status=getattr(exc, "code", None) if isinstance(getattr(exc, "code", None), int) else None)
            raise
        finally:
            write_json(self.path.parent / "wire-requests.json", self.wires)


def engine_for(path):
    engine = create_engine(f"sqlite:///{path}")
    event.listen(engine, "connect", lambda raw, _: raw.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    return engine


def apply_card(character, fields):
    for key, value in fields.items():
        if hasattr(type(character), key) and key not in {"id", "owner_id", "handle"}:
            setattr(character, key, value)
    character.character_background = ""
    character.persona_summary = ""


def save_plan(db, world, ready, now):
    return store.apply_plan(db, scope=PlanScope(world, ready.membership, ready.world_character, ready.character),
        output=output(), target_date=now.astimezone(ZoneInfo(world.timezone)).date(),
        now=now, source_digest="a" * 64, expected_snapshot={})


def confirmed_reservation(db, world, first, second, now):
    for identity, actor, target, kind in (("fixture-proposed", first, second, "joint_proposed"),
                                         ("fixture-accepted", second, first, "joint_accepted")):
        _add_social_event(db, event_id=identity, world_id=world.id, actor_world_character_id=actor.world_character.id,
            target_world_character_id=target.world_character.id, event_type=kind, occurred_at=now)
    joint = models.JointActivity(id="fixture-reservation", world_id=world.id,
        activity_seed="저녁에 함께 정원에서 휴식하기", place_key=None, schedule_mode="exact",
        eligible_dayparts=["evening"], status="scheduled", scheduled_local_date=date.fromisoformat(
            now.astimezone(ZoneInfo(world.timezone)).date().isoformat()),
        target_daypart="evening", timezone_snapshot=world.timezone,
        source_proposal_event_id="fixture-proposed", source_acceptance_event_id="fixture-accepted",
        scheduled_start_at=store.daypart_windows(now.astimezone(ZoneInfo(world.timezone)).date(), world.timezone)["evening"][0],
        scheduled_end_at=store.daypart_windows(now.astimezone(ZoneInfo(world.timezone)).date(), world.timezone)["evening"][1], version=1)
    db.add(joint)
    db.flush()
    for ready, role in ((first, "proposer"), (second, "acceptor")):
        db.add(models.JointActivityParticipant(
            joint_activity_id=joint.id, world_id=world.id, world_character_id=ready.world_character.id,
            role=role, participation_status="scheduled"))
    db.flush()
    return joint


async def daily_case(args, case, fields):
    card, mode = case
    engine = engine_for(args.output / f"daily-{card}-{mode}.sqlite3")
    now = _utc(datetime.combine(datetime.now(UTC).date()+timedelta(days=7), datetime.min.time())+timedelta(hours=7))
    try:
        with Session(engine, expire_on_commit=False) as db:
            world, ready, peer = _seed(db, two_characters=True)
            apply_card(ready.character, fields)
            create_profile(db, world, ready.user.id, "Alex")
            world.name, world.tagline = "SNS", "캐릭터의 일상을 공유하는 공간"
            world.setting_description = "현대의 SNS 공간. 캐릭터는 자신의 원래 설정을 유지하며 일상 경험을 공유한다."
            world.daily_life_description = "쉬기, 취미, 공부, 돌봄, 대화와 탐색. 아직 실행하지 않은 계획은 경험이 아니다."
            from app.domains.worlds.models import WorldRole
            db.add(WorldRole(id="eval-role", world_id=world.id, role_key="student", name="주민"))
            mark_new_subject(db, world_id=world.id, world_character_id=ready.world_character.id)
            if mode == "reservation":
                confirmed_reservation(db, world, ready, peer, now)
            if mode in {"pinned-three", "all-preserved", "topics-only"}:
                plan = save_plan(db, world, ready, now)
                for item in store.current_items(db, plan.id)[:3 if mode == "pinned-three" else 4]:
                    item.is_user_pinned = True
            if mode != "initial" and mode != "topics-only":
                replace_source_topics(db, world_id=world.id, world_character_id=ready.world_character.id,
                    topics=[("기존 관심", "common")])
                prep = db.scalar(select(RecommendationPreparation).where(RecommendationPreparation.source_key == ready.world_character.id))
                prep.state, prep.applied_digest = "ready", "prior-topics"
            db.commit()
            result = await runtime.ensure_preparation(db, character_id=ready.character.id, world_id=world.id,
                user=ready.user, request_id=f"evaluation-{mode}", now=now)
            db.expire_all()
            plan = store.current_plan(db, ready.world_character.id, date.fromisoformat(result.local_date))
            job = db.scalar(select(ActivityPreparationJob))
            rows = store.current_items(db, plan.id) if plan else []
            valid = result.plan_state == "ready" and (mode == "all-preserved" or result.request_state == "ready")
            if valid:
                assert len(rows) == 4
                assert all(row.activity_kind != "joint_activity" and row.social_mode != "joint"
                    for row in rows if not row.joint_activity_id)
                if mode == "reservation":
                    assert sum(row.joint_activity_id is not None for row in rows) == 1
                if mode in {"initial", "topics-only"}:
                    assert result.topic_state == "ready"
            return {"status": "valid" if valid else "failed", "result": result.model_dump(mode="json"),
                "plan": store.plan_snapshot(db, plan), "input": job.input_snapshot if job else None,
                "usage": job.usage_snapshot if job else {"calls": []}, "provider_required": mode != "all-preserved"}
    finally:
        engine.dispose()


async def inbox_case(args, card, fields, credential_row):
    from app.domains.social.schemas.feed import JointActivityProposalPreview
    engine = engine_for(args.output / f"inbox-{card}.sqlite3")
    now = _utc(datetime.combine(datetime.now(UTC).date()+timedelta(days=7), datetime.min.time())+timedelta(hours=7))
    try:
        with Session(engine, expire_on_commit=False) as db:
            world, proposer, ready = _seed(db, two_characters=True)
            apply_card(ready.character, fields)
            create_profile(db, world, ready.user.id, "Alex")
            world.name, world.tagline = "SNS", "캐릭터의 일상을 공유하는 공간"
            world.setting_description = "현대의 SNS 공간. 캐릭터는 자신의 원래 설정을 유지하며 일상 경험을 공유한다."
            world.daily_life_description = "쉬기, 취미, 공부, 돌봄, 대화와 탐색. 아직 실행하지 않은 계획은 경험이 아니다."
            root = _post(db, post_id="evaluation-root", fixture=ready, body="오늘은 정원을 둘러보고 싶어.", created_at=now)
            original = _post(db, post_id="evaluation-proposal", fixture=proposer, body="오늘 저녁에 함께 정원에서 쉴래?",
                created_at=now, reply_to_post_id=root.id)
            proposal_event = _record_post_event(db, world_id=world.id, actor_world_character_id=proposer.world_character.id,
                target_world_character_id=ready.world_character.id, event_type="joint_proposed", source=original,
                target_post_id=root.id, root_post_id=root.id, occurred_at=now, idempotency_key="evaluation-proposal-event",
                interaction_intent="joint_activity_proposal")
            proposal = proposals.create_published_proposal(db,
                preview=JointActivityProposalPreview(text=original.body, source_post_id=root.id,
                    activity_seed="저녁에 함께 정원에서 휴식하기", target_world_character_id=ready.world_character.id,
                    place_key=None, target_daypart="evening", date_policy="exact", target_date=now.astimezone(ZoneInfo(world.timezone)).date()),
                proposal_comment=original, proposal_event=proposal_event, proposer_world_character_id=proposer.world_character.id, now=now)
            later = _post(db, post_id="evaluation-ordinary", fixture=proposer, body="참, 사진도 멋지더라.", created_at=now+timedelta(seconds=1), reply_to_post_id=root.id)
            db.add(models.CharacterActiveWorld(character_id=ready.character.id, world_character_id=ready.world_character.id,
                selected_at=now, idempotency_key="evaluation-active", version=1))
            for post in (original, later):
                db.add(models.Notification(world_id=world.id, recipient_character_id=ready.character.id,
                    recipient_world_character_id=ready.world_character.id, actor_character_id=proposer.character.id,
                    actor_world_character_id=proposer.world_character.id, notification_type="reply", post_id=root.id,
                    source_post_id=post.id, created_at=post.created_at))
            db.commit()
            tracker = RunLlmTracker(max_calls=8)
            ctx = SimpleNamespace(db=db, credential=credential_row, character=ready.character, user_id=ready.user.id,
                run_id=f"evaluation-inbox-{card}", generation_thinking_level=THINKING, generation_model=MODEL,
                on_rate_limit_wait=None, activity_policy=SimpleNamespace(allowed_actions={"reply", "like"}))
            async def guard(_):
                return {}
            adapter = CombinedInboxLane(ctx, actor=ready.world_character, lane="inbox", tracker=tracker,
                hybrid_service=None, guard=guard, ledger=SimpleNamespace(reserve=lambda _: None))
            state = await adapter.load({})
            assert len(state["candidates"]) == 2
            original_candidate = next(row for row in state["candidates"] if row["activity_proposal"])
            assert state["lane_data"][original_candidate["target_id"]]["post_id"] == original.id
            shared = shared_input(ctx, ready.world_character, world)
            # Supply actual available slots; the model may still reject/abstain.
            shared["available_schedule"] = {"local_date": str(now.astimezone(ZoneInfo(world.timezone)).date()),
                "available_dayparts": ["evening"], "timezone": world.timezone}
            state.update(identity={"contract_version": 2, "activity_id": ctx.run_id}, shared_context=shared,
                memories={}, memory_validations={}, generation_mode="combined")
            selected = await adapter.select(state)
            state.update(selected)
            # Selection is optional. Independently inspect proposal interpretation
            # with the real supplied original as the attention target.
            state["selections"] = [{"target_id": original_candidate["target_id"], "memory_query": "함께 정원에서 쉬자는 현재 초대"}]
            state.update(await adapter.context(state))
            state.update(await adapter.plan(state))
            state.update(await adapter.validate(state))
            state.update(await adapter.write(state))
            assert proposal.status == "proposed"  # A generated acceptance is not a reservation yet.
            return {"status": "valid", "selection": selected, "candidates": state["candidates"],
                "decision": state["decision"], "drafts": state["drafts"], "calls": tracker.calls,
                "public_execution": False, "reservation": False}
    finally:
        engine.dispose()


async def run(args):
    args.output.mkdir(parents=True, exist_ok=True)
    budget_directory = args.budget_directory or args.output
    budget_directory.mkdir(parents=True, exist_ok=True)
    lock_path = budget_directory / "active.lock"
    os.close(os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    try:
        cred = credential(args.credentials, args.character_id)
        material = CredentialResolver.resolve_llm_credential(cred, purpose=CredentialPurpose.RESIDENT_LLM,
            owner_id=cred.owner_id, character_id=cred.character_id)
        if (material.provider, material.model, material.thinking_level) != ("google", MODEL, THINKING):
            raise ValueError("approved_evaluation_credential_model_mismatch")
        register_models()
        fields, hashes = {}, {}
        for name in ("Seraphina", "Sakana", "FluxTheCat"):
            content = (args.cards / f"{name}.png").read_bytes()
            fields[name], hashes[name] = map_card(parse_card(content)).fields, sha256(content).hexdigest()
        budget = Budget(budget_directory)
        start_requests = budget.value["physical_requests"]
        write_json(args.output / "manifest.json", {"model": MODEL, "thinking": THINKING, "cap": CAP,
            "credential_character_id": args.character_id, "credential_id": material.credential_id,
            "credential_fingerprint": material.fingerprint, "card_sha256": hashes,
            "generation_contract": GENERATION_CONTRACT, "operational_writes": False,
            "sdk_attempts": 1, "scope": "Separate synthetic file DBs; generation/apply plus optional selection and forced-attention proposal interpretation."})
        records = []
        with patch.object(settings, "DAILY_PREPARATION_ENABLED", True), patch.object(CredentialResolver, "resolve_llm_credential", return_value=material), patch.object(gemini, "_generate_content_sync", budget.generate):
            cases = [(name, mode) for name in fields for mode in ("initial", "daily", "reservation", "pinned-three", "all-preserved", "topics-only")]
            for card, mode in [*cases, *((name, "inbox") for name in fields)]:
                case_id = f"{mode}-{card}"
                if args.cases and case_id not in args.cases:
                    continue
                target = args.output / f"{case_id}.json"
                if target.exists():
                    records.append(json.loads(target.read_text()))
                    continue
                budget.case = case_id
                before = budget.value["physical_requests"]
                try:
                    result = await (inbox_case(args, card, fields[card], cred) if mode == "inbox" else daily_case(args, (card, mode), fields[card]))
                except Exception as exc:
                    result = {"status": "failed", "error_type": type(exc).__name__}
                    for key in ("failure_class", "parse_error_type", "validation_code", "field_path"):
                        value = getattr(exc, key, None)
                        if value:
                            result[key] = value
                    if isinstance(exc, ValueError) and str(exc).replace("_", "").isalnum() and len(str(exc)) <= 90:
                        result["reason_code"] = str(exc)
                result.update(case=case_id, card=card, mode=mode, physical_requests=budget.value["physical_requests"]-before)
                write_json(target, result)
                records.append(result)
                print(json.dumps({key: result[key] for key in ("case", "status", "physical_requests")}), flush=True)
                if budget.value["physical_requests"] >= CAP:
                    break
        write_json(args.output / "summary.json", {"cap": CAP, "physical_requests": budget.value["physical_requests"],
            "this_run_requests": budget.value["physical_requests"] - start_requests,
            "cases": len(records), "valid": sum(row["status"] == "valid" for row in records),
            "failed": sum(row["status"] != "valid" for row in records), "records": [{key: row[key] for key in ("case", "status", "physical_requests")} for row in records]})
    finally:
        lock_path.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--cards", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--budget-directory", type=Path, help="Reuse the cumulative wire budget after implementation repairs.")
    parser.add_argument("--cases", nargs="+", help="Run only named cases; retain the same cumulative budget.")
    parser.add_argument("--real-ai-approved", action="store_true", required=True)
    asyncio.run(run(parser.parse_args()))
