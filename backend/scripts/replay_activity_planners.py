"""Read-only checkpoint input replay. Runs providers, never execution/settlement ports."""
import argparse, asyncio, json, sqlite3, hashlib
from pathlib import Path
from types import SimpleNamespace
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from app.integrations.direct_llm import RunLlmTracker
from app.runtime.autonomous_activity.provider import ActivityProvider
from app.runtime.autonomous_activity.routine import RoutineLane
from scripts.evaluate_personalized_activity import credential

async def run(args):
    root=args.root.resolve()
    with sqlite3.connect((root/"runtime/activity/activity-checkpoints.sqlite").as_uri()+"?mode=ro",uri=True) as db:
        rows=db.execute("select checkpoint_ns,type,checkpoint from checkpoints where thread_id=? order by checkpoint_id desc",("activity:"+args.activity_id,)).fetchall()
    states={}
    serializer=JsonPlusSerializer()
    for namespace,kind,data in rows:
        name=namespace.split(":")[0]
        if name in states: continue
        value=serializer.loads_typed((kind,data))["channel_values"]
        if value.get("decision_context"): states[name]=value
    cred=credential(root,args.character_id)
    tracker=RunLlmTracker(max_calls=3)
    provider=ActivityProvider(SimpleNamespace(credential=cred,character=SimpleNamespace(id=args.character_id),run_id="readonly-replay",generation_thinking_level=cred.thinking_level,on_rate_limit_wait=None),tracker)
    results={"operational_writes":False,"activity_id":args.activity_id}
    if "FeedActivityGraph" in states:
        state=states["FeedActivityGraph"]
        ids={s["target_id"] for s in state["selections"]}
        try:
            value=await provider.plan(lane="feed",context=state["decision_context"],candidates=[c for c in state["candidates"] if c["target_id"] in ids])
            results["feed"]={"status":"valid","actions":[d["action"] for d in value["decisions"]]}
        except Exception as exc:
            results["feed"]={"status":"failed","reason":type(exc).__name__,"cause":str(exc.__cause__)[:160]}
    if "RoutineActivityGraph" in states:
        state=states["RoutineActivityGraph"]; frozen=state["lane_data"]["prepared"]
        previous=state["decision_context"]["routine"].get("previous_success")
        marker=json.loads((root/"canonical/current-generation.json").read_text())
        with sqlite3.connect((root/"canonical"/marker["relative_path"]/"angmoo.sqlite3").as_uri()+"?mode=ro",uri=True) as db:
            seq=db.execute("select sequence_no from activity_beats where id=?",(frozen["beat_id"],)).fetchone()[0]
        context=SimpleNamespace(episode=SimpleNamespace(id=frozen["refs"]["episode"]),
            previous_beat=SimpleNamespace(id=previous["beat_id"],sequence_no=previous["sequence_no"]) if previous else None,
            previous_post=SimpleNamespace(id=previous["post"]["id"]) if previous else None,
            source_events=[SimpleNamespace(source_event_id=e["source_event_id"]) for e in frozen["source_events"]],
            considered_source_event_ids=[e["source_event_id"] for e in frozen["source_events"]])
        lane=RoutineLane.__new__(RoutineLane)
        lane.prepared=SimpleNamespace(context=context,beat=SimpleNamespace(id=frozen["beat_id"],sequence_no=seq))
        captured={}
        class Captured(Exception): pass
        class Capture:
            async def call(self,**kwargs): captured.update(kwargs); raise Captured()
        lane.provider=Capture()
        try: await lane.plan(state)
        except Captured: pass
        lane.provider=provider
        try:
            decision=await provider.call(**captured)
            draft=await lane.write({**state,"decision":decision})
            results["routine"]={"status":"valid","identity_matches":True,"scene_kind":decision["plan"]["scene_kind"],"draft_count":len(draft["drafts"])}
        except Exception as exc:
            results["routine"]={"status":"failed","reason":type(exc).__name__,"cause":str(exc.__cause__)[:160]}
    usage=tracker.summary()
    for call in usage.get("calls",[]):
        for key in ("credential_id","key_fingerprint","character_id","json_postprocess_error"): call.pop(key,None)
    results["usage"]=usage
    args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in results.items() if k!="usage"},ensure_ascii=False))

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True);p.add_argument("--character-id",required=True);p.add_argument("--activity-id",required=True);p.add_argument("--output",type=Path,required=True)
    asyncio.run(run(p.parse_args()))
