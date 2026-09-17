from dataclasses import replace
import json

import pytest

from app.domains.chat.models import ChatMessageThought
from app.domains.memory.exceptions import MemoryConflictError, MemoryValidationError
from app.domains.memory.service.episode_manifest import episode_input_manifest, restore_episode_input
from app.runtime.memory.episode_details import RuntimeEpisodeDetailReader
from memory.test_episode_chat_pipeline import setup, response_session


def test_restart_manifest_reloads_same_originals_and_thought_without_copying_them(response_session):
    db = response_session
    scope, memory, bundle, done, now = setup(db)
    payload = episode_input_manifest(bundle)
    encoded = json.dumps(payload, ensure_ascii=False)
    assert bundle.new_units[0].thought.text not in encoded
    assert all(member.text not in encoded for member in bundle.new_units[0].members if member.text)
    db.commit()
    db.expire_all()
    restored = restore_episode_input(json.loads(encoded), scope=scope, detail_reader=RuntimeEpisodeDetailReader(db))
    assert restored == bundle
    assert restored.new_units[0].thought.text == bundle.new_units[0].thought.text


def test_restart_manifest_rejects_changed_thought_or_scope(response_session):
    db = response_session
    scope, memory, bundle, done, now = setup(db)
    payload = episode_input_manifest(bundle)
    with pytest.raises(MemoryValidationError, match="manifest_invalid"):
        restore_episode_input(payload, scope=replace(scope, owner_id="another"), detail_reader=RuntimeEpisodeDetailReader(db))
    db.get(ChatMessageThought, done.committed_assistant_message_id).thought_text = "나중에 바뀐 생각"
    db.flush()
    with pytest.raises(MemoryConflictError, match="revision_changed"):
        restore_episode_input(payload, scope=scope, detail_reader=RuntimeEpisodeDetailReader(db))
