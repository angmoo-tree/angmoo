"""M04: real worker, verified Vec1, pinned SDK/mock HTTP, official CLI/collector.

No event files are authored by this test. The runtime recorder creates them.
Only temporary product data and an isolated copy of these sources are used.
"""
import asyncio
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.embedding import MemoryVectorEligibility
from app.domains.memory.repository.vector_eligibility import register_content
from app.domains.memory.repository.vector_queue import enqueue
from app.providers.gemini import GeminiAdapter
from app.runtime.diagnostics.sns_observation import SNSObserver
from app.runtime.memory.sqlite_vec1 import SqliteMemoryVectorIndex
from app.runtime.memory.vector_projection import MemoryVectorProjection
from memory.test_p8_l_h_canonical_recall import runtime_factory
from memory.test_vector_batch_delivery import populate
from memory.test_embedding_batch_transport import transport

REPO=Path(__file__).resolve().parents[3]


def cli(root,data,*args):
    result=subprocess.run([sys.executable,str(root/"backend/scripts/sns_observation.py"),"--data-root",str(data),*args],capture_output=True,text=True,encoding="utf-8",timeout=40)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("chunks",[(7,),(1,2,4)])
def test_actual_worker_cli_collector_first_sample(runtime_factory,tmp_path,monkeypatch,transport,chunks):
    extension=os.environ.get("ANGMOO_TEST_VEC1_EXTENSION")
    pwsh=shutil.which("pwsh")
    if not extension or not pwsh:
        pytest.skip("M04 requires a verified native Vec1 build and PowerShell")
    extension=Path(extension);attestation=json.loads(extension.with_name("manifest.json").read_text())
    assert hashlib.sha256(extension.read_bytes()).hexdigest()==attestation["sha256"]
    # Official child commands load identical sources with an isolated packaged
    # native resource. Nothing is installed into the user's checkout/runtime.
    isolated=tmp_path/"runtime"
    shutil.copytree(REPO/"backend/app",isolated/"backend/app",ignore=shutil.ignore_patterns("__pycache__","resources"))
    (isolated/"backend/scripts").mkdir(parents=True)
    shutil.copy2(REPO/"backend/scripts/sns_observation.py",isolated/"backend/scripts")
    for name in ("Invoke-SnsMediaMemoryObservation.ps1","SnsCollectorPolicy.psm1","sns_media_memory_probe.py"):
        (isolated/"scripts/diagnostics").mkdir(parents=True,exist_ok=True)
        shutil.copy2(REPO/"scripts/diagnostics"/name,isolated/"scripts/diagnostics")
    resources=isolated/"backend/app/runtime/resources/vec1";resources.mkdir(parents=True)
    shutil.copy2(extension,resources/extension.name);shutil.copy2(extension.with_name("manifest.json"),resources/"manifest.json")
    ids=populate(runtime_factory,monkeypatch,7)
    data=tmp_path/"data";canonical=data/"canonical/generations/test/angmoo.sqlite3";canonical.parent.mkdir(parents=True)
    (data/"canonical/current-generation.json").write_text(json.dumps({"schema_version":1,"relative_path":"generations/test"}))
    with sqlite3.connect(runtime_factory.kw["bind"].url.database) as source, sqlite3.connect(canonical) as target:source.backup(target)
    engine=create_engine(f"sqlite:///{canonical.as_posix()}");factory=sessionmaker(bind=engine,expire_on_commit=False)
    # Actual arrivals are registered in separate commits, after each preceding
    # subset has settled. The worker must not wait to collect a forced batch.
    with factory() as db:
        for row in db.scalars(select(MemoryVectorEligibility)):
            if row.memory_item_id not in ids[:chunks[0]]:db.delete(row)
        db.commit()
    manifest=cli(isolated,data,"start","--world","recall-world","--actor","recall-subject","--minutes","1","--tail-minutes","0","--source-revision","isolated-current-source")
    session=manifest["session_id"]
    observer=SNSObserver(data,heartbeat_seconds=.1)
    projection_dir=data/"search/memory-vectors";projection_dir.mkdir(parents=True)
    (projection_dir/"current.json").write_text(json.dumps({"version":1,"active":"v1","staging":None,"previous":None}))
    index=SqliteMemoryVectorIndex(projection_dir/"generations/v1/vectors.sqlite3",extension_path=extension,extension_sha256=attestation["sha256"])
    projection=MemoryVectorProjection(factory,index,provider=GeminiAdapter())
    async def exercise():
        await projection.start()
        offset=0
        for group_size in chunks:
            group=ids[offset:offset+group_size]
            if offset:
                with factory() as db:
                    for identifier in group:
                        register_content(db,db.get(MemoryItem,identifier),now=datetime.now(UTC))
                        # Freeze this ready subset in the same durable admission
                        # transaction, as the explicit preparation owner does.
                        enqueue(db,"v1",identifier,"recall-world",force=True)
                    db.commit()
                projection._wake.set() # same existing wake hint; no additional index or API work
            offset+=group_size
            until=time.monotonic()+20
            while time.monotonic()<until:
                with engine.connect() as db:
                    count=db.exec_driver_sql("SELECT count(*) FROM memory_vector_work WHERE state IN ('done','scheduled') AND desired_revision=applied_revision AND last_code IN ('indexed','current')").scalar()
                if count==offset:break
                await asyncio.sleep(.02)
            assert count==offset,(projection.status,projection.last_code,count)
        await projection.stop()
    try:
        until=time.monotonic()+5
        while time.monotonic()<until:
            support=cli(isolated,data,"memory-preflight","--session",session)
            if support["runtime_fresh"]:break
        assert support["support"]=="supported" and support["runtime_fresh"]
        asyncio.run(exercise())
        assert [len(json.loads(request.content)["requests"]) for request in transport[0]]==list(chunks)
        assert projection.last_code is None
        assert all(index.identity(f"memory-item:{identifier}") is not None for identifier in ids)
        cli(isolated,data,"stop","--session",session)
    finally:
        observer.close();engine.dispose()
    output=tmp_path/"collected"
    result=subprocess.run([pwsh,"-NoProfile","-File",str(isolated/"scripts/diagnostics/Invoke-SnsMediaMemoryObservation.ps1"),
        "-DataRoot",str(data),"-SessionId",session,"-OutputRoot",str(output),"-PythonExe",sys.executable,"-MaxFlushSeconds","0"],capture_output=True,text=True,encoding="utf-8",timeout=60)
    assert result.returncode==0,(result.stdout,result.stderr)
    health=json.loads((output/"collector-health.json").read_text(encoding="utf-8-sig"))
    assert health["export_success"] and health["copy_success"] and health["memory_flush_complete"]
    directory=output/"export/memory-pipeline"
    coverage=json.loads((directory/"coverage.json").read_text())
    events=[json.loads(line) for line in (directory/"timeline.jsonl").read_text().splitlines()]
    assert coverage["http_attempts"]==len(chunks)
    assert len({e["item_id"] for e in events if e["event"]=="queue" and e.get("boundary")=="ack" and e.get("acknowledged")})==7
    assert len({e["item_id"] for e in events if e["event"]=="result" and e.get("boundary")=="committed"})==7
    snapshot=json.loads((directory/"snapshots/canonical-final.json").read_text())
    assert snapshot["status"]=="ok" and len(snapshot["projection"])==7
    assert coverage["memory_pipeline_evidence_complete"] is True,coverage
    evidence=os.environ.get("ANGMOO_M04_EVIDENCE")
    if evidence:
        target=Path(evidence)/("batch-seven" if chunks==(7,) else "sequential-1-2-4")
        shutil.copytree(output,target)
        (target/"execution.json").write_text(json.dumps({"evidence_kind":"isolated_fixture","chunks":chunks,
            "independent_http_requests":len(transport[0]),"vectors":7,"acknowledged":7,"native_extension_sha256":attestation["sha256"],
            "operational_target":"M04_TARGET_NOT_APPLIED","quality":"not_evaluated"},indent=2))
