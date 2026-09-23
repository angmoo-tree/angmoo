"""C-only synthetic SQLite measurement. Never opens an installed application DB.

Run from backend: uv run python scripts/measure_topic_recommendation.py --output PATH
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import platform
import ctypes
from ctypes import wintypes

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from sqlalchemy import create_engine, event, insert
from sqlalchemy.orm import Session
from app.models import Base
from app.runtime.persistence.model_registration import register_models
from app.domains.social.models.posts import Post, ProfileFollow
from app.domains.social.models.feed import WorldCharacterFeedObservation
from app.domains.social.models.topics import RecommendationPost, RecommendationPostTopic
from app.domains.social.service.recommendation_topics import TopicMatcher, replace_source_topics
from app.domains.social.service.world_feed import load_ready_search_profile
from app.runtime.social.world_feed_queries import WorldFeedQueries
from app.runtime.social.recommendation_feed import candidates
from social.test_world_feed_search import _user, _world, _add_world_character, _add_ready_profile


def percentile(values, fraction):
    return sorted(values)[min(len(values)-1, int(len(values)*fraction))]


def memory_bytes():
    if sys.platform != "win32":
        return None
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    data = Counters(); data.cb = ctypes.sizeof(data)
    ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(-1), ctypes.byref(data), data.cb)
    return {"rss": data.WorkingSetSize, "peak_rss": data.PeakWorkingSetSize}


def run(output):
    from app.runtime.social.topic_scope import configure
    configure()
    register_models()
    now = datetime.now(UTC)
    with tempfile.TemporaryDirectory(prefix="angmoo-topic-measure-") as temporary, ExitStack() as resources:
        path = Path(temporary) / "synthetic.sqlite"
        engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"check_same_thread": False, "timeout": 10})
        resources.callback(engine.dispose)
        @event.listens_for(engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            owner = _user("measure-owner"); db.add(owner); db.flush()
            world = _world(owner); db.add(world); db.flush()
            world_id = world.id
            actors = []
            for index in range(50):
                _, character, wc = _add_world_character(db, world=world, suffix=f"measure-{index}", feed_mode="topic_recommendation_v1")
                _add_ready_profile(db, world=world, character=character, world_character=wc)
                topics = replace_source_topics(db, world_id=world.id, world_character_id=wc.id,
                    topics=[(f"주제{(index+j)%20:02}", "world") for j in range(3)])
                actors.append((character.id, character.owner_id, wc.id, topics))
            db.flush()
            posts, receipts, links, follows = [], [], [], []
            for index in range(10000):
                character, owner_id, wc_id, topics = actors[index%50]
                identity = f"measure-post-{index:06}"
                created = now-timedelta(seconds=10000-index)
                posts.append(dict(id=identity, author_user_id=owner_id, author_character_id=character,
                    world_id=world.id, author_world_character_id=wc_id, author_name=f"character {index%50}",
                    title="Synthetic post", body="측정용 본문 "*180, created_at=created))
                receipts.append(dict(post_id=identity, world_id=world.id, created_at=created, matched_catalog_version=1))
                if index%2 == 0:
                    links.append(dict(post_id=identity, topic_id=topics[0], world_id=world.id, created_at=created))
            db.execute(insert(Post), posts); db.execute(insert(RecommendationPost), receipts); db.execute(insert(RecommendationPostTopic), links)
            for index, (character, _, wc_id, _) in enumerate(actors):
                for offset in range(1, 9):
                    other = actors[(index+offset)%50]
                    follows.append(dict(world_id=world.id, follower_character_id=character, follower_world_character_id=wc_id,
                                        target_character_id=other[0], target_world_character_id=other[2]))
            db.execute(insert(ProfileFollow), follows); db.commit()
        def sample(index):
            start = time.perf_counter()
            with Session(engine) as db:
                refs = WorldFeedQueries(db)
                profile = load_ready_search_profile(db, references=refs, world_character_id=actors[index%50][2])
                result = candidates(db, profile=profile, allowed_policy_actions=("like", "comment", "follow"), now=now, references=refs)
                assert len(result.candidates) <= 20 and result.raw_candidate_count <= 200
                assert len({c.post_id for c in result.candidates}) == len(result.candidates)
                assert sum(len(c.body_preview) for c in result.candidates) <= 18000
                return (time.perf_counter()-start)*1000, result.query_latency_ms, len(result.candidates)
        cold = sample(0)
        measurements = []
        for concurrency in (1, 2, 4):
            cpu = time.process_time(); wall = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                results = list(executor.map(sample, range(200)))
            values = [r[0] for r in results]
            measurements.append(dict(concurrency=concurrency, samples=200, ready_p50_ms=round(statistics.median(values),2),
                ready_p95_ms=round(percentile(values,.95),2), query_p95_ms=percentile([r[1] for r in results],.95),
                max_ms=round(max(values),2), cpu_seconds=round(time.process_time()-cpu,2), wall_seconds=round(time.perf_counter()-wall,2),
                min_candidates=min(r[2] for r in results), max_candidates=max(r[2] for r in results)))
            print(json.dumps(measurements[-1]), flush=True)
        with Session(engine) as db:
            seen_rows = [dict(id=f"seen-{index}", world_id=world_id, observer_world_character_id=actors[0][2],
                post_id=p["id"], status="observed", claim_token="synthetic", lease_expires_at=now,
                cycle_key="synthetic", run_id="synthetic", matched_keywords=[], matched_fields=[], rank_score=0,
                post_created_at=p["created_at"], claimed_at=now, observed_at=now) for index, p in enumerate(posts)]
            db.execute(insert(WorldCharacterFeedObservation), seen_rows); db.commit()
        seen_samples=[sample(0) for _ in range(30)]
        assert all(row[2] == 0 for row in seen_samples)
        with engine.connect() as connection:
            query_plans = {}
            statements = {
                "latest": ("SELECT post_id FROM social_recommendation_posts WHERE world_id=? ORDER BY created_at DESC,post_id DESC LIMIT 24", (world_id,)),
                "topic": ("SELECT post_id FROM social_recommendation_post_topics WHERE world_id=? AND topic_id=? ORDER BY created_at DESC,post_id DESC LIMIT 4", (world_id, actors[0][3][0])),
                "relation": ("SELECT id FROM posts WHERE world_id=? AND author_world_character_id=? ORDER BY created_at DESC,id DESC LIMIT 2", (world_id, actors[1][2])),
                "seen": ("SELECT id FROM world_character_feed_observations WHERE observer_world_character_id=? AND post_id=?", (actors[0][2], posts[0]["id"])),
            }
            for label, (sql, params) in statements.items():
                query_plans[label] = [row[3] for row in connection.exec_driver_sql("EXPLAIN QUERY PLAN " + sql, params)]
            try:
                storage = dict(connection.exec_driver_sql("SELECT name,sum(pgsize) FROM dbstat GROUP BY name").all())
            except Exception:
                storage = {"available": False}
        start=time.perf_counter()
        matcher=TopicMatcher([(str(i), f"주제{i:04}") for i in range(5000)])
        build=(time.perf_counter()-start)*1000
        values=[]
        for i in range(200):
            start=time.perf_counter(); assert matcher.match(["주제4999 "*400]) == ["4999"]
            values.append((time.perf_counter()-start)*1000)
        result=dict(dataset=dict(posts=10000,characters=50), cold_ready_ms=round(cold[0],2),
            environment=dict(python=sys.version, platform=platform.platform(), cpu=platform.processor()),
            warm=measurements, seen10000=dict(samples=30,ready_p95_ms=round(percentile([r[0] for r in seen_samples],.95),2)),
            memory=memory_bytes(), query_plans=query_plans, storage_by_object=storage,
            catalog5000=dict(build_ms=round(build,2), match_p95_ms=round(percentile(values,.95),2)),
            db_bytes=path.stat().st_size, wal_bytes=Path(str(path)+"-wal").stat().st_size if Path(str(path)+"-wal").exists() else 0,
            provider_calls=0, scope="synthetic C recommendation only; no workflow/real-AI/user-check claim")
        engine.dispose()
        Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",required=True)
    run(parser.parse_args().output)
