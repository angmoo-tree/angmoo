"""Read-only actual SNS recall probe; existing shared FTS/Vec1 contracts.

Only configured query embedding requests are sent; canonical and projections
are opened read-only, no new remembered content or social effects are written.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sqlite3
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.runtime.persistence.model_registration import register_models
from app.domains.world_characters.models import WorldCharacter
from app.domains.characters.models import Character
from app.domains.social.models.posts import Post
from app.domains.memory.service.hybrid_recall import HybridRecallService
from app.domains.memory.repository.episode_hybrid_recall import SqlAlchemyEpisodeHybridReader
from app.domains.memory.repository.embedding import MemoryEmbeddingRepository
from app.runtime.memory.composition import memory_repository
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from app.runtime.memory.hybrid_axes import FtsHybridAxis, VectorHybridAxis
from app.runtime.memory.fts_worker import FtsReadWorkers
from app.runtime.memory.vector_worker import VectorReadWorkers
from app.runtime.memory.vector_resources import bundled_vector_index
from app.runtime.memory.sqlite_fts5_recall import MemoryRecallIndexSettings
from app.runtime.memory_embedding_provider import MemoryQueryEmbedder
from app.runtime.autonomous_activity.recall import SelectedRecall
from app.runtime.autonomous_activity.revalidation import assert_memories_current


async def run(args):
    register_models()
    root=args.root.resolve()
    marker=json.loads((root/"canonical/current-generation.json").read_text())
    path=(root/"canonical"/marker["relative_path"]/"angmoo.sqlite3").resolve()
    if not path.is_relative_to(root/"canonical"):
        raise ValueError("invalid_canonical_path")
    settings.APP_SECRET_FILE=str(root/"secrets/app-secret")
    settings.CREDENTIAL_ENCRYPTION_PROVIDER="local"
    engine=create_engine("sqlite://",creator=lambda: sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,check_same_thread=False))
    factory=sessionmaker(bind=engine)
    fts_path=root/"search/memory-recall/generations/memory-episode-v1/angmoo-memory-recall.sqlite3"
    vector_root=root/"search/memory-vectors"
    generation=json.loads((vector_root/"current.json").read_text())["active"]
    index=bundled_vector_index(vector_root/"generations"/generation/"vectors.sqlite3",generation=generation)
    fts=FtsHybridAxis(FtsReadWorkers(database_path=fts_path,settings=MemoryRecallIndexSettings(generation="memory-episode-v1")),lexical_policy="group_or_v1")
    vector=VectorHybridAxis(VectorReadWorkers(database_path=index.database_path,extension_path=index._extension,
        extension_sha256=hashlib.sha256(index._extension.read_bytes()).hexdigest(),generation=generation),
        MemoryQueryEmbedder(factory,lambda db:MemoryEmbeddingRepository(db,memory_repository(db))))
    service=HybridRecallService(fts=fts,vector=vector,canonical=SqlAlchemyEpisodeHybridReader(factory,detail_reader_factory=RuntimeEpisodeDetailReader))
    with factory() as db:
        actor=db.get(WorldCharacter,args.actor_id)
        owner=db.get(Character,actor.character_id).owner_id
        posts=db.scalars(select(Post).where(Post.world_id==actor.world_id,Post.author_world_character_id!=actor.id,
            Post.visibility=="public",Post.deleted_at.is_(None),Post.report_hidden_at.is_(None)).order_by(Post.created_at.desc()).limit(3)).all()
        scope={"owner_id":owner,"world_id":actor.world_id,"actor_id":actor.id}
        cases=[{"target_id":p.id,"counterpart_id":p.author_world_character_id,"text":p.topic_signature or ((p.title or "")+" "+p.body)} for p in posts]
    retriever=SelectedRecall(service,**scope)
    provider = None
    if args.compare:
        from types import SimpleNamespace
        from scripts.evaluate_personalized_activity import credential
        from app.integrations.direct_llm import RunLlmTracker
        from app.runtime.autonomous_activity.provider import ActivityProvider
        from app.domains.world_characters.service.activity_state import read_state
        with factory() as db:
            character = db.get(Character, actor.character_id)
            shared = {"persona": character.persona_summary, "current_state": read_state(db, world_id=actor.world_id, actor_id=actor.id), "today_activity": []}
        cred = credential(root, actor.character_id)
        tracker = RunLlmTracker(max_calls=12)
        provider = ActivityProvider(SimpleNamespace(credential=cred, character=SimpleNamespace(id=actor.character_id), run_id="recall-comparison", generation_thinking_level=cred.thinking_level, on_rate_limit_wait=None), tracker)
    rows=[]
    for candidate in cases:
        query=candidate["text"][:800]
        result=await retriever.one(activity_id="read-only-v2-probe",target=candidate,query={"query":query})
        verification="valid"
        try:
            with factory() as db:
                assert_memories_current(db,**scope,memories={candidate["target_id"]:result})
        except Exception as exc:
            verification=type(exc).__name__+":"+str(exc)[:120]
        row={"target":candidate["target_id"],"query_sha256":hashlib.sha256(query.encode()).hexdigest(),
            "query_chars":len(query),"status":result["status"],"packets":len(result.get("packets",[])),
            "memory_ids":result.get("ranked_memory_ids",[]),"verification":verification,
            "duration_ms":result.get("duration_ms"),"axes":result.get("axes"),"embedding_usage":result.get("embedding_usage")}
        if provider:
            from app.runtime.autonomous_activity.contracts import Candidate
            from app.runtime.autonomous_activity.queries import resolve_query
            from app.runtime.autonomous_activity.contracts import Selection
            target = Candidate(target_id=candidate["target_id"], counterpart_id=candidate["counterpart_id"], source_ids=[candidate["target_id"]], text=candidate["text"], allowed_actions=["comment", "like"]).model_dump()
            selection = await provider.select(lane="feed", context=shared, candidates=[target], limit=1)
            chosen = selection.get("selections", [])
            q = resolve_query(Selection.model_validate(chosen[0] if chosen else {"target_id":candidate["target_id"]}), Candidate.model_validate(target), lane="feed")
            alternate = await retriever.one(activity_id="read-only-v2-query-comparison", target=candidate, query=q.model_dump())
            row["ai_query"] = {"sha256":hashlib.sha256(q.query.encode()).hexdigest(), "origin":q.origin, "chars":len(q.query), "memory_ids":alternate.get("ranked_memory_ids", []), "duration_ms":alternate.get("duration_ms"), "status":alternate["status"]}
            row["query_overlap"] = len(set(result.get("ranked_memory_ids", [])) & set(alternate.get("ranked_memory_ids", [])))
            decisions = {}
            for variant, memories in (("none", {}), ("natural", {candidate["target_id"]: result}), ("ai", {candidate["target_id"]: alternate})):
                try:
                    decision = await provider.plan(lane="feed", context={**shared,"memories":memories}, candidates=[target])
                    decisions[variant] = {"actions":[d["action"] for d in decision["decisions"]], "purposes":[d.get("comment_purpose") for d in decision["decisions"]], "state_status":decision["state_status"], "brief_hashes":[hashlib.sha256(d["brief"].encode()).hexdigest() for d in decision["decisions"]]}
                except Exception as exc:
                    import re
                    cause = exc.__cause__
                    reason = str(cause) if cause and re.fullmatch(r"[A-Za-z_]+", str(cause)) else type(cause).__name__
                    decisions[variant] = {"status":"failed", "reason":type(exc).__name__, "cause":reason}
            row["decisions"] = decisions
        rows.append(row)
        args.output.write_text(json.dumps(rows,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
        print(json.dumps(row,ensure_ascii=False,default=str),flush=True)
    args.output.write_text(json.dumps(rows,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    engine.dispose()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--actor-id",required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--compare",action="store_true")
    asyncio.run(run(parser.parse_args()))
