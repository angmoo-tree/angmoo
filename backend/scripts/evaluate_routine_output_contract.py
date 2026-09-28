"""Opt-in 40+8+12 wire-request Routine evaluation; canonical credential DB is read-only."""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from importlib.metadata import version
import json
import os
from pathlib import Path
from time import monotonic
from types import SimpleNamespace as View

from pydantic import Field, create_model

from app.contracts.activity_thought import THOUGHT_PROMPT
from app.domains.identity.contracts import CredentialPurpose
from app.domains.identity.service.credential_resolution import CredentialResolver
from app.domains.routine_posts import schemas
from app.domains.routine_posts.contracts.context import RoutinePostContext
from app.domains.routine_posts.contracts.interaction import RoutineInteractionInput
from app.contracts.routine_output import ENUM_OUTPUT, LEGACY_OUTPUT
from app.domains.routine_posts.service.evidence import _validate_plan, _state_after, build_routine_prompt_context, allowed_continuity_facts, allowed_detail_keys
from app.domains.routine_posts.service.original_post import ORIGINAL_POST_INSTRUCTIONS, validate_original_post
from app.domains.routines.contracts.lifecycle import DueTick
from app.domains.routines.policies.activity_state import initial_state, apply_state_changes
from app.runtime.autonomous_activity.routine import RoutineLane
from app.runtime.autonomous_activity.generation_contracts import draft_schema, envelope_schema, parse_routine_draft
from app.runtime.autonomous_activity.planner_contract import parse_action
from app.providers.contracts import ProviderRequest
from app.providers.gemini import GeminiAdapter
from app.providers.diagnostics import schema_evidence, structured_error_evidence
from scripts.evaluate_personalized_activity import credential

MODEL, THINKING, CAP = "gemini-3.1-flash-lite", "high", 60
STAGES = ("baseline", "remove_self_view", "remove_effect_classification", "bind_server_metadata", "energy_free")
CASES = (("source-0", 0), ("source-2", 2), ("self-reply-4", 4), ("relationship-5", 5),
         ("long-id-7", 7), ("unknown-state-8", 8), ("tired-but-joyful", 4), ("morning-night-conflict", 8))
LEGACY_FIELDS = {"motivation_kind", "motivation_text", "emotion_label", "emotion_text", "emotion_intensity"}
META_FIELDS = {"episode_id", "beat_id", "sequence_no", "considered_source_event_ids"}
LegacyStateEffect = create_model("EvaluationLegacyStateEffect", __base__=schemas.RoutineSourceEventEffectV2,
    state_change=(schemas.RoutineStateChange, Field(default_factory=schemas.RoutineStateChange)))
LegacyStateDecision = create_model("EvaluationLegacyStateDecision", __base__=schemas.RoutineDecisionOutput,
    source_event_effects=(list[LegacyStateEffect], Field(default_factory=list, max_length=8)))
LegacyStateBound = create_model("EvaluationLegacyStateBound", __base__=schemas.BoundRoutinePlan,
    source_event_effects=(list[LegacyStateEffect], Field(default_factory=list, max_length=8)))


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temp.replace(path)


class Budget:
    def __init__(self, path):
        self.path = path
        self.value = json.loads(path.read_text()) if path.exists() else {"cap": CAP, "physical_requests": 0, "reserve_requests": 0}
        if self.value["cap"] != CAP:
            raise ValueError("evaluation_budget_changed")

    def reserve(self, *, recovery=False):
        if self.value["physical_requests"] >= CAP or (recovery and self.value["reserve_requests"] >= 12):
            raise ValueError("evaluation_budget_exhausted")
        self.value["physical_requests"] += 1
        self.value["reserve_requests"] += int(recovery)
        write_json(self.path, self.value)


def fixture(case_id, count, stage):
    now = datetime(2026, 8, 10, 1, 16, tzinfo=UTC)
    world = View(id="synthetic-world", name="기록가들의 SNS", tagline="일상을 나누는 공간", setting_description="현대적인 작은 마을", daily_life_description="각자 자신의 실제 일상을 공유한다.", tone_tags=["일상"], timezone="Asia/Seoul")
    character = View(id="synthetic-character", name="민서", worldview="신중한 기록가 민서. 고양이와 오래된 지도 이야기를 좋아하고 한국어 존댓말로 차분하게 말한다.", character_background="바닷가 마을 출신.", personality="확인되지 않은 소문을 사실로 쓰지 않는다.", speech_style="짧고 정중한 한국어", topic_preferences="지도, 고양이", safety_rules="상대의 정정과 거절을 존중한다.", persona_summary="신중한 기록가")
    old_state = initial_state()
    if case_id == "tired-but-joyful":
        old_state.update(mood="joyful", mood_intensity=45, energy=10, social_energy=12, action_note="피곤하지만 친구를 만나 기쁘다.")
    if case_id == "morning-night-conflict":
        old_state.update(mood="calm", mood_intensity=30, action_note="오늘 밤 내일의 훈련을 준비하고 잠자리에 들려고 한다.")
    state = {k: v for k, v in old_state.items() if stage == 0 or stage < 4 or k not in {"energy", "social_energy"}}
    events = tuple(RoutineInteractionInput(source_event_id=("event-" + str(index) + "-" + "x" * 44 if case_id == "long-id-7" else f"event-{index}"),
        world_id=world.id, consumer_world_character_id="synthetic-actor", actor_world_character_id="partner",
        excerpt=("정정할게. 자료는 잃어버리지 않았어. 새 지도가 있어." if index == 0 else "지금은 오전이야. 오후 계획은 아직 실행하지 않았어."),
        occurred_at=now-timedelta(minutes=index+1), directness=100, episode_relevance=80, relationship_band="familiar") for index in range(count))
    episode = View(id="synthetic-episode", version=1, effective_activity_snapshot={"title": "지도 정리", "activity_seed": "작업대에서 오래된 지도 분류", "daypart": "morning"})
    previous_body = "오전 작업대에 지도를 펼쳐 날짜를 확인했습니다."
    if case_id == "morning-night-conflict":
        previous_body = "하루를 마치고 잠자리에 들 준비를 합니다. 내일 훈련을 떠올립니다."
    previous = View(id="previous-root", created_at=now-timedelta(minutes=30), title="지도 기록", body=previous_body, topic_signature="지도 정리")
    context = RoutinePostContext(world=world, membership=View(id="membership"), world_character=View(id="synthetic-actor", local_profile={}), character=character,
        profile=None, plan=View(id="plan", version=1, local_date=date(2026,8,10), timezone_name="Asia/Seoul"),
        item=View(id="item", daypart="morning", activity_kind="study", title="지도 정리", activity_seed="오전 작업대에서 지도를 날짜별로 분류한다.", social_mode="solo", place_key=None,
            scheduled_start_at=now-timedelta(hours=3,minutes=16), scheduled_end_at=now+timedelta(hours=1,minutes=44)),
        episode=episode, due_tick=DueTick(now, 0), previous_beat=View(id="previous-beat", sequence_no=1, result_snapshot={"scene_brief": "오전 지도 정리를 시작했다."}), previous_post=previous,
        state_before=state, source_events=events, eligible_event_count=count, overflow_reason_counts={}, prompt_comment_chars=100*count,
        output_contract=ENUM_OUTPUT if stage==4 else LEGACY_OUTPUT, state_schema_version=2 if stage==4 else 1)
    beat=View(id="synthetic-beat", sequence_no=2, claim_run_id="synthetic-activity", status="claimed", state_schema_version=context.state_schema_version)
    if case_id == "first-scene-0":
        context=replace(context, previous_beat=None, previous_post=None)
        beat.sequence_no=1
    replies=[{"post_id":"own-reply", "title":"Re: 햇살 가득한 오후의 인사", "body":"따뜻한 기운 가득한 시간 되길 바랄게요!", "purpose":"already_published_reply"}] if case_id in {"self-reply-4", "morning-night-conflict"} else []
    common={"known":case_id!="unknown-state-8", "mood": state["mood"] if case_id!="unknown-state-8" else None, "mood_intensity":state["mood_intensity"] if case_id!="unknown-state-8" else None,
        "state_note":state["action_note"] if case_id!="unknown-state-8" else None,"version":1}
    manifest=[{"post_id":f"source-{i}","target_ref":"partner","revision":"r1","created_at":e.occurred_at.isoformat()} for i,e in enumerate(events)]
    decision_context={"routine":build_routine_prompt_context(context, as_of_utc=now), "current_state":common, "now":now.isoformat(),
        "persona":{"description":character.worldview}, "today_activity":{"records":[{"summary":r["body"], "kind":"reply", "title":r["title"]} for r in replies]},
        "completed_social_replies":replies, "memories":{"routine":{"packets":[{"ref":"memory-1","text":"상대가 자료를 잃어버렸다는 것은 정정됐다. 상대는 믿을 만한 기록가이다."}]}},
        "relationships":{"partner":{"affinity":"friendly","trust":"trusted","tension":"low"}}, "source_manifest":manifest,
        "metric_sources":[{"source_ref":r["post_id"],"target_ref":"partner","text":e.excerpt} for r,e in zip(manifest,events)]}
    return context,beat,decision_context,replies


class Captured(Exception):
    pass


async def request_parts(context, beat, decision_context):
    captured={}
    class CaptureProvider:
        async def call(self, **kwargs):
            captured.update(kwargs)
            raise Captured()
    lane=RoutineLane.__new__(RoutineLane)
    lane.prepared=View(context=context,beat=beat)
    lane.provider=CaptureProvider()
    try:
        await lane.plan({"decision_context":decision_context,"candidates":[{"target_id":"item","source_ids":[],"allowed_actions":["post"]}]})
    except Captured:
        return captured
    raise AssertionError("evaluation_capture_failed")


def stage_schema(schema, stage):
    result=deepcopy(schema)
    props=result["properties"]
    if stage>=1:
        for key in LEGACY_FIELDS: props.pop(key,None)
    if stage>=2:
        effect=props["source_event_effects"]["items"]
        for key in ("effect","intensity"): effect["properties"].pop(key,None)
        effect["required"]=[k for k in effect.get("required",[]) if k not in {"effect","intensity"}]
    if stage>=3:
        for key in META_FIELDS: props.pop(key,None)
    result["required"]=[k for k in result.get("required",[]) if k in props]
    return envelope_schema(result,"routine")


def validate_decision(value, context, beat, stage):
    if not isinstance(value,dict) or not isinstance(value.get("decision"),dict):
        raise ValueError("decision_missing")
    decision=dict(value["decision"])
    aux={key:decision.pop(key) for key in ("state_update","state_source_refs","relationship_metrics") if key in decision}
    parse_action({"decisions":[],**aux}, [{"target_id":"item","source_ids":[f"source-{i}" for i in range(len(context.source_events))],"allowed_actions":["post"]}])
    if stage<=1:
        plan=_validate_plan(decision,context=context,beat=beat)
    elif stage in {2,3}:
        choice=LegacyStateDecision.model_validate({k:v for k,v in decision.items() if k not in META_FIELDS})
        metadata={"episode_id":context.episode.id,"beat_id":beat.id,"sequence_no":beat.sequence_no,"considered_source_event_ids":context.considered_source_event_ids}
        plan=LegacyStateBound.model_validate({**choice.model_dump(),**(metadata if stage==3 else {k:decision.get(k) for k in META_FIELDS})})
        if (plan.episode_id,plan.beat_id,plan.sequence_no,plan.considered_source_event_ids)!=(context.episode.id,beat.id,beat.sequence_no,context.considered_source_event_ids):
            raise ValueError("routine_identity_invalid")
        if not set(plan.continuity_facts).issubset(allowed_continuity_facts(context)) or not plan.continuity_facts:
            raise ValueError("routine_continuity_invalid")
        if not set(plan.used_detail_keys).issubset(allowed_detail_keys(context)):
            raise ValueError("routine_detail_invalid")
    else:
        plan=_validate_plan(decision,context=context,beat=beat)
    apply_state_changes(context.state_before,[effect.state_change.model_dump() for effect in plan.source_event_effects],
        scheduled_without_source=not bool(plan.used_source_event_ids),schema_version=context.state_schema_version)
    return {"plan":plan.model_dump(mode="json"),"state_update":aux.get("state_update"),"relationship_metrics":aux.get("relationship_metrics")}


def validate_draft(value, replies):
    draft=parse_routine_draft(value)
    validate_original_post(title=draft["title"],body=draft["body"],completed_replies=replies)
    return draft


async def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    lock=args.output/"active.lock"
    os.close(os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600))
    budget=Budget(args.output/"budget.json")
    try:
        cred=credential(args.credentials,args.character_id)
        material=CredentialResolver.resolve_llm_credential(cred,purpose=CredentialPurpose.RESIDENT_LLM,owner_id=cred.owner_id,character_id=cred.character_id)
        manifest={"model":MODEL,"thinking_level":THINKING,"sdk_version":version("google-genai"),"sdk_attempts":1,"credential_id":cred.id,"credential_character_id":cred.character_id,
            "cap":CAP,"base_requests":40,"repeats":8,"recovery_cap":12,"max_output_tokens":8192,"recovery_tokens":16384,"operational_writes":False,
            "cases":CASES,"stages":STAGES,"scope":"Frozen synthetic generation comparison; actual storage/resume/retrieval contracts verified by local regression."}
        path=args.output/"manifest.json"
        if path.exists() and json.loads(path.read_text())!=json.loads(json.dumps(manifest)):
            raise ValueError("evaluation_manifest_changed")
        write_json(path,manifest)
        if args.diagnose_rejection:
            # One explicitly bounded diagnostic for the SDK ClientError whose
            # HTTP fields were unavailable in the first comparison recorder.
            path=args.output/"diagnostic-rejection.json"
            if path.exists():
                raise ValueError("evaluation_diagnostic_already_completed")
            saved=json.loads((args.output/"long-id-7-0-0.request.json").read_text())
            budget.reserve(recovery=True)
            diagnostic={"case":"long-id-7","stage":"baseline","physical_request":budget.value["physical_requests"],
                "schema":schema_evidence(saved["schema"]),"purpose":"Capture safe HTTP error fields for an unchanged previously rejected synthetic schema."}
            try:
                response=await GeminiAdapter().generate_json(ProviderRequest(api_key=material.reveal(),model=MODEL,thinking_level=THINKING,
                    system_prompt=saved["system"],user_prompt=json.dumps(saved["payload"],ensure_ascii=False),max_output_tokens=8192,
                    timeout_seconds=120,response_schema=saved["schema"],response_mime_type="application/json",sdk_attempts=1))
                diagnostic.update(status="returned",usage=asdict(response.usage))
            except Exception as exc:
                detail=getattr(exc,"response_json",{})
                status=(detail.get("error",{}).get("status") if isinstance(detail,dict) else None)
                diagnostic.update(status="rejected",error_type=type(exc).__name__,provider_code=getattr(exc,"code",None),
                    provider_status=status if status in {"INVALID_ARGUMENT","UNAVAILABLE","RESOURCE_EXHAUSTED"} else None,
                    **structured_error_evidence([("sdk",detail)]))
            write_json(path,diagnostic)
            print(json.dumps({k:v for k,v in diagnostic.items() if k!="schema"}),flush=True)
            return
        completed=set()
        result_path=args.output/"results.jsonl"
        if result_path.exists():
            completed={(row["case"],row["stage"],row["repeat"]) for row in map(json.loads,result_path.read_text().splitlines())}
        jobs=[(name,count,stage,0) for name,count in CASES for stage in range(5)]
        jobs.extend((name,count,stage,1) for name,count in CASES[4:] for stage in (0,4))
        if args.first_scene:
            jobs=[("first-scene-0",0,stage,0) for stage in (0,4)]
        for case_id,count,stage,repeat in jobs:
            if (case_id,STAGES[stage],repeat) in completed: continue
            context,beat,payload,replies=fixture(case_id,count,stage)
            captured=await request_parts(context,beat,payload)
            schema=stage_schema(captured["schema"],stage)
            system=captured["system"]+"\nReturn decision and draft together. Write one Korean root SNS post from the decided routine scene. Preserve title, body, topic_signature, novelty_basis and thought. " + THOUGHT_PROMPT
            if stage>=3:
                system=system.replace("Copy beat_identity episode_id, beat_id and sequence_no exactly. considered_source_event_ids must equal supplied IDs in order. ","The server binds identity and considered IDs; do not output those fields. ")
            if stage>=1:
                system+=" Do not output legacy motivation_* or emotion_* fields."
            if stage>=2:
                system+=" Do not output event effect classification or effect intensity; keep source_event_id and state_change."
            user=json.dumps(captured["payload"],ensure_ascii=False,default=str)
            row={"case":case_id,"stage":STAGES[stage],"repeat":repeat,"schema":schema_evidence(schema),"attempts":[]}
            request_file=args.output/f"{case_id}-{stage}-{repeat}.request.json"
            write_json(request_file,{"system":system,"payload":captured["payload"],"schema":schema})
            if args.dry_run:
                print(json.dumps({"case":case_id,"stage":STAGES[stage],"schema":{k:v for k,v in row["schema"].items() if k != "schema_snapshot"}}),flush=True)
                continue
            fixed_decision=None
            request_schema=schema
            request_system=system
            for attempt in range(2):
                try:
                    budget.reserve(recovery=attempt>0 or args.first_scene)
                except ValueError:
                    row["status"]="budget_exhausted"
                    break
                started=monotonic()
                response=None
                try:
                    response=await GeminiAdapter().generate_json(ProviderRequest(api_key=material.reveal(),model=MODEL,thinking_level=THINKING,
                        system_prompt=request_system,user_prompt=user,max_output_tokens=8192 if attempt==0 else 16384,timeout_seconds=120,response_schema=request_schema,response_mime_type="application/json",sdk_attempts=1))
                    raw=response.parsed if isinstance(response.parsed,dict) else json.loads(response.text)
                    write_json(args.output/f"{case_id}-{stage}-{repeat}-{attempt}.response.json",raw)
                    if fixed_decision is None:
                        fixed_decision=validate_decision(raw,context,beat,stage)
                        draft=validate_draft(raw.get("draft"),replies)
                    else:
                        draft=validate_draft(raw,replies)
                    values={**fixed_decision,"draft":draft}
                    row["result"]=values
                    row["attempts"].append({"status":"valid","finish_reason":response.finish_reason,"usage":asdict(response.usage),"duration_ms":round((monotonic()-started)*1000)})
                    row["status"]="valid"
                    break
                except Exception as exc:
                    row["attempts"].append({"status":"failed","error_type":type(exc).__name__,"provider_code":getattr(exc,"provider_code",None) or getattr(exc,"code",None),
                        "validation_code":str(exc) if str(exc) in {"routine_reuses_published_reply","routine_identity_invalid","routine_continuity_invalid","routine_detail_invalid"} else getattr(exc,"validation_code",None),
                        "usage":asdict(response.usage) if response is not None else None,
                        "finish_reason":response.finish_reason if response is not None else None,
                        "duration_ms":round((monotonic()-started)*1000)})
                    row["status"]="failed"
                    # Preserve permanent provider rejection; don't resend identical 400 schemas.
                    retry=getattr(exc,"retryable",False) or isinstance(exc,(ValueError,))
                    if not retry or budget.value["reserve_requests"]>=12: break
                    if fixed_decision is not None:
                        # A valid decision survives an invalid draft, just as in production.
                        request_schema=draft_schema("routine")
                        request_system=ORIGINAL_POST_INSTRUCTIONS + " Write only the draft from the fixed plan. " + THOUGHT_PROMPT
                        user=json.dumps({"context":captured["payload"],"fixed_plan":fixed_decision["plan"],"repair_feedback":"The previous draft was invalid. Write a valid new root Routine post; never copy an executed reply."},ensure_ascii=False,default=str)
                    else:
                        user=json.dumps({"input":captured["payload"],"repair_feedback":"Return a complete valid response with the exact allowed source/continuity/detail IDs. Write a new root Routine post, never copy an executed reply."},ensure_ascii=False,default=str)
            with result_path.open("a",encoding="utf-8") as stream:
                stream.write(json.dumps(row,ensure_ascii=False,default=str)+"\n")
            print(json.dumps({"case":case_id,"stage":STAGES[stage],"repeat":repeat,"status":row["status"],"used":budget.value["physical_requests"]}),flush=True)
        if args.dry_run:
            return
        rows=[json.loads(line) for line in result_path.read_text().splitlines()]
        write_json(args.output/"summary.json",{"requests":budget.value, "rows":len(rows), "valid":sum(r["status"]=="valid" for r in rows),
            "by_stage":{stage:{"cases":sum(r["stage"]==stage for r in rows),"valid":sum(r["stage"]==stage and r["status"]=="valid" for r in rows),
                "recovered":sum(r["stage"]==stage and r["status"]=="valid" and len(r["attempts"])>1 for r in rows)} for stage in STAGES}})
    finally:
        lock.unlink(missing_ok=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--credentials",type=Path,required=True)
    parser.add_argument("--character-id",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--diagnose-rejection",action="store_true")
    parser.add_argument("--first-scene",action="store_true")
    asyncio.run(run(parser.parse_args()))
