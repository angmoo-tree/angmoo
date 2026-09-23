"""Local synthetic DB/partition measurement; no provider, user DB or network."""
import json
import platform
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from datetime import UTC, datetime, timedelta
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests'))
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session
from p7_graph_support import seed_projection_fixture
from app.models import Base
from app.domains.relationships.models.personalization import RelationshipExperienceReceipt
from app.domains.relationships.service.policy_activation import activate_policy
from app.domains.relationships.service.personalized_metrics import ExperiencedSource, stage_experience, apply_staged_experience
from app.domains.relationships.policies.daily_review import partition_review_inputs


class References:
    def validate(self, source):
        pass  # Synthetic immutable sources; production scope validation is separately tested.


def measure(experience_count):
    with tempfile.TemporaryDirectory(prefix='angmoo-ri-') as temp:
        dbpath = Path(temp) / 'fixture.sqlite'
        engine = create_engine('sqlite:///' + dbpath.as_posix())
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            f = seed_projection_fixture(db, suffix='measure')
            now = datetime.now(UTC)
            activate_policy(db, world_id=f.world.id, now=now-timedelta(days=1))
            db.commit()
            for start in range(0,experience_count,1000):
                db.execute(insert(RelationshipExperienceReceipt), [dict(id=f'old-{i}',world_id=f.world.id,
                    actor_world_character_id=f.actor_world_character.id,target_world_character_id=f.target_world_character.id,
                    source_kind='post',source_key=str(i),source_revision='a'*64,occurred_at=now,delivered_at=now)
                    for i in range(start,min(start+1000,experience_count))])
            db.commit()
            times=[]
            for i in range(100):
                source=ExperiencedSource(f.world.id,f.actor_world_character.id,f.target_world_character.id,
                    'post',f'new-{i}','a'*64,now,now,'Asia/Seoul')
                started=time.perf_counter()
                app=stage_experience(db,references=References(),source=source,decision_key=f'run-{i}',interpretation=None)
                apply_staged_experience(db,application_id=app.id,references=References(),now=now)
                db.commit()
                times.append((time.perf_counter()-started)*1000)
        tracemalloc.start()
        started=time.perf_counter()
        memories=[dict(memory_id=f'm-{i}',summary='격려와 의견 충돌을 기억한다. '*10,
            digest='a'*64,source_refs=[f'post:{i//2}'],occurred_at=now.isoformat()) for i in range(experience_count)]
        parts=partition_review_inputs({'actor_id':'a','target_id':'b'},memories)
        partition_ms=(time.perf_counter()-started)*1000
        _,peak=tracemalloc.get_traced_memory()
        tracemalloc.stop()
        size=dbpath.stat().st_size
        engine.dispose()
        return dict(experience_rows=experience_count,measured_transactions=100,metric_p50_ms=round(median(times),2),
            metric_p95_ms=round(sorted(times)[94],2),partition_memories=experience_count,partition_parts=len(parts),
            partition_ms=round(partition_ms,2),partition_peak_mib=round(peak/1048576,2),sqlite_mib=round(size/1048576,2))


if __name__ == '__main__':
    result={'platform':platform.platform(),'python':platform.python_version(),'provider_calls':0,
        'scope':'one hot directional pair; synthetic receipts, real SQLite commits; partition in memory; no full-world concurrency',
        'measurements':[measure(n) for n in (1000,10000,100000)]}
    destination=Path(sys.argv[1])
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
