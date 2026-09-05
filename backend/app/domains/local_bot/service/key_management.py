"""Owner LocalBot connection and key issue/revocation workflows."""
from sqlalchemy.orm import Session
from app.core import security
from app.domains.local_bot import schemas
from app.domains.local_bot.constants import LOCAL_KEY_PREFIX
from app.domains.local_bot.contracts.key_management import LocalKeyOwner, LocalKeyCharacter, LocalKeyWorkflows
from app.domains.local_bot.repository import keys as key_repository
from app.domains.local_bot.service import key_records
from app.domains.characters.service.access import _get_owned_character, _ensure_local_mode


def _local_connection_read(db: Session, character: LocalKeyCharacter) -> schemas.AgentLocalConnectionRead:
    active_key = key_repository.get_active_local_key(db, character.id)
    key = active_key or key_repository.get_latest_local_key(db, character.id)
    return schemas.AgentLocalConnectionRead(character_id=character.id, execution_mode=character.execution_mode, has_active_key=active_key is not None, token_prefix=key.token_prefix if key else None, last_used_at=key.last_used_at if key else None, created_at=key.created_at if key else None, revoked_at=key.revoked_at if key else None)


def _local_key_token_prefix(token: str) -> str:
    return f'{token[:24]}...'


def get_local_connection(db: Session, user: LocalKeyOwner, character_id: str) -> schemas.AgentLocalConnectionRead:
    character = _get_owned_character(db, user, character_id)
    _ensure_local_mode(character)
    return _local_connection_read(db, character)


def issue_local_key(db: Session, user: LocalKeyOwner, character_id: str, *, workflows: LocalKeyWorkflows) -> schemas.AgentLocalKeyCreateRead:
    character = _get_owned_character(db, user, character_id)
    _ensure_local_mode(character)
    token = f'{LOCAL_KEY_PREFIX}{security.create_token()}'
    key = key_records.create_local_key(db, user=user, character=character, token=token, token_prefix=_local_key_token_prefix(token))
    workflows.log_activity(db, user_id=user.id, character_id=character.id, action_type='local_key_issued', target_post_id=None, reason='local_key_management', result=f'Issued local key prefix {key.token_prefix}.')
    return schemas.AgentLocalKeyCreateRead(connection=_local_connection_read(db, character), token=token)


def revoke_local_key(db: Session, user: LocalKeyOwner, character_id: str, *, workflows: LocalKeyWorkflows) -> None:
    character = _get_owned_character(db, user, character_id)
    _ensure_local_mode(character)
    key = key_records.revoke_active_local_key(db, character.id)
    if key is not None:
        workflows.log_activity(db, user_id=user.id, character_id=character.id, action_type='local_key_revoked', target_post_id=None, reason='local_key_management', result=f'Revoked local key prefix {key.token_prefix}.')
