"""FI10 adversarial synthetic workloads. No credentials or external AI calls.

Run from backend: uv run --with psutil python scripts/benchmark_grouped_fts_extended.py --out <new-directory>
Cold means a newly spawned process with OS cache uncontrolled, never OS-cache cold.
"""
import argparse
import asyncio
from collections import Counter
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
import multiprocessing
from pathlib import Path
import sqlite3
import statistics
import sys
import threading
from time import monotonic, process_time

import psutil
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domains.memory.contracts.recall import MemoryRecallDocument, MemoryRecallSearchQuery, MemoryRecallLexicalPolicy, RecallDocumentKind, MemoryRecallSearchIncomplete
from app.domains.memory.policies.grouped_fts import build_groups
from app.runtime.memory.grouped_fts_search import render_match, MAX_BYTES
from app.runtime.memory.fts_worker import FtsReadWorkers, _fts_child
from app.runtime.memory import vector_worker
from app.runtime.memory.sqlite_fts5_recall import SqliteMemoryRecallIndex, _prepare_document, _scope_filters
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.domains.memory.contracts.scope import MemoryScope

SCOPE=MemoryScope('benchmark-owner','benchmark-world','benchmark-subject')
NOW=datetime(2026,9,15,tzinfo=UTC)
WORKLOADS={
    'bigram_collision':'아버지가',
    'long_input':'별빛 '+' '.join(f'keyword{n}' for n in range(45)),
    'foreign_scope':'보안표식',
    'large_raw_row':'거대본문',
}


def save(path, value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str),encoding='utf-8')


def stats(values):
    values=sorted(values)
    return {'n':len(values),'p50_ms':statistics.median(values),
            'p95_ms':values[min(len(values)-1,int(len(values)*.95))],'max_ms':max(values)}


class Sample:
    """Resource samples, not a claimed exact peak or exact child CPU total."""
    def __init__(self):
        self.stop=threading.Event();self.rss=0;self.child_rss=0;self.child_cpu={}
    def __enter__(self):
        def run():
            parent=psutil.Process()
            while not self.stop.wait(.01):
                total=0
                try: processes=[parent]+parent.children(recursive=True)
                except psutil.Error: continue
                for p in processes:
                    try:
                        rss=p.memory_info().rss;total+=rss
                        if p.pid!=parent.pid:
                            self.child_rss=max(self.child_rss,rss)
                            cpu=p.cpu_times();self.child_cpu[p.pid]=cpu.user+cpu.system
                    except psutil.Error:pass
                self.rss=max(self.rss,total)
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
        return self
    def __exit__(self,*args):self.stop.set();self.thread.join()
    def result(self):
        return {'sampled_tree_peak_rss_bytes':self.rss,'sampled_child_peak_rss_bytes':self.child_rss,
                'sampled_child_cpu_seconds':sum(self.child_cpu.values()),'sample_interval_ms':10}


def documents(size):
    for n in range(size):
        owner,world,subject=SCOPE.owner_id,SCOPE.world_id,SCOPE.subject_world_character_id
        if n>=size//2:
            if n%3==0:owner='foreign-owner'
            elif n%3==1:world='foreign-world'
            else:subject='foreign-subject'
        text='아버지 가방에 편지가 있었다. 별빛 축제에서 연습했다. 기록'+str(n)
        if n>=size//2 or n==1:text+=' 보안표식'
        if n==0:text='거대본문 '+('x'*(5*1024*1024))
        for prefix in ('summary','evidence'):
            content='거대본문 짧은 요약' if n==0 and prefix=='summary' else text
            yield MemoryRecallDocument(f'{prefix}:{n}',str(n),owner,world,subject,
                RecallDocumentKind.MEMORY_ITEM,str(n),content,occurred_at=NOW,metadata={'item_version':'1'})


def make_query(text,policy):
    return MemoryRecallSearchQuery(SCOPE,text,(RecallDocumentKind.MEMORY_ITEM,),50,
        korean_spacing_fallback=True,lexical_policy=policy)


def warm(index,size,repeats,out):
    results=[]
    for policy in MemoryRecallLexicalPolicy:
        for label,text in WORKLOADS.items():
            q=make_query(text,policy);times=[];counts=Counter();reasons=Counter();max_bytes=0;max_scanned=0
            unexpected=0;leaked=0;cpu=process_time();last_stats={}
            with Sample() as sample:
                for n in range(repeats):
                    t=monotonic()
                    if policy==MemoryRecallLexicalPolicy.GROUP_OR_V1:
                        batch=index.search_grouped(q,deadline=monotonic()+5)
                        rows=batch.candidates;counts[batch.status.value]+=1;reasons[batch.reason_code]+=1
                        last_stats=batch.stats;max_bytes=max(max_bytes,batch.stats['bytes_scanned']);max_scanned=max(max_scanned,batch.stats['scanned'])
                        assert max_bytes<=MAX_BYTES and len(rows)<=50
                        if label=='bigram_collision':unexpected+=bool(rows) or batch.reason_code!='fts_candidate_window_exhausted'
                        if label=='long_input':unexpected+=batch.reason_code!='fts_input_truncated'
                        if label=='large_raw_row':unexpected+=batch.reason_code!='fts_materialization_budget'
                        if label=='foreign_scope':unexpected+=set(c.memory_item_id for c in rows)!={'1'}
                    else:
                        try:
                            rows=index.search(q);counts['completed']+=1
                        except MemoryRecallSearchIncomplete:
                            rows=();counts['incomplete']+=1
                    leaked+=sum(int(c.memory_item_id)>=size//2 for c in rows)
                    times.append((monotonic()-t)*1000)
            row={'size':size,'documents':size*2,'policy':policy.value,'workload':label,**stats(times),
                'cpu_seconds':process_time()-cpu,'statuses':dict(counts),'reasons':dict(reasons),
                'max_materialized_bytes':max_bytes if policy==MemoryRecallLexicalPolicy.GROUP_OR_V1 else None,
                'max_scanned':max_scanned if policy==MemoryRecallLexicalPolicy.GROUP_OR_V1 else None,
                'last_stats':last_stats,'last_returned':len(rows),'scope_leaks':leaked,'unexpected':unexpected,**sample.result()}
            results.append(row);save(out/'warm.json',results)
            print(json.dumps({k:row[k] for k in ('size','policy','workload','p95_ms','statuses','unexpected','scope_leaks')}),flush=True)
    return results


def _sql_stage_child(pipe,database,settings,query,deadline,entered,release):
    """Pause from inside an actual SQLite progress callback, test harness only."""
    original=SqliteMemoryRecallIndex._connect
    class Connection:
        def __init__(self,raw):self.raw=raw
        def __getattr__(self,key):return getattr(self.raw,key)
        def set_progress_handler(self,callback,n):
            if callback is None:return self.raw.set_progress_handler(None,n)
            def progress():
                if not entered.is_set():
                    entered.set();release.wait(15)
                return callback()
            self.raw.set_progress_handler(progress,n)
    @contextmanager
    def instrument(index,*args,**kwargs):
        with original(index,*args,**kwargs) as c:yield Connection(c)
    SqliteMemoryRecallIndex._connect=instrument
    _fts_child(pipe,database,settings,query,deadline)


async def wait_event(event):
    async with asyncio.timeout(10):
        while not event.is_set():await asyncio.sleep(.001)


async def cancel_matrix(path,size,out):
    rows=[];context=multiprocessing.get_context('spawn')
    q=make_query('별빛 축제',MemoryRecallLexicalPolicy.GROUP_OR_V1)
    for stage in ('queue','sql','receive_ready'):
        for n in range(5):
            workers=FtsReadWorkers(database_path=path,concurrency=2)
            entered=context.Event();release=context.Event();original_context=vector_worker.multiprocessing.get_context
            if stage=='queue':
                await workers._slots.acquire();await workers._slots.acquire()
            if stage=='sql':
                workers._child_target=SqlStageTarget(entered,release)
            if stage=='receive_ready':
                class Receiver:
                    def __init__(self,raw):self.raw=raw
                    def __getattr__(self,key):return getattr(self.raw,key)
                    def poll(self,*args):
                        ready=self.raw.poll(*args)
                        if ready:entered.set();return False
                        return ready
                class Context:
                    def Pipe(self,**kw):
                        receiver,sender=context.Pipe(**kw);return Receiver(receiver),sender
                    def Process(self,**kw):return context.Process(**kw)
                vector_worker.multiprocessing.get_context=lambda *args:Context()
            task=asyncio.create_task(workers.search(q,deadline=monotonic()+15))
            try:
                if stage=='queue':await asyncio.sleep(.02)
                else:await wait_event(entered)
                pids=list(workers.active_processes);t=monotonic();task.cancel()
                try:await task
                except asyncio.CancelledError:pass
                else:raise AssertionError('cancellation_not_observed')
                cleanup=(monotonic()-t)*1000
                assert not workers.active_processes and all(not psutil.pid_exists(pid) for pid in pids)
                rows.append({'size':size,'stage':stage,'sample':n,'cleanup_ms':cleanup,'remaining_workers':0,
                    'actual_sql_progress_entered':stage=='sql','actual_pipe_data_ready':stage=='receive_ready'})
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
                vector_worker.multiprocessing.get_context=original_context
                if stage=='queue':workers._slots.release();workers._slots.release()
            save(out/'cancel.json',rows)
    print(json.dumps({'size':size,'cancellations':len(rows),'remaining_workers':0}),flush=True)
    return rows


class SqlStageTarget:
    def __init__(self,entered,release):self.entered=entered;self.release=release
    def __call__(self,pipe,database,settings,query,deadline):
        _sql_stage_child(pipe,database,settings,query,deadline,self.entered,self.release)


async def cold(index,size,out):
    results=[];workers=FtsReadWorkers(database_path=index.database_path)
    for policy in MemoryRecallLexicalPolicy:
        for label,text in WORKLOADS.items():
            durations=[];statuses=[]
            with Sample() as sample:
                for _ in range(5):
                    t=monotonic()
                    try:
                        result,_=await workers.search(make_query(text,policy),deadline=monotonic()+5)
                        statuses.append(result.receipt.status.value)
                    except TimeoutError:statuses.append('timeout')
                    durations.append((monotonic()-t)*1000)
            assert not workers.active_processes
            results.append({'size':size,'policy':policy.value,'workload':label,**stats(durations),
                'statuses':statuses,'remaining_workers':0,'cold_definition':'new_process_OS_cache_uncontrolled',**sample.result()})
            save(out/'cold.json',results)
    return results


def wal_and_deadline(index,size,out):
    results=[]
    # New fixture only: preserve active snapshots while exercising real row write
    # plus projection digest refresh in the same transaction.
    index._read_only=False
    with index._connect(index.database_path) as setup:setup.execute('PRAGMA journal_mode=WAL')
    for n in range(5):
        with index._connect(index.database_path) as writer:
            writer.execute('PRAGMA wal_autocheckpoint=0')
            readers=[sqlite3.connect(index.database_path.as_uri()+'?mode=ro',uri=True) for _ in range(2)]
            try:
                for reader in readers:
                    reader.execute('BEGIN');reader.execute('SELECT COUNT(*) FROM memory_recall_documents').fetchone()
                t=monotonic();writer.execute('BEGIN IMMEDIATE')
                doc=MemoryRecallDocument(f'writer:{n}',f'writer:{n}','foreign-owner',SCOPE.world_id,SCOPE.subject_world_character_id,
                    RecallDocumentKind.MEMORY_ITEM,'writer','별빛 축제 writer',occurred_at=NOW,metadata={'item_version':'1'})
                index._insert_document(writer,_prepare_document(doc));index._refresh_state(writer);writer.commit()
                elapsed=(monotonic()-t)*1000
                wal=Path(str(index.database_path)+'-wal');held_bytes=wal.stat().st_size
                checkpoint_held=tuple(writer.execute('PRAGMA wal_checkpoint(PASSIVE)').fetchone())
                assert held_bytes>0
            finally:
                for reader in readers:reader.rollback();reader.close()
            t=monotonic();checkpoint_done=tuple(writer.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone())
            reclaimed_ms=(monotonic()-t)*1000
            assert wal.stat().st_size==0 and checkpoint_done[0]==0
            results.append({'size':size,'sample':n,'writer_with_digest_ms':elapsed,'wal_bytes_while_readers_hold_snapshot':held_bytes,
                'checkpoint_held':checkpoint_held,'checkpoint_released':checkpoint_done,'wal_after_bytes':0,'reclaim_ms':reclaimed_ms})
    index._read_only=True
    deadlines=[]
    for _ in range(5):
        t=monotonic();batch=index.search_grouped(make_query('별빛',MemoryRecallLexicalPolicy.GROUP_OR_V1),deadline=t+.005)
        deadlines.append({'status':batch.status.value,'reason':batch.reason_code,'elapsed_ms':(monotonic()-t)*1000})
        assert batch.reason_code=='fts_deadline_exceeded'
    save(out/'wal-deadline.json',{'wal':results,'deadline':deadlines})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--sizes',type=int,nargs='+',default=[10000,100000])
    parser.add_argument('--repeats',type=int,default=100)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    save(args.out/'manifest.json',{'created':datetime.now(UTC).isoformat(),'sizes':args.sizes,'warm_repeats':args.repeats,
        'cold_repeats':5,'cancel_per_stage':5,'ai_calls':0,'workloads':WORKLOADS,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'distribution':'half current memories allowed; half split across foreign owner/world/subject; 2 docs per memory; one 5MiB raw evidence row',
        'limits':'benchmark 5s deadline; production 200 candidate window and 4MiB materialization; product settings unchanged',
        'receive_stage':'actual pipe packet ready, before synchronous deserialization; partial-frame stall is not injected',
        'cold':'new process, OS cache uncontrolled; no system cache purge'})
    for size in args.sizes:
        out=args.out/str(size);out.mkdir()
        index=SqliteMemoryRecallIndex(StaticRuntimeDataPath(out/'data'))
        index.database_path.parent.mkdir(parents=True,exist_ok=True)
        t=monotonic();index._build_database(index.database_path,(_prepare_document(d) for d in documents(size)))
        print(json.dumps({'built':size,'documents':2*size,'seconds':monotonic()-t}),flush=True)
        reader=SqliteMemoryRecallIndex.reader(index.database_path)
        with reader._connect(reader.database_path) as c:
            storage=c.execute('SELECT COUNT(*),COUNT(DISTINCT memory_item_id),sum(length(CAST(normalized_text AS BLOB))),sum(length(CAST(text AS BLOB))),sum(length(CAST(metadata_json AS BLOB))) FROM memory_recall_documents').fetchone()
            q=make_query('아버지가',MemoryRecallLexicalPolicy.GROUP_OR_V1);filters,params=_scope_filters(q)
            plan=c.execute('EXPLAIN QUERY PLAN SELECT d.document_id,bm25(memory_recall_fts) AS rank FROM memory_recall_fts JOIN memory_recall_documents d ON d.document_id=memory_recall_fts.document_id WHERE memory_recall_fts MATCH ? AND '+' AND '.join(filters)+' ORDER BY rank,d.occurred_at DESC,d.document_id LIMIT 200',(render_match(build_groups(q.text).groups),*params)).fetchall()
        save(out/'fixture.json',{'storage_counts_and_bytes':list(storage),'db_bytes':index.database_path.stat().st_size,'explain':[list(r) for r in plan]})
        rows=warm(reader,size,args.repeats,out)
        assert all(not r['unexpected'] and not r['scope_leaks'] for r in rows)
        asyncio.run(cold(reader,size,out));asyncio.run(cancel_matrix(index.database_path,size,out))
        wal_and_deadline(reader,size,out)
        save(out/'complete.json',{'passed':True,'ai_calls':0,'size':size})
    save(args.out/'complete.json',{'passed':True,'sizes':args.sizes,'ai_calls':0})


if __name__=='__main__':main()
