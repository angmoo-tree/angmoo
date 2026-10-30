"""Real PostgreSQL upgrade and historical-request progress, no external AI."""
from datetime import UTC, datetime
from uuid import uuid4
from sqlalchemy import text,select
from sqlalchemy.orm import Session
from postgresql.test_activity_transactions import store
from memory.test_maintenance_rounds import closed_fixture
from app.domains.memory.service import consolidation_requests as service
from app.runtime.relationships.manual_review_worker import advance_manual_requests
from app.runtime.relationships.manual_review import ManualRelationshipFollowup
from app.domains.relationships.models.personalization import RelationshipReviewWork as Work,RelationshipReviewMemoryReceipt as Receipt
from app.domains.relationships.models.manual_review import RelationshipReviewRequest as Request
from app.domains.memory.models.consolidation_request import MemoryConsolidationRequest
from app.runtime.persistence.postgresql_schema import initialize,VERSION


def test_v4_upgrade_repairs_later_request_preserving_original_failure_and_results(store,monkeypatch):
    engine,_,_=store
    with Session(engine,expire_on_commit=False) as db:
        scope,workflows,data,original,old,payloads,future=closed_fixture(db,monkeypatch)
        payloads.extend(future)
        result=service.submit(scope=scope,db=db,workflows=workflows,data=data.model_copy(update={'idempotency_key':uuid4().hex}))
        finish=db.get(MemoryConsolidationRequest,result['request_id']);finish.state='queued';db.commit()
        advance_manual_requests(db,datetime.now(UTC));db.commit()
        request=db.get(Request,result['request_id']);new=db.get(Work,request.work_ids[0])
        new.status,new.result='applied',{'decision':'keep'}
        for receipt in db.scalars(select(Receipt).where(Receipt.work_id==new.id)):receipt.status='applied'
        for receipt in db.scalars(select(Receipt).where(Receipt.work_id==old.id)):receipt.status,receipt.reason='pending',None
        request.snapshot=request.snapshot+original.snapshot;request.work_ids=request.work_ids+[old.id];request.state='closed'
        frozen=list(request.snapshot);old_frozen=list(original.snapshot);db.commit()
        request_id,old_id,original_id=request.memory_request_id,old.id,original.memory_request_id
    with engine.begin() as connection:
        connection.execute(text('UPDATE angmoo_postgresql_schema_version SET version=4'))
        initialize(connection)
        assert connection.execute(text('SELECT version FROM angmoo_postgresql_schema_version')).scalar_one()==VERSION
        initialize(connection)
    with Session(engine) as db:
        request=db.get(Request,request_id)
        assert request.snapshot==frozen and db.get(Request,original_id).snapshot==old_frozen
        progress=ManualRelationshipFollowup(db).extend(db.get(MemoryConsolidationRequest,request_id),{'state':'completed','accepted_at':request.accepted_at})
        assert progress['flow_state']=='completed'
        assert (progress['relationship']['target_count'],progress['relationship']['completed_count'],progress['relationship']['kept_count'])==(1,1,1)
        assert db.get(Work,old_id).status=='failed' and db.get(Request,original_id).state=='closed'
