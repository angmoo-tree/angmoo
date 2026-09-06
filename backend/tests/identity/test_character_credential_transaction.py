"""Deleting a key preserves one transaction across slot, setting and credential owners."""
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.model_fixture_support import models as _registered_models
from app.domains.identity.models import User, LlmCredential
from app.domains.characters.models import Character
from app.domains.routines.models import AgentActivitySetting, AgentSlot
from app.domains.identity.service.credential_management import delete_credential
from app.runtime.characters.management import build_character_credential_workflows


@pytest.mark.parametrize("outcome", ["commit", "rollback"])
def test_credential_delete_keeps_shared_session_and_rolls_back_flushed_slot(tmp_path: Path, outcome: str) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'credential.sqlite3'}")
    for table in (User.__table__, Character.__table__, LlmCredential.__table__, AgentActivitySetting.__table__, AgentSlot.__table__):
        table.create(engine)
    try:
        with Session(engine) as db:
            user = User(id="owner", display_name="owner")
            character = Character(id="character", owner_id="owner", name="character", handle="credential-transaction", persona_summary="fixture", status="active", execution_mode="llm")
            credential = LlmCredential(id="credential", owner_id="owner", character_id="character", provider="google", purpose="agent", model="gemini-3.1-flash-lite", label="fixture", auth_profile_id="synthetic-profile", encrypted_api_key="synthetic-envelope", key_fingerprint="synthetic-fingerprint", enabled=True)
            setting = AgentActivitySetting(character_id="character", auto_enabled=True)
            slot = AgentSlot(agent_id="slot", status="assigned_idle", assigned_user_id="owner", assigned_character_id="character", assigned_credential_id="credential")
            db.add_all([user, character, credential, setting, slot])
            db.commit()
            observed = []

            def world_autonomy(session: Session, *, character_id: str, enabled: bool) -> bool:
                assert session is db
                assert character_id == "character"
                assert enabled is False
                assert setting.auto_enabled is False
                assert slot.assigned_character_id is None
                assert credential.enabled is True
                with Session(engine) as observer:
                    observed.append((observer.get(AgentSlot, "slot").assigned_character_id, observer.get(AgentActivitySetting, "character").auto_enabled, observer.get(LlmCredential, "credential").enabled))
                if outcome == "rollback":
                    raise RuntimeError("synthetic world write failure")
                return False

            workflows = replace(build_character_credential_workflows(), sync_enabled=lambda: False, set_world_autonomy=world_autonomy)
            if outcome == "rollback":
                with pytest.raises(RuntimeError, match="synthetic world write failure"):
                    delete_credential(db, user, "character", workflows=workflows)
            else:
                delete_credential(db, user, "character", workflows=workflows)
            assert observed == [("character", True, True)]
            assert db.get(Character, "character") is character
            assert db.get(LlmCredential, "credential") is credential
            with Session(engine) as observer:
                durable_character = observer.get(Character, "character")
                durable_credential = observer.get(LlmCredential, "credential")
                durable_slot = observer.get(AgentSlot, "slot")
                durable_setting = observer.get(AgentActivitySetting, "character")
                if outcome == "rollback":
                    assert durable_character.status == "active"
                    assert durable_credential.enabled is True
                    assert durable_credential.encrypted_api_key == "synthetic-envelope"
                    assert durable_credential.key_fingerprint == "synthetic-fingerprint"
                    assert durable_slot.assigned_character_id == "character"
                    assert durable_setting.auto_enabled is True
                else:
                    assert durable_character.status == "inactive"
                    assert durable_credential.enabled is False
                    assert durable_credential.encrypted_api_key is None
                    assert durable_credential.key_fingerprint is None
                    assert durable_credential.cooldown_until is None
                    assert durable_slot.assigned_character_id is None
                    assert durable_setting.auto_enabled is False
    finally:
        engine.dispose()
