"""Auxiliary diagnostics must not expose text or become commit/AI owners."""
from types import SimpleNamespace
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.runtime.diagnostics.situation_observation import output_shape, safe_event, after_receipt_commit, CAPABILITY
from app.runtime.diagnostics.situation_coverage import coverage
from tests.runtime.test_sns_observation import data_root as observer_data_root


@pytest.mark.parametrize("raw,reason,status", [("absent","field_absent","missing"), (None,"field_null","missing"),
    (False,"field_type_invalid","invalid"), ([],"empty_list","missing"),
    ([{"target_id":"another","description":"text"}],"target_missing","missing"),
    ([{"target_id":"p1"}],"description_absent","missing"),
    ([{"target_id":"p1","description":None}],"description_null","missing"),
    ([{"target_id":"p1","description":4}],"description_type_invalid","invalid"),
    ([{"target_id":"p1","description":" "}],"description_empty","invalid"),
    ([{"target_id":"p1","description":"가"*1001}],"description_too_long","invalid"),
    ([{"target_id":"p1","description":"\ud800"}],"description_unicode_invalid","invalid"),
    ([{"target_id":"p1","description":"secretword"}],"valid","valid")])
def test_detailed_reasons_preserve_parser_and_never_emit_description(raw, reason, status):
    payload={"decision":{},"draft":{}}
    if raw != "absent": payload["situations"]=raw
    facts=output_shape(payload,("p1",))
    assert facts["entries"][0]["reason"] == reason
    assert facts["entries"][0]["status"] == status
    assert "secretword" not in json.dumps(safe_event(facts))


def test_duplicate_order_invalid_target_and_limits():
    payload={"situations":[{"target_id":"p1","description":"내용"}]*2 + [{"target_id":None}], "decision":{},"draft":{}}
    facts=output_shape(payload,("p1",))
    assert not facts["order_valid"] and facts["invalid_target_count"] == 1
    assert facts["entries"][0]["reason"] == "target_duplicate"
    assert facts["entries"][0]["status"] == "output_order_invalid"
    assert len(output_shape({}, tuple(f"p{i}" for i in range(20)))["entries"]) == 16


@pytest.mark.parametrize("rollback", [True, False])
def test_receipt_diagnostic_follows_existing_outer_commit_only(rollback):
    received=[]
    tracker=SimpleNamespace(observer=True,_notify=lambda kind,payload:received.append((kind,payload)))
    receipt=SimpleNamespace(sequence=1,lane="routine",state="pending",description_status="valid",target_key="routine-post",error_code=None)
    with Session(create_engine("sqlite://")) as db:
        db.begin()
        with db.begin_nested():
            after_receipt_commit(db,tracker,receipt,decision={},override=None,raw_digest="a"*64,normalized_digest="b"*64,actual_digest="b"*64)
        assert not received
        (db.rollback if rollback else db.commit)()
        assert len(received) == int(not rollback)


def test_old_export_is_unsupported_and_missing_commit_is_diagnostic_loss():
    _,old=coverage({},[],[],damaged=0,dropped=0,canonical={})
    assert old["situation_evidence_complete"] == "unsupported"
    _,new=coverage({"capabilities":[CAPABILITY]},[],[{"sequence":1}],damaged=0,dropped=0,canonical={"canonical_receipt_support":"supported"})
    assert new["diagnostic_loss_not_admission_failure"] == 1 and not new["situation_evidence_complete"]


def test_carry_in_baseline_receipts_are_not_missing_new_commit_events():
    import sqlite3
    from app.runtime.diagnostics.situation_coverage import canonical_receipts
    with sqlite3.connect(':memory:') as db:
        db.row_factory=sqlite3.Row
        db.executescript('CREATE TABLE memory_scope_settings(id TEXT,world_id TEXT,subject_world_character_id TEXT);'
            'CREATE TABLE memory_situation_receipts(sequence INTEGER,scope_setting_id TEXT,logical_activity_id TEXT,'
            'lane TEXT,target_key TEXT,state TEXT,description_status TEXT,error_code TEXT,captured_at TEXT);'
            "INSERT INTO memory_scope_settings VALUES('scope','world','actor');")
        db.executemany('INSERT INTO memory_situation_receipts VALUES(?,?,?,?,?,?,?,?,?)',[
            (1,'scope','carry','inbox','old','blocked','valid','situation_result_mismatch','2026-10-10 00:00:00'),
            (2,'scope','carry','feed','new','pending','valid',None,'2026-10-10 01:00:00'),
            (3,'scope','carry','routine','late','pending','valid',None,'2026-10-10 05:00:00')])
        rows,facts=canonical_receipts(db,{'world_id':'world','actor_ids':['actor'],
            'started_at':'2026-10-10T09:28:13+09:00','tail_ends_at':'2026-10-10T13:58:13+09:00'},{'carry'})
        assert [row['sequence'] for row in rows]==[2]
        assert facts['canonical_baseline_states']=={'blocked':1} and facts['canonical_states']=={'pending':1}
        assert facts['current_blocked_count']==0 and facts['window_receipt_count']==1


def test_coverage_requires_the_selected_physical_stage_and_payload():
    attempt = {"provider_call_order": 1, "call_order": 1, "json_attempt": 1,
        "stage_attempt_id": "writer-final", "input_payload_hash": "a" * 64}
    def record(kind, **changes):
        return {"activity_id": "activity", "lane": "feed", "node": "FeedWriter",
            "event_type": kind, "details": {**attempt, **changes}}
    base = [record("input_manifest", situation_expected=True),
        record("llm_call", status="ok", call_type="generate_content"), record("llm_json_attempt", status="valid"),
        record("situation_output_shape"), record("situation_output_parsed"),
        record("situation_receipt_committed", receipt_sequence=1)]
    def inspect(events):
        return coverage({"capabilities": [CAPABILITY]}, events, [{"sequence": 1}], damaged=0, dropped=0,
            canonical={"canonical_receipt_support": "supported"})[1]
    assert inspect(base)["situation_evidence_complete"] is True
    wrong = [*base[:-1], record("situation_receipt_committed", receipt_sequence=1, stage_attempt_id="writer-old")]
    assert inspect(wrong)["correlation_ambiguous"] == 1 and not inspect(wrong)["situation_evidence_complete"]
    collision = [*base, record("situation_output_shape", stage_attempt_id="resumed-stage")]
    assert inspect(collision)["correlation_ambiguous"] == 1 and not inspect(collision)["situation_evidence_complete"]


def test_off_and_failing_diagnostic_sink_cannot_change_a_transaction():
    receipt = SimpleNamespace(sequence=1, lane="routine", state="pending", description_status="valid",
        target_key="routine-post", error_code=None)
    def fail(*args):
        raise OSError("synthetic diagnostic sink failure")
    with Session(create_engine("sqlite://")) as db:
        db.begin()
        after_receipt_commit(db, SimpleNamespace(observer=None), receipt, decision={}, override=None,
            raw_digest="a"*64, normalized_digest="b"*64, actual_digest="b"*64)
        assert "situation_diagnostics" not in db.info
        after_receipt_commit(db, SimpleNamespace(observer=True, _notify=fail), receipt, decision={}, override=None,
            raw_digest="a"*64, normalized_digest="b"*64, actual_digest="b"*64)
        db.commit()
        assert "situation_diagnostics" not in db.info


@pytest.mark.parametrize('missing_file',['situation-evidence.jsonl','situation-evidence-coverage.json'])
def test_auxiliary_export_failure_preserves_the_core_export(observer_data_root,tmp_path,monkeypatch,missing_file):
    from datetime import datetime, UTC, timedelta
    from app.runtime.diagnostics import sns_observation_report as reports
    now=datetime.now(UTC)
    manifest=reports.start_session(observer_data_root,world_id='world-1',actor_ids=['actor-1'],now=now)
    reports.stop_session(observer_data_root,manifest['session_id'],now=now+timedelta(seconds=1))
    reports.export_session(observer_data_root,manifest['session_id'],destination=tmp_path/'baseline',now=now+timedelta(seconds=2))
    original_jsonl,original_json=reports._jsonl,reports._atomic_json
    def jsonl(path,values):
        if path.name==missing_file: raise OSError('synthetic auxiliary export failure')
        return original_jsonl(path,values)
    def atomic_json(path,values):
        if path.name==missing_file: raise OSError('synthetic auxiliary export failure')
        return original_json(path,values)
    monkeypatch.setattr(reports,'_jsonl',jsonl)
    monkeypatch.setattr(reports,'_atomic_json',atomic_json)
    reports.export_session(observer_data_root,manifest['session_id'],destination=tmp_path/'partial',now=now+timedelta(seconds=2))
    actual=json.loads((tmp_path/'partial/coverage.json').read_text())
    baseline=json.loads((tmp_path/'baseline/coverage.json').read_text())
    assert datetime.fromisoformat(actual.pop('database_extracted_at')) >= datetime.fromisoformat(baseline.pop('database_extracted_at'))
    assert actual==baseline
    if missing_file.endswith('jsonl'):
        result=json.loads((tmp_path/'partial/situation-evidence-coverage.json').read_text())
        assert result['situation_evidence_complete'] is False and result['export_error']=='situation_export_failed'
    else:
        assert not (tmp_path/'partial/situation-evidence-coverage.json').exists()


def test_rolled_back_savepoint_never_emits_at_later_outer_commit():
    received=[]
    tracker=SimpleNamespace(observer=True,_notify=lambda *args:received.append(args))
    receipt=SimpleNamespace(sequence=1,lane="routine",state="pending",description_status="valid",target_key="routine-post",error_code=None)
    with Session(create_engine("sqlite://")) as db:
        db.begin()
        nested=db.begin_nested()
        after_receipt_commit(db,tracker,receipt,decision={},override=None,raw_digest="a"*64,normalized_digest="b"*64,actual_digest="b"*64)
        nested.rollback()
        db.commit()
    assert not received


def test_actual_json_attempt_context_precedes_base_failure_and_tracks_retry(monkeypatch):
    import asyncio
    from app.integrations import direct_llm as transport
    calls=[];events=[]
    async def fake(**kwargs):
        calls.append(kwargs)
        return transport.DirectLlmResponse('',{'decision':{},'draft':{},'situations':None},{},
            call_order=len(calls),provider_call_order=len(calls)+4)
    monkeypatch.setattr(transport,'generate_text',fake)
    def validate(value):
        if len(calls)==1: raise ValueError('base_invalid')
        return {'base':'valid'}
    context=transport.DirectLlmCallContext('synthetic',None,None,'FeedDecisionDraft','feed','google','synthetic')
    result=asyncio.run(transport.generate_json(api_key='synthetic',context=context,tracker=transport.RunLlmTracker(),
        system_prompt='synthetic',user_prompt='synthetic',response_schema={},validator=validate,
        on_json_object=lambda value,attempt:events.append(('before',dict(attempt))),
        on_json_validated=lambda value,base,attempt:events.append(('after',dict(attempt)))))
    assert result=={'base':'valid'} and len(calls)==2
    assert events==[('before',{'call_order':1,'provider_call_order':5,'json_attempt':1}),
        ('before',{'call_order':2,'provider_call_order':6,'json_attempt':2}),
        ('after',{'call_order':2,'provider_call_order':6,'json_attempt':2})]


def test_combined_callback_keeps_actual_node_and_selected_final_attempt(monkeypatch):
    import asyncio
    from sqlalchemy.orm import Session
    from runtime.test_activity_combined_delivery import fixture
    from social.test_feed_reaction_intent import _engine
    from memory.test_activity_situation_receipt import enabled
    from app.runtime.autonomous_activity import provider as transport
    from app.runtime.diagnostics.situation_observation import stage_attempt
    async def scenario():
        with Session(_engine(),expire_on_commit=False) as db:
            lane,state,_,post=fixture(db)
            lane.provider.situation_snapshot=enabled(db,lane)
            state.update(await lane.load(state));lane.provider.situation_state=state
            events=[];lane.tracker.observer=lambda kind,value:events.append((kind,value))
            async def fake(**kwargs):
                value={'decision':{'decisions':[{'target_id':post.id,'action':'like','brief':'공감'}],
                    'state_update':None,'relationship_metrics':[]},'draft':{'replies':[]},
                    'situations':[{'target_id':post.id,'description':'privatedescription'}]}
                attempt={'call_order':1,'provider_call_order':3,'json_attempt':1}
                kwargs['on_json_object'](value,attempt)
                result=kwargs['validator'](value)
                kwargs['on_json_validated'](value,result,attempt)
                return result
            monkeypatch.setattr(transport,'generate_json',fake)
            monkeypatch.setattr(transport,'_api_key',lambda _: 'synthetic')
            monkeypatch.setattr(transport,'_llm_context',lambda *args,**kwargs:None)
            token=stage_attempt.set('stage-1')
            try:result=await lane.provider.plan(lane='feed',context={},candidates=state['candidates'])
            finally:stage_attempt.reset(token)
            assert result['_situation_attempt']['node']=='FeedDecisionDraft'
            assert result['_situation_attempt']['provider_call_order']==3
            assert result['_situation_attempt']['stage_attempt_id']=='stage-1'
            observed=[value for kind,value in events if kind in {'situation_output_shape','situation_output_parsed'}]
            assert len(observed)==2 and 'privatedescription' not in json.dumps(observed)
    asyncio.run(scenario())
