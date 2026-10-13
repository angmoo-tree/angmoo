"""Prove the narrow shared-key HTTP retirement without relaxing its DI frame."""
import ast
import importlib.util
from pathlib import Path

import pytest


_path = Path(__file__).resolve().parents[3] / "scripts/ci/chat_forwarder_retirement.py"
_spec = importlib.util.spec_from_file_location("chat_settings_retirement_contract", _path)
proof = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(proof)

SOURCE = "backend/app/domains/chat/router/messages.py"
BEFORE = '''from fastapi import Depends, HTTPException
@router.put("/messages/settings", response_model=SettingsRead)
def update_message_settings(data: SettingsUpdate, db=Depends(get_db), user=Depends(get_current_user), settings_service=Depends(get_settings_service)) -> SettingsRead:
    return settings_service.update_user_settings(db, user, data)
@router.get("/messages/threads")
def list_threads(db=Depends(get_db), user=Depends(get_current_user)):
    return thread_service.list_threads(db, user)
'''
AFTER = BEFORE.replace(
    "return settings_service.update_user_settings(db, user, data)",
    'raise HTTPException(410, detail="world_character_settings_required")',
)


def signed_change(path, name, before, after):
    expected_before = ast.parse(BEFORE).body[1]
    expected_after = ast.parse(AFTER).body[1]
    return (path == SOURCE and name == "update_message_settings"
            and proof.dump(before) == proof.dump(expected_before)
            and proof.dump(after) == proof.dump(expected_after))


def test_exact_committed_retirement_preserves_the_http_frame():
    proof.validate_message_settings_retirement(SOURCE, BEFORE, AFTER, signed_change)


def test_unchanged_original_route_requires_no_retirement_record():
    proof.validate_message_settings_retirement(SOURCE, BEFORE, BEFORE, lambda *args: False)


def test_unsigned_retirement_fails_closed():
    with pytest.raises(ValueError, match="HTTP endpoint or dependency"):
        proof.validate_message_settings_retirement(SOURCE, BEFORE, AFTER, lambda *args: False)


@pytest.mark.parametrize("current", [
    AFTER.replace("HTTPException(410", "HTTPException(409"),
    AFTER.replace("world_character_settings_required", "another_contract"),
    AFTER.replace('raise HTTPException(410, detail="world_character_settings_required")', "return save_shared_key(data)"),
    AFTER.replace("Depends(get_current_user)", "Depends(get_unchecked_user)", 1),
    AFTER.replace("response_model=SettingsRead", "response_model=PrivateSettingsRead"),
    AFTER.replace("return thread_service.list_threads(db, user)", "return all_threads(db)"),
    AFTER.replace("from fastapi", "from untrusted_module"),
], ids=["wrong-status", "wrong-reason", "global-write", "auth-dependency",
        "response-model", "other-endpoint", "foreign-import"])
def test_arbitrary_approved_changes_cannot_retire_or_change_the_http_frame(current):
    with pytest.raises(ValueError, match="HTTP endpoint or dependency"):
        proof.validate_message_settings_retirement(SOURCE, BEFORE, current, lambda *args: True)
