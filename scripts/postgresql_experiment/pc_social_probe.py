import pathlib,sys,json,uuid
from dataclasses import replace
ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
from pc_schema_probe import pc_engine
from app.database import create_session_factory
from app.core.sqlite_concurrency import SqliteRetryPolicy
from app.runtime.persistence.postgresql_schema import metadata
from social.test_l4_social_write_uow import _seed,_owner_post,_autonomous_post
from app.domains.identity.models import User
from app.runtime.social.sqlalchemy_unit_of_work import SqlAlchemySocialWriteUnitOfWork
metadata()
engine=pc_engine();factory=create_session_factory(engine)
with factory() as db:exists=db.get(User,'social-uow-owner') is not None
if not exists:_seed(factory)
key=uuid.uuid4().hex
policy=SqliteRetryPolicy(maximum_elapsed_seconds=5,max_attempts=6)
with factory() as db:
    command=replace(_owner_post(),idempotency_key='pg-'+key)
    first=SqlAlchemySocialWriteUnitOfWork(db,retry_policy=policy).create_owner_post(command)
    second=SqlAlchemySocialWriteUnitOfWork(db,retry_policy=policy).create_owner_post(command)
    assert first.post.id==second.post.id and second.replayed
    print(json.dumps({'post':first.post.id,'idempotency':'pass'}))
