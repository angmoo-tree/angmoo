"""Same-transaction scope composition and unchanged fail-closed reads."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from model_fixture_support import models
from app.models import Base
from app.domains.memory.contracts.scope import MemoryScope
from app.domains.memory.exceptions import MemoryScopeError
from app.runtime.memory.composition import memory_batch_repository, memory_repository
from test_p8_l_f_memory_domain import _seed_scope


def test_memory_scope_timezone_sees_caller_flush_without_committing(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as caller:
        scope = _seed_scope(caller)
        world = caller.get(models.World, scope.world_id)
        world.timezone = "UTC"
        caller.flush()
        repository = memory_batch_repository(caller)
        assert repository.session is caller
        assert repository.memory._session is caller
        assert repository.timezone(scope) == "UTC"
        with Session(engine) as observer:
            assert observer.get(models.World, scope.world_id).timezone == "Asia/Seoul"
        caller.rollback()
        assert repository.timezone(scope) == "Asia/Seoul"
    engine.dispose()


@pytest.mark.parametrize("invalid", ["owner", "world", "subject"])
def test_memory_scope_keeps_three_reads_and_invalid_scope_error(tmp_path, invalid):
    engine = create_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as caller:
        scope = _seed_scope(caller)
        if invalid == "owner":
            scope = MemoryScope("another-owner", scope.world_id, scope.subject_world_character_id)
        elif invalid == "world":
            caller.get(models.World, scope.world_id).archived_at = datetime.now(UTC)
            caller.flush()
        else:
            caller.get(models.WorldCharacter, scope.subject_world_character_id).status = "left"
            caller.flush()
        statements = []

        def record(_conn, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        with pytest.raises(MemoryScopeError, match="^memory_scope_invalid$"):
            memory_repository(caller).validate_scope(scope)
        event.remove(engine, "before_cursor_execute", record)
        assert len(statements) == 3
        assert "FROM users" in statements[0]
        assert "FROM worlds" in statements[1]
        assert "FROM world_characters" in statements[2]
        caller.rollback()
    engine.dispose()
