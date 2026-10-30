"""Actual PostgreSQL: single-thread admission invariants and independent work."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Event, Lock

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from postgresql.test_activity_transactions import store
from postgresql.test_chat_storage import prepare
from app.core.database_transactions import database_write
from app.domains.characters.models import Character
from app.domains.world_characters.models import WorldCharacter, CharacterActiveWorld
from app.runtime.world_characters.creation_configuration import initialize_created_world_character
from app.domains.chat.models import MessageThread, MessageMessage, ChatResponseRequest
from app.domains.chat.schemas import WorldChatMessageCreate, WorldChatRetryCreate
from app.domains.chat.exceptions import MessageInFlightError, MessageValidationError, MessageNotFoundError
from app.domains.chat.service.generation import GenerationService
from app.domains.identity.models import User
from app.runtime.chat.message_composition import thread_service, settings_service
from app.runtime.chat import generation_workflows


def _service(monkeypatch):
    service = GenerationService(thread_service, settings_service, generation_workflows)
    # Only provider configuration is synthetic. All ownership, role, thread,
    # duplicate, lifecycle, trigger and transaction operations remain real.
    monkeypatch.setattr(service, '_request_names', lambda *args: {})
    monkeypatch.setattr(thread_service, 'resolve_world_thread_response_model',
                        lambda *args: 'gemini-3-flash-preview')
    return service


def _independent_threads(engine):
    prepare(engine)
    with Session(engine) as db:
        original = db.get(Character, 'social-uow-autonomous-character')
        actor = db.get(WorldCharacter, 'social-uow-autonomous-actor')
        thread = db.get(MessageThread, 'chat-one')
        for suffix in ('two', 'three'):
            values = {c.name: getattr(original, c.name) for c in Character.__table__.columns}
            values.update(id='parallel-'+suffix, handle='parallel-'+suffix, name='Parallel '+suffix)
            character = Character(**values)
            db.add(character)
            db.flush()
            values = {c.name: getattr(actor, c.name) for c in WorldCharacter.__table__.columns}
            values.update(id='actor-'+suffix, character_id=character.id)
            role = WorldCharacter(**values)
            db.add(role)
            db.flush()
            initialize_created_world_character(db, character=character, world_character=role)
            db.add(CharacterActiveWorld(character_id=character.id, world_character_id=role.id,
                idempotency_key='parallel-active-'+suffix, selected_at=datetime.now(UTC)))
            values = {c.name: getattr(thread, c.name) for c in MessageThread.__table__.columns}
            values.update(id='chat-'+suffix, character_id=character.id, responding_world_character_id=role.id)
            db.add(MessageThread(**values))
        db.commit()


def test_independent_text_admissions_survive_concurrent_workflow_checkpoints(store, monkeypatch):
    engine, _, _ = store
    _independent_threads(engine)
    service = _service(monkeypatch)
    ready, finished, first_lock = Event(), Event(), Lock()
    barrier, first, checkpoints = Barrier(3), [], []

    def delay(*args):
        # Reproduce the PRoot case: the first accepted chat starts persisting
        # progress while other independent admissions are still validating.
        time.sleep(0.015)

    def admit(suffix):
        with Session(engine) as db:
            owner = db.get(User, 'social-uow-owner')
            barrier.wait(timeout=10)
            value = service.accept_world_message(db, owner, 'social-uow-world', 'chat-'+suffix,
                WorldChatMessageCreate(content='synthetic concurrent admission', idempotency_key='parallel-request-'+suffix))
            with first_lock:
                if not first:
                    first.append((suffix, value.response_request.request_id))
            ready.set()
            return value

    def checkpoint_loop():
        assert ready.wait(10)
        suffix, request_id = first[0]
        # At least one real committed checkpoint overlaps the admission group.
        while True:
            with Session(engine) as db:
                owner = db.get(User, 'social-uow-owner')
                def checkpoint():
                    service._mutation_thread(db, owner, 'social-uow-world', 'chat-'+suffix)
                    row = db.get(ChatResponseRequest, request_id)
                    row.node_state_json = json.dumps({'synthetic_checkpoint': len(checkpoints)})
                    db.flush()
                database_write(db, checkpoint)
                checkpoints.append(True)
            if finished.is_set():
                return

    event.listen(engine, 'before_cursor_execute', delay)
    try:
        with ThreadPoolExecutor(4) as executor:
            worker = executor.submit(checkpoint_loop)
            try:
                outcomes = list(executor.map(admit, ('one', 'two', 'three')))
            finally:
                finished.set()
            worker.result(timeout=10)
    finally:
        event.remove(engine, 'before_cursor_execute', delay)
    assert [result.outcome for result in outcomes] == ['accepted'] * 3
    assert checkpoints
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MessageMessage)) == 3
        assert db.scalar(select(func.count()).select_from(ChatResponseRequest)) == 3
        assert db.scalar(text('SHOW transaction_isolation')) == 'serializable'


@pytest.mark.parametrize('same_key', [True, False])
def test_same_thread_concurrent_admission_keeps_idempotency_and_one_active_request(store, monkeypatch, same_key):
    engine, _, _ = store
    prepare(engine)
    service, barrier = _service(monkeypatch), Barrier(2)

    def admit(number):
        with Session(engine) as db:
            owner = db.get(User, 'social-uow-owner')
            barrier.wait(timeout=10)
            try:
                return service.accept_world_message(db, owner, 'social-uow-world', 'chat-one',
                    WorldChatMessageCreate(content='same payload',
                        idempotency_key='same-thread-request-'+str(0 if same_key else number))).outcome
            except MessageInFlightError:
                return 'in_flight'

    with ThreadPoolExecutor(2) as executor:
        outcomes = list(executor.map(admit, (1, 2)))
    assert sorted(outcomes) == sorted(['accepted', 'replayed' if same_key else 'in_flight'])
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MessageMessage)) == 1
        assert db.scalar(select(func.count()).select_from(ChatResponseRequest)) == 1


def test_text_admission_revalidates_revocation_after_its_initial_snapshot(store, monkeypatch):
    engine, _, _ = store
    prepare(engine)
    service, changed = _service(monkeypatch), []

    def revoke(connection, cursor, statement, params, context, many):
        if changed or not statement.startswith('SELECT installation_identities.singleton_key'):
            return
        # The caller owner read has established a snapshot, but its shared
        # scope fences have not yet been acquired. A new attempt must see this.
        changed.append(True)
        with engine.begin() as writer:
            writer.execute(text("UPDATE worlds SET status='archived' WHERE id='social-uow-world'"))

    event.listen(engine, 'before_cursor_execute', revoke)
    try:
        with Session(engine) as db:
            owner = db.get(User, 'social-uow-owner')
            with pytest.raises(MessageNotFoundError):
                service.accept_world_message(db, owner, 'social-uow-world', 'chat-one',
                    WorldChatMessageCreate(content='must not be stored', idempotency_key='revocation-request-key'))
    finally:
        event.remove(engine, 'before_cursor_execute', revoke)
    assert changed
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MessageMessage)) == 0
        assert db.scalar(select(func.count()).select_from(ChatResponseRequest)) == 0


def test_image_admission_and_other_writers_keep_serializable(store, monkeypatch):
    engine, _, _ = store
    prepare(engine)
    service, observed = _service(monkeypatch), []
    def names(db, *args):
        observed.append(db.scalar(text('SHOW transaction_isolation')))
        raise MessageValidationError('synthetic_stop_before_image_or_provider')
    monkeypatch.setattr(service, '_request_names', names)
    with Session(engine) as db:
        owner = db.get(User, 'social-uow-owner')
        with pytest.raises(MessageValidationError):
            service.accept_world_message(db, owner, 'social-uow-world', 'chat-one',
                WorldChatMessageCreate(content='synthetic image', attachment_asset_id='synthetic-asset',
                    idempotency_key='image-request-key-001'))
    with Session(engine) as db:
        assert database_write(db, lambda: db.scalar(text('SHOW transaction_isolation'))) == 'serializable'
    assert observed == ['serializable']


def test_committed_retry_invalidates_waiting_text_admission_snapshot(store, monkeypatch):
    engine, _, _ = store
    prepare(engine)
    service = _service(monkeypatch)
    monkeypatch.setattr(service, '_validate_request_names', lambda *args: None)
    with Session(engine) as db:
        owner = db.get(User, 'social-uow-owner')
        first = service.accept_world_message(db, owner, 'social-uow-world', 'chat-one',
            WorldChatMessageCreate(content='original', idempotency_key='original-request-key'))
    with Session(engine) as db:
        prior = db.get(ChatResponseRequest, first.response_request.request_id)
        prior.state, prior.retryable, prior.terminal_reason = 'failed', True, 'provider_failure'
        prior.terminal_at = datetime.now(UTC)
        db.commit()
    retried = []

    def retry_before_lock(connection, cursor, statement, params, context, many):
        locks_thread = (statement.startswith('UPDATE message_threads SET updated_at=') or
                        statement.startswith('SELECT message_threads.') and 'FOR UPDATE' in statement)
        if retried or not locks_thread:
            return
        retried.append(True)
        with Session(engine) as other:
            owner = other.get(User, 'social-uow-owner')
            value = service.retry_world_response(other, owner, 'social-uow-world', 'chat-one',
                WorldChatRetryCreate(failed_request_id=first.response_request.request_id,
                                    idempotency_key='retry-prior-request-key'))
            assert value.outcome == 'accepted'

    event.listen(engine, 'before_cursor_execute', retry_before_lock)
    try:
        with Session(engine) as db:
            owner = db.get(User, 'social-uow-owner')
            with pytest.raises(MessageInFlightError):
                service.accept_world_message(db, owner, 'social-uow-world', 'chat-one',
                    WorldChatMessageCreate(content='must not overtake retry', idempotency_key='new-after-retry-key'))
    finally:
        event.remove(engine, 'before_cursor_execute', retry_before_lock)
    assert retried
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(MessageMessage)) == 1
        assert db.scalar(select(func.count()).select_from(ChatResponseRequest)) == 2
        assert db.scalar(select(func.count()).select_from(ChatResponseRequest).where(
            ChatResponseRequest.state == 'accepted')) == 1
