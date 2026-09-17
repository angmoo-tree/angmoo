"""GC8 opt-in fixed-model retrieval evaluation; no product writes or CRG calls.

Real Supervisor/Planner calls and production validators/executors/Graph recall,
with frozen synthetic storage gateways. This does not measure real FTS recall.
"""
import argparse
import asyncio
from contextvars import ContextVar
from dataclasses import asdict
from datetime import datetime, UTC, timedelta
import hashlib
import json
import logging
import os
from pathlib import Path
from time import monotonic

from evaluate_chat_supervisor_selection import read_material
from graph_contract_fixture import Policy, Recall, IDS, OWNER_ID, WORLD_ID, SUBJECT_ID
from app.integrations import direct_llm
from app.integrations.llm.supervisor_selection import DirectLlmSupervisorSelectionProvider, control_selection_system_prompt, control_selection_tools
from app.integrations.llm.graph_retrieval_planner import DirectLlmGraphRetrievalPlannerProvider
from app.integrations.llm.canonical_retrieval_planner import DirectLlmCanonicalRetrievalPlannerProvider
from app.domains.chat.contracts.supervisor_selection import SelectionArgumentOptions
from app.domains.chat.contracts.retrieval_policy import RetrievalPreflightCommand
from app.domains.chat.contracts.retrieval_router_provider import RetrievalRouterContextMessage
from app.domains.chat.service.retrieval_routing import RetrievalRoutingService
from app.domains.chat.service.graph_retrieval import GraphRetrievalPlanningService, GraphRetrievalCommand
from app.domains.chat.service.canonical_retrieval import CanonicalRetrievalPlanningService, CanonicalRetrievalCommand
from app.domains.chat.service.both_retrieval import BothRetrievalWorkflowCoordinator, BothRetrievalCommand
from app.domains.relationships.service.graph_planning import GraphRetrievalPlanExecutor
from app.domains.memory.service.retrieval_plan import CanonicalRetrievalPlanExecutor
from app.domains.memory.contracts.recall import CanonicalRecallResult, CanonicalRecallRecord, CanonicalRecallStatus, RecallDocumentKind
from app.contracts.retrieval_observation import Observation, current


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def sha(value): return hashlib.sha256(value).hexdigest()


class MemoryFixture:
    def execute(self, query, **kwargs):
        return CanonicalRecallResult(operation=query.operation, status=CanonicalRecallStatus.READY, candidate_count=1, records=(
            CanonicalRecallRecord(reference="source:social_event:gc-library", kind=RecallDocumentKind.SOCIAL_EVENT,
                canonical_source_id="gc-library", source_event_id="gc-library", counterpart_world_character_id=IDS['진'],
                text="리오는 진과 도서관에서 별자리 관찰 계획을 이야기했다.", occurred_at=datetime(2026,9,1,tzinfo=UTC)),))


def cases(fixture, split):
    if split == 'development':
        return [dict(id=f'dev-{i}', question=q, route=r, kind=k, direction=d, target=t, language='ko')
                for i,(q,r,k,d,t) in enumerate(fixture['development'],1)]
    return [dict(id=f'held-{i}-{lang}', question=p[lang], language=lang,
                 **{k:p[k] for k in ('route','kind','direction','target')})
            for i,p in enumerate(fixture['heldout_pairs'],1) for lang in ('ko','en')]


def query_correct(case, executed):
    kind = case['kind']
    if kind is None: return None
    if not executed: return False
    direction = case['direction']
    if kind == 'pair':
        rows = [r for r in executed if r['operation']=='direct_relationship' and r['target']==IDS[case['target']]]
        return {r['direction'] for r in rows} == ({'incoming','outgoing'} if direction=='bidirectional' else {direction})
    if kind == 'collection':
        return all(r['operation'] in {'relationship_neighborhood','rank_related_characters'} and r['direction']==direction and r['target'] is None for r in executed)
    if kind == 'collection_then_pair':
        return (len(executed)>=2 and executed[0]['operation']=='rank_related_characters'
                and executed[0]['limit']==1 and executed[0]['direction']==direction
                and bool(executed[0]['people']) and executed[1]['operation']=='direct_relationship'
                and executed[1]['direction']==direction and executed[1]['target']==executed[0]['people'][0])
    operation = {'shared':'shared_neighbors','path':'shortest_path'}[kind]
    return any(r['operation']==operation and r['target']==IDS[case['target']] and r['direction']==direction for r in executed)


async def main(args):
    fixture = json.loads(args.inputs.read_text(encoding='utf-8'))
    selected = cases(fixture,args.split)
    repeats = 1 if args.split=='development' else 2
    options = {'NA':SelectionArgumentOptions(True), 'GC':SelectionArgumentOptions(True,False,True)}
    hashes = {p.relative_to(Path(__file__).parents[1]).as_posix():sha(p.read_bytes())
              for p in (Path(__file__).parents[1]/'app').rglob('*.py')}
    metadata = {'input_hash':sha(args.inputs.read_bytes()), 'source_hashes':hashes,
                'model':'gemini-3.1-flash-lite','thinking':'high','split':args.split,
                'requests':len(selected)*repeats*2,'deadline_seconds':95,'concurrency':2,
                'prompts':{n:sha(control_selection_system_prompt(o).encode()) for n,o in options.items()},
                'schemas':{n:sha(json.dumps([asdict(t) for t in control_selection_tools(o)],sort_keys=True).encode()) for n,o in options.items()},
                'scope':'Synthetic storage with real model calls and production retrieval services; no CRG or product writes; no FTS quality claim.'}
    if args.check:
        print(json.dumps({'preflight':'pass','requests':metadata['requests'],'model_calls':0,'credential_reads':0})); return
    args.output.mkdir(parents=True,exist_ok=True)
    if (args.output/'results.jsonl').exists(): raise ValueError('evaluation_already_started')
    if args.split=='heldout':
        previous=json.loads((args.output.parent/'development'/'metadata.json').read_text())
        if any(previous[k]!=metadata[k] for k in ('input_hash','source_hashes','prompts','schemas')):
            raise ValueError('candidate_changed_since_development')
    ledger_path=args.output.parent/'ledger.json'
    ledger=json.loads(ledger_path.read_text()) if ledger_path.exists() else {'maximum':122,'started':0}
    if ledger['maximum']!=122 or ledger['started']+metadata['requests']>122: raise ValueError('budget_exceeded')
    material,saved=read_material()
    if material.model!='gemini-3.1-flash-lite' or material.thinking_level!='high': raise ValueError('model_baseline_mismatch')
    write(args.output/'metadata.json',metadata)
    usage_context=ContextVar('gc_usage',default=None)
    originals={name:getattr(direct_llm,name) for name in ('generate_text','generate_json')}
    def measure(original):
        async def call(**kwargs):
            try: return await original(**kwargs)
            finally:
                usage=usage_context.get()
                if usage is not None:
                    tracker=kwargs['tracker']; summary=tracker.summary()
                    # Keep the tracker alive for this request: otherwise Python
                    # can reuse its id for a later planner and overwrite usage.
                    usage[str(id(tracker))]=(tracker, {'physical':tracker.provider_call_order_in_run,
                        'input_tokens':summary['total_prompt_tokens'],'output_tokens':summary['total_output_tokens'],
                        'thought_tokens':summary['total_thought_tokens']})
        return call
    for name,original in originals.items(): setattr(direct_llm,name,measure(original))
    semaphore=asyncio.Semaphore(2); rows=[]
    async def run(case,name,repeat):
        async with semaphore:
            ledger['started']+=1; write(ledger_path,ledger)
            row={'case':case['id'],'variant':name,'repeat':repeat,'expected':case['route'],'attempts':[]}
            obs=Observation(request_id=f"gc-{case['id']}-{name}-{repeat}",detailed=True)
            ot=current.set(obs); usage={}; ut=usage_context.set(usage); started=monotonic()
            recall=Recall(fixture)
            try:
                provider=DirectLlmSupervisorSelectionProvider(material,native_controls=True,code_coordination=True,graph_query_contract=name=='GC')
                class Observed:
                    async def route(self,request):
                        try:
                            result=await provider.route(request)
                        except Exception as exc:
                            row['attempts'].append({'phase':'repair' if request.repair_diagnostic else 'first','code':getattr(exc,'validation_code','unknown')}); raise
                        row['attempts'].append({'phase':'repair' if request.repair_diagnostic else 'first','code':'valid'}); return result
                now=datetime.now(UTC); deadline=now+timedelta(seconds=95)
                command=RetrievalPreflightCommand(obs.request_id,OWNER_ID,WORLD_ID,'synthetic-thread',IDS['하나'],SUBJECT_ID,case['question'])
                routing=await RetrievalRoutingService(router=Observed(),policy=Policy(case['language'])).route(command,
                    recent_context=(RetrievalRouterContextMessage('user','나는 하나(Hana)야.'),),now=now,deadline_at=deadline)
                row.update(route=routing.intent.route.value,intent=routing.intent.payload(),first_pass_valid=routing.metrics.first_pass_valid,tracker=routing.call_tracker)
                graph=GraphRetrievalPlanningService(planner=DirectLlmGraphRetrievalPlannerProvider(material),executor=GraphRetrievalPlanExecutor(recall))
                canonical=CanonicalRetrievalPlanningService(planner=DirectLlmCanonicalRetrievalPlannerProvider(material),executor=CanonicalRetrievalPlanExecutor(MemoryFixture()))
                now=datetime.now(UTC)
                common=dict(user_message=case['question'],intent=routing.intent,resolved=routing.resolved,call_tracker=routing.call_tracker)
                result=None
                if row['route']=='GRAPH': result=await graph.plan_and_execute(GraphRetrievalCommand(**common),now=now,deadline_at=deadline)
                elif row['route']=='CANONICAL': result=await canonical.plan_and_execute(CanonicalRetrievalCommand(**common,thread_id='synthetic-thread'),now=now,deadline_at=deadline)
                elif row['route']=='BOTH': result=await BothRetrievalWorkflowCoordinator(canonical=canonical,graph=graph).coordinate(BothRetrievalCommand(**common,thread_id='synthetic-thread'),now=now,deadline_at=deadline)
                if result is not None: row['tracker']=result.call_tracker
                row.update(status='ok',query_correct=query_correct(case,recall.executed))
                row['correct']=row['route']==case['route'] and row['query_correct'] is not False
            except Exception as exc:
                row.update(status='failed',correct=False,error_type=type(exc).__name__)
                diag=getattr(exc,'graph_failure_diagnostic',None) or getattr(exc,'router_diagnostic',None)
                if diag is not None: row['failure']=diag.payload()
                if getattr(exc,'call_tracker',None): row['tracker']=exc.call_tracker
            finally:
                current.reset(ot); usage_context.reset(ut)
            row.update(executed=recall.executed,diagnostics=obs.payload(),details=obs.details,usage=[value for _,value in usage.values()],elapsed_ms=round((monotonic()-started)*1000))
            with (args.output/'results.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(row,ensure_ascii=False)+'\n')
            rows.append(row)
            print(json.dumps({'completed':len(rows),'planned':metadata['requests'],'case':case['id'],'variant':name,'status':row['status'],'correct':row['correct']}),flush=True)
    try:
        await asyncio.gather(*(run(c,n,r) for r in range(repeats) for i,c in enumerate(selected) for n in (('NA','GC') if (i+r)%2==0 else ('GC','NA'))))
    finally:
        for name,original in originals.items(): setattr(direct_llm,name,original)
    summary={n:{'n':sum(r['variant']==n for r in rows),'correct':sum(r['correct'] for r in rows if r['variant']==n),
                'completed':sum(r['status']=='ok' for r in rows if r['variant']==n)} for n in options}
    write(args.output/'summary.json',summary); print(json.dumps(summary),flush=True)


if __name__=='__main__':
    logging.basicConfig(level=logging.ERROR)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--split',choices=['development','heldout'],required=True);parser.add_argument('--check',action='store_true')
    asyncio.run(main(parser.parse_args()))
