"""Opt-in provider comparisons with frozen synthetic inputs and no effect ports.

This compares actual V1/V2 planner contracts, not whole application throughput.
It also isolates query output and state output. Credentials are read-only.
"""
import argparse
import asyncio
from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
from time import monotonic

from scripts.evaluate_personalized_activity import credential, CASES, PERSONAS
from app.runtime.autonomous_activity.provider import ActivityProvider, TargetOutput, ActionOutput, SELECTOR_INSTRUCTIONS, PLANNER_INSTRUCTIONS, parse_action
from app.runtime.autonomous_activity.contracts import Candidate
from app.integrations.direct_llm import RunLlmTracker
from app.providers.gemini import build_gemini_developer_response_schema
from app.domains.relationships.policies.interpretation_prompt import METRIC_INSTRUCTIONS, with_metric_schema
from app.domains.social.service.feed_reaction_prompts import build_reaction_prompts
from app.domains.social.service.feed_reaction_validation import validate_reaction_decision
from app.domains.social.schemas.feed import WorldFeedCandidateRead, FeedReactionDecision


async def run(args):
    if args.output.exists():
        raise ValueError("evaluation_output_exists")
    cred = credential(args.root, args.character_id)
    rows = []
    for index in (2, 3, 4):
        case_id, text, memory = CASES[index]
        tracker = RunLlmTracker(max_calls=5)
        ctx = SimpleNamespace(credential=cred, character=SimpleNamespace(id=args.character_id),
            run_id="comparison-"+case_id, generation_thinking_level=cred.thinking_level, on_rate_limit_wait=None)
        provider = ActivityProvider(ctx,tracker)
        targets = [Candidate(target_id="p",counterpart_id="partner",source_ids=["p"],text=text,allowed_actions=["comment","like"]).model_dump(),
            Candidate(target_id="other",counterpart_id="other",source_ids=["other"],text="게시판 점검이 끝났습니다.",allowed_actions=["like"]).model_dump()]
        shared = {"persona":PERSONAS[index%3],"current_state":{"known":True,"mood":"calm","mood_intensity":25,"state_note":"차분하게 하루를 보내고 있다."},
            "today_activity":[],"state_elapsed_seconds":1800,"memories":memory,
            "metric_sources":[{"source_ref":"p","target_ref":"partner","text":text}]}
        row={"case":case_id,"kind":"real_ai_frozen_contract_comparison","operational_writes":False}
        start=monotonic()
        try:
            selection_schema=build_gemini_developer_response_schema(TargetOutput)
            item=selection_schema["properties"]["selections"]["items"]
            item["properties"].pop("memory_query",None)
            item["required"]=[x for x in item.get("required",[]) if x!="memory_query"]
            row["selection_only"]=await provider.call(node="ComparisonSelectionOnly",lane="evaluation",system=SELECTOR_INSTRUCTIONS.split("For EACH SELECTED")[0],
                payload={"context":{k:v for k,v in shared.items() if k!="memories"},"candidates":targets,"selection_limit":1},schema=selection_schema,validator=lambda x:x,max_tokens=2048)
            row["selection_query"]=await provider.select(lane="feed",context={k:v for k,v in shared.items() if k!="memories"},candidates=targets,limit=1)
            row["with_state"]=await provider.plan(lane="feed",context=shared,candidates=targets[:1])
            schema=with_metric_schema(build_gemini_developer_response_schema(ActionOutput))
            for key in ("state_update","state_source_refs"):
                schema["properties"].pop(key,None)
                schema["required"]=[x for x in schema.get("required",[]) if x!=key]
            row["without_state"]=await provider.call(node="ComparisonActionWithoutState",lane="evaluation",
                system=PLANNER_INSTRUCTIONS.split("state_update is null")[0]+METRIC_INSTRUCTIONS,
                payload={"context":shared,"selected_targets":targets[:1]},schema=schema,validator=lambda x:parse_action(x,targets[:1]),max_tokens=4096)
            profile=SimpleNamespace(world=SimpleNamespace(name="작업 공동체",tagline="함께 작업하는 사람들",timezone="Asia/Seoul"),
                character=SimpleNamespace(name="기록자",persona_summary=PERSONAS[index%3],speech_style="간결한 한국어"),
                world_character=SimpleNamespace(local_profile={}),profile=SimpleNamespace(visible_summary="작업 공동체의 구성원"),action_profile={})
            candidate=WorldFeedCandidateRead(candidate_index=0,post_id="p",author_world_character_id="partner",author_character_id="partner-char",author_name="동료",title="",body_preview=text,
                topic_signature=text,created_at=datetime.now(UTC),world_local_datetime="2026-09-23 09:00",age_seconds=0,age_bucket="recent",matched_keywords=[],matched_fields=[],rank_score=1,allowed_actions=["comment","like"])
            system,user=build_reaction_prompts(profile=profile,candidates=(candidate,))
            result=await provider.call(node="ComparisonV1FeedPlanner",lane="evaluation",system=system,payload=json.loads(user),schema=build_gemini_developer_response_schema(FeedReactionDecision),
                validator=lambda x:validate_reaction_decision(x,candidates=(candidate,),proposal_eligible_indices=frozenset()),max_tokens=4096)
            row["v1_feed_planner"]=result.model_dump(mode="json")
            row["status"]="valid"
        except Exception as exc:
            row["status"]="failed";row["reason"]=type(exc).__name__
        usage=tracker.summary()
        for call in usage.get("calls",[]):
            for key in ("credential_id","key_fingerprint","character_id"):
                call.pop(key,None)
        row.update(duration_ms=round((monotonic()-start)*1000),usage=usage)
        rows.append(row)
        args.output.write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
        print(json.dumps({"case":case_id,"status":row["status"]}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--character-id",required=True);p.add_argument("--output",type=Path,required=True)
    asyncio.run(run(p.parse_args()))
