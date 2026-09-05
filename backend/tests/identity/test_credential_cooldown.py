from datetime import UTC, datetime, timedelta

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.cruds.agent_runs import get_credential
from app.domains.identity.service.credential_cooldown import set_cooldown_until
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_credential_cooldown_mutation_keeps_caller_identity_no_sql_and_rollback(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        _seed(db)
        credential = get_credential(db, 'credential-routine')
        previous = datetime(2026, 9, 6, 9, tzinfo=UTC)
        credential.cooldown_until = previous
        db.commit()
        sql = []
        def record(_connection, _cursor, statement, _parameters, _context, _many):
            sql.append(statement)
        event.listen(engine, 'before_cursor_execute', record)
        for value in [None, previous + timedelta(hours=1)]:
            _ = credential.cooldown_until
            count = len(sql)
            assert set_cooldown_until(credential, cooldown_until=value) is None
            assert credential.cooldown_until is value
            assert credential in db.dirty
            assert len(sql) == count
            with Session(engine) as observer:
                assert get_credential(observer, credential.id).cooldown_until.replace(tzinfo=UTC) == previous
            db.rollback()
            assert credential.cooldown_until.replace(tzinfo=UTC) == previous
        event.remove(engine, 'before_cursor_execute', record)
    engine.dispose()
