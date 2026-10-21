"""Real bounded pages: scope, ties, deletion, attachment loading and no writes."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from chat.test_p8_l_d_world_chat_api import _fixture, _seed, FRONTEND_HEADERS
from model_fixture_support import models
from app.domains.chat.service.message_pages import committed_evidence_summary


@pytest.fixture
def room():
    client, engine, principal = _fixture()
    owner, outsider, responder = _seed(engine, principal)
    result = client.post('/api/v1/worlds/world-a/chat/threads', headers=FRONTEND_HEADERS,
                         json={'responding_world_character_id': responder})
    assert result.status_code == 200
    thread = result.json()['thread']['id']
    now = datetime.now(UTC)
    with Session(engine) as db:
        db.add_all(models.MessageMessage(thread_id=thread, role='user' if i % 2 == 0 else 'assistant',
                    content=f'synthetic {i}', created_at=now + timedelta(seconds=i//3), status='ok') for i in range(123))
        db.commit()
        ids = list(db.scalars(select(models.MessageMessage.id).order_by(models.MessageMessage.id)))
    yield client, engine, principal, owner, outsider, thread, ids
    client.close(); engine.dispose()


def test_latest_before_after_and_deleted_cursor_are_bounded_read_only(room):
    client, engine, _, _, _, thread, ids = room
    path=f'/api/v1/worlds/world-a/chat/threads/{thread}'
    statements=[]
    event.listen(engine, 'before_cursor_execute', lambda c, cur, statement, *args: statements.append(statement))
    initial=client.get(path).json()
    assert [m['id'] for m in initial['messages']] == ids[-50:]
    assert initial['message_page']['has_more']
    older=client.get(path+'/messages', params={'before':initial['message_page']['oldest_cursor']}).json()
    assert [m['id'] for m in older['items']] == ids[-100:-50]
    assert older['has_more']
    first=client.get(path+'/messages', params={'before':older['oldest_cursor']}).json()
    assert [m['id'] for m in first['items']] == ids[:23]
    assert not first['has_more']
    newer=client.get(path+'/messages', params={'after':first['newest_cursor']}).json()
    assert [m['id'] for m in newer['items']] == ids[23:73]
    assert newer['has_more']
    assert not any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements)
    with Session(engine) as db:
        db.delete(db.get(models.MessageMessage, ids[-50])); db.commit()
    deleted=client.get(path+'/messages', params={'before':initial['message_page']['oldest_cursor']}).json()
    assert [m['id'] for m in deleted['items']] == ids[-100:-50]


@pytest.mark.parametrize('query', [{'limit':0},{'limit':101},{'before':'bad!'}, {'before':'a','after':'b'}])
def test_invalid_pages_are_rejected(room, query):
    client, _, _, _, _, thread, _=room
    assert client.get(f'/api/v1/worlds/world-a/chat/threads/{thread}/messages', params=query).status_code==422


def test_cursor_cannot_authorize_other_owner_world_or_deleted_thread(room):
    client, engine, principal, owner, outsider, thread, _=room
    path=f'/api/v1/worlds/world-a/chat/threads/{thread}'
    cursor=client.get(path).json()['message_page']['oldest_cursor']
    principal['user']=outsider
    assert client.get(path+'/messages', params={'before':cursor}).status_code==403
    principal['user']=owner
    assert client.get(path.replace('world-a','world-b')+'/messages', params={'before':cursor}).status_code==404
    with Session(engine) as db:
        db.get(models.MessageThread,thread).deleted_at=datetime.now(UTC); db.commit()
    assert client.get(path+'/messages',params={'before':cursor}).status_code==404


def test_committed_summary_projection_includes_current_context_once():
    metadata={'evidence_capability':'available','public_evidence_count':2,'_social_context_inspector_v1':{'items':[{},{}]}}
    summary=committed_evidence_summary('request',12,metadata)
    assert summary.count==4 and summary.assistant_message_id==12
    assert committed_evidence_summary('request',12,{}) is None


def test_empty_room_keeps_a_contiguous_after_boundary():
    client, engine, principal = _fixture()
    _, _, responder = _seed(engine, principal)
    response = client.post('/api/v1/worlds/world-a/chat/threads', headers=FRONTEND_HEADERS,
        json={'responding_world_character_id': responder}).json()['thread']
    cursor = response['message_page']['newest_cursor']
    assert cursor and not response['messages']
    with Session(engine) as db:
        db.add_all(models.MessageMessage(thread_id=response['id'], role='user', content='synthetic',
            status='ok', created_at=datetime.now(UTC)) for _ in range(123))
        db.commit()
        ids = list(db.scalars(select(models.MessageMessage.id).order_by(models.MessageMessage.id)))
    first = client.get(f"/api/v1/worlds/world-a/chat/threads/{response['id']}/messages", params={'after': cursor}).json()
    assert [item['id'] for item in first['items']] == ids[:50]
    assert first['has_more']
    client.close(); engine.dispose()
