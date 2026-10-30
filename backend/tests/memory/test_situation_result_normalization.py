"""New output normalization is retained; legacy mismatch never rereads originals."""
from dataclasses import replace
from types import SimpleNamespace
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import pytest
from sqlalchemy import select, func
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from memory.test_activity_situation_contract import NOW, values
from memory.test_situation_delivery_recovery import durable_stack
from memory.test_activity_situation_application import real_source
from memory.test_situation_recovery_actions import recheck
from app.domains.memory.contracts.activity_situation import CommittedEffect, stable_digest
from app.domains.memory.models.activity_situation import MemorySituationManifest
from app.domains.memory.models.items import MemoryItem
from app.domains.memory.models.situation_result_binding import MemorySituationResultBinding
from app.domains.memory.repository.situation_admission import admit
from app.domains.memory.repository.situation_apply import apply_page
from app.domains.memory.repository.situation_runs import claim_run
from app.domains.memory.repository.situation_validation import restore_context
from app.domains.social.utils.situation_output import stored_output
from app.runtime.memory.situation_sources import SituationSources
from app.runtime.memory.situation_result_basis import CheckpointResultBasis
from app.runtime.autonomous_activity.situation_memory import participant


def historical(db, scope, checkpoint, *, wrong=False):
    post = real_source(db, scope)
    raw = {"action": "post", "target": post.id, "title": "하루\t기록", "body": "약속을 기다렸다.  \r\n\r\n\r\n산책했다.  "}
    actual = stored_output(raw)
    post.title, post.body = actual["title"], actual["body"]
    db.commit()
    manifest, draft, result = values(db, scope, target="routine-post", logical="historic-normalization")
    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/input/body", role="core", ordinal=0, target="routine-post")
    output = replace(source, role="committed_result", ordinal=1, payload_path="/committed_result/body")
    manifest = replace(manifest, sources=(source,))
    result = replace(result, lane="routine", planned_effects=("post",), effects=(CommittedEffect("post", "POST", post.id, "succeeded"),),
        planned_output_digest=stable_digest(raw), final_output_digest=stable_digest(actual), result_sources=(output,))
    row = admit(db, manifest=manifest, draft=draft, result=result, now=NOW)
    db.commit()
    assert row.state == "blocked" and raw != actual
    final = {"title": raw["title"], "body": raw["body"] + ("다른 내용" if wrong else "")}
    state = {"identity": {"activity_id": result.logical_activity_id}, "decision": {
        "_situation_manifest": manifest.to_dict(), "_situation_normalized_draft": final}}
    kind, data = JsonPlusSerializer().dumps_typed({"channel_values": state})
    with closing(sqlite3.connect(checkpoint)) as cp, cp:
        cp.execute("CREATE TABLE checkpoints(thread_id TEXT,checkpoint_ns TEXT,checkpoint_id TEXT,type TEXT,checkpoint BLOB)")
        cp.execute("INSERT INTO checkpoints VALUES(?,?,?,?,?)", ("activity:" + row.logical_activity_id, "RoutineActivityGraph:final", "1", kind, data))
    return row, post


def consume(db, memory, request, path):
    token = claim_run(db, request.run_id, now=NOW)
    db.commit()
    apply_page(db, memory, SituationSources(db, result_basis=CheckpointResultBasis(path)),
        run_id=request.run_id, token=token, now=NOW)
    db.commit()


def test_legacy_result_mismatch_stays_blocked_without_runtime_reconstruction(durable_stack, tmp_path):
    db, scope, setting, memory = durable_stack
    cp = tmp_path / "checkpoint.sqlite"
    row, post = historical(db, scope, cp)
    original = row.content_digest, stable_digest(row.result), stable_digest(db.get(MemorySituationManifest, row.manifest_id).payload)
    request = recheck(db, setting, row=row)
    consume(db, memory, request, cp)
    assert row.state == "blocked" and row.error_code == "situation_success_binding_invalid"
    assert db.scalar(select(func.count()).select_from(MemorySituationResultBinding)) == 0
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0
    assert original == (row.content_digest, stable_digest(row.result), stable_digest(db.get(MemorySituationManifest, row.manifest_id).payload))
    cp.unlink()
    with pytest.raises(ValueError, match="success_binding_invalid"):
        restore_context(db, row)
    post.body += " 실제 수정"
    db.commit()
    with pytest.raises(ValueError, match="success_binding_invalid"):
        restore_context(db, row)


@pytest.mark.parametrize("failure", ["wrong-draft", "missing-checkpoint", "changed-source", "closed-epoch", "missing-description"])
def test_failed_rechecks_leave_no_proof_or_memory(durable_stack, tmp_path, failure):
    db, scope, setting, memory = durable_stack
    cp = tmp_path / "checkpoint.sqlite"
    row, post = historical(db, scope, cp, wrong=failure == "wrong-draft")
    if failure == "missing-checkpoint": cp.unlink()
    if failure == "changed-source": post.title += " 내용 변경"
    if failure == "missing-description":
        # A tampered invalid original is rejected, never repaired from an AI or
        # another target's description.
        row.description = None
    db.commit()
    request = recheck(db, setting, row=row)
    if failure == "closed-epoch":
        from app.domains.memory.models.batch import MemoryActivationEpoch
        db.get(MemoryActivationEpoch, row.activation_epoch).closed_at = NOW
        db.commit()
    consume(db, memory, request, cp)
    assert row.state == "blocked"
    assert db.scalar(select(func.count()).select_from(MemorySituationResultBinding)) == 0
    assert db.scalar(select(func.count()).select_from(MemoryItem)) == 0


def test_current_receipt_capacity_rolls_back_memory_and_snapshot_together(durable_stack,monkeypatch):
    from memory.test_experience_snapshots import captured
    from memory.test_activity_situation_application import apply
    from app.domains.memory.exceptions import MemoryCapacityReached
    from app.domains.memory.models.experience import MemoryExperienceSnapshot
    db,scope,setting,memory=durable_stack
    post=real_source(db,scope)
    manifest,draft,result=captured(db,scope,post)
    row=admit(db,manifest=manifest,draft=draft,result=result,now=NOW);db.commit()
    assert row.state=='pending'
    monkeypatch.setattr('app.domains.memory.repository.situation_apply.STORAGE_LIMIT',0)
    with pytest.raises(MemoryCapacityReached):apply(db,setting,memory)
    db.rollback()
    assert row.state=='pending' and row.description==draft.description
    assert db.scalar(select(func.count()).select_from(MemoryItem))==0
    assert db.scalar(select(func.count()).select_from(MemoryExperienceSnapshot))==0


@pytest.mark.parametrize("body,title", [("줄 끝  \n다음 줄\t\n\n\n마지막  ", "두\n줄"), ("문자\\n개행\\t  ", "여러  공백"), ("한글🙂\r\n끝", "제목")])
def test_new_routine_admission_projects_social_text_once(durable_stack, body, title):
    db, scope, setting, memory = durable_stack
    post = real_source(db, scope)
    raw = {"action": "post", "target": post.id, "body": body, "title": title}
    actual = stored_output(raw)
    post.body, post.title = actual["body"], actual["title"]
    db.commit()
    manifest, draft, _ = values(db, scope, target="routine-post")
    source = SituationSources(db).describe(scope, kind="POST", identifier=post.id, delivered=post.body,
        path="/input/body", role="core", ordinal=0, target="routine-post")
    manifest = replace(manifest, sources=(source,))
    state = {"identity": {"activity_id": "new-post"}, "decision": {"_situation_manifest": manifest.to_dict(),
        "_situations": {"routine-post": {"target_key": draft.target_key, "description": draft.description, "status": draft.status, "error_code": None}},
        "_situation_normalized_draft": {"title": title, "body": body}}}
    callback = participant(SimpleNamespace(lane="routine"), state, "routine-post")
    callback(db, SimpleNamespace(status="succeeded", action_type="post", target_post_id=post.id, id=-1), {"post_id": post.id}, NOW)
    from app.domains.memory.models.activity_situation import MemorySituationReceipt
    receipt = db.scalar(select(MemorySituationReceipt))
    assert receipt.state == "pending", receipt.error_code
    assert receipt.result["planned_output_digest"] == stable_digest(actual)
    assert receipt.result["final_output_digest"] == stable_digest(actual)
    db.commit()
    from memory.test_activity_situation_application import apply
    apply(db, setting, memory)
    assert receipt.state == "applied", receipt.error_code


@pytest.mark.parametrize("field", ["body", "title"])
def test_missing_or_non_text_fields_are_not_coerced(field):
    for bad in (None, 42, {}, []):
        with pytest.raises(ValueError, match="expected_text_invalid"):
            stored_output({"action": "post", "target": None, "body": "본문", "title": "제목", field: bad})


@pytest.mark.parametrize("lane", ["inbox", "feed"])
def test_legacy_reply_format_mismatch_does_not_infer_a_new_result(durable_stack, tmp_path, lane):
    from memory.test_situation_delivery_recovery import delivered_reply
    from app.domains.memory.contracts.activity_situation import DeliveredInputManifest
    from app.domains.memory.policies.situation_output import parse_description
    from app.domains.social.models.posts import Post
    db, scope, setting, memory = durable_stack
    previous, incoming = delivered_reply(db, scope)
    response=db.get(Post,"committed-subject-reply")
    body="고마워요.  \n차를 마시며 쉬어요.\t "
    raw={"action":"reply","target":incoming.id,"body":body}
    actual=stored_output(raw);response.body=actual["body"];db.commit()
    manifest=replace(DeliveredInputManifest.from_dict(db.get(MemorySituationManifest,previous.manifest_id).payload),call_identity="reply-normalization-call")
    output=SituationSources(db).describe(scope,kind="REPLY",identifier=response.id,delivered=response.body,
        path="/committed_result/body",role="committed_result",ordinal=1,target=incoming.id)
    _,_,result=values(db,scope,target=incoming.id,logical="reply-normalization")
    result=replace(result,lane=lane,planned_effects=("reply",),effects=(CommittedEffect("reply","REPLY",response.id,"succeeded"),),
        planned_output_digest=stable_digest(raw),final_output_digest=stable_digest(actual),result_sources=(output,))
    row=admit(db,manifest=manifest,draft=parse_description("안부를 읽고 답글을 남겼다.",target_key=incoming.id),result=result,now=NOW);db.commit()
    cp=tmp_path/'reply-checkpoint.sqlite'
    state={"identity":{"activity_id":row.logical_activity_id},"lane_data":{incoming.id:{"post_id":incoming.id}},
        "decision":{"decisions":[{"target_id":incoming.id,"action":"comment"}],
        "_situation_overrides":{incoming.id:{"manifest":manifest.to_dict(),"normalized":{"replies":[{"target_id":incoming.id,"body":body}]}}}}}
    kind,data=JsonPlusSerializer().dumps_typed({"channel_values":state})
    with closing(sqlite3.connect(cp)) as connection,connection:
        connection.execute("CREATE TABLE checkpoints(thread_id TEXT,checkpoint_ns TEXT,checkpoint_id TEXT,type TEXT,checkpoint BLOB)")
        connection.execute("INSERT INTO checkpoints VALUES(?,?,?,?,?)",("activity:"+row.logical_activity_id,lane.title()+"ActivityGraph:writer","1",kind,data))
    request=recheck(db,setting,row=row);consume(db,memory,request,cp)
    assert row.state=="blocked" and row.error_code=="situation_success_binding_invalid"
    assert db.scalar(select(func.count()).select_from(MemorySituationResultBinding))==0


@pytest.mark.parametrize("revision",["situation-validation.v2","situation-validation.v3"])
def test_old_run_cannot_approve_new_result_proofs(durable_stack,tmp_path,revision):
    from app.domains.memory.models.activity_situation import MemorySituationApplyRun
    db,scope,setting,memory=durable_stack
    cp=tmp_path/'old-run.sqlite';row,_=historical(db,scope,cp)
    request=recheck(db,setting,row=row)
    run=db.get(MemorySituationApplyRun,request.run_id)
    run.settings_snapshot={**run.settings_snapshot,"validation_revision":revision};db.commit()
    consume(db,memory,request,cp)
    assert row.state=="blocked" and row.error_code=="situation_success_binding_invalid"
    assert db.scalar(select(func.count()).select_from(MemorySituationResultBinding))==0
