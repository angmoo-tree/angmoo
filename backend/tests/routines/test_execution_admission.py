from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.cruds.agent_runs import get_credential, get_default_credential
from app.domains.identity.models import LlmCredential
from app.domains.routines.exceptions import CharacterOwnershipError, CredentialNotFoundError
from app.domains.routines.service import execution_admission as admission
from app.domains.social.exceptions import CharacterNotFoundError, CharacterSuspendedError
from app.runtime.resident.identity_references import SqlAlchemyRunIdentityReferences
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_run_admission_preserves_owner_default_credential_scope_and_pending_visibility(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        credential = get_credential(db, 'credential-routine')
        calls = []
        def lookup(session, key):
            calls.append(('explicit', session, key))
            return get_credential(session, key)
        def default_lookup(session, owner_id, *, character_id):
            calls.append(('default', session, owner_id, character_id))
            return get_default_credential(session, owner_id, character_id=character_id)
        references = SqlAlchemyRunIdentityReferences(db, credential_lookup=lookup, default_credential_lookup=default_lookup)
        assert calls == []
        fixture.character.deleted_at = datetime.now(UTC)
        fixture.character.moderation_status = 'suspended'
        with pytest.raises(CharacterNotFoundError):
            admission._read_available_run_character(references, fixture.character.id)
        assert calls == []
        fixture.character.deleted_at = None
        with pytest.raises(CharacterSuspendedError):
            admission._read_available_run_character(references, fixture.character.id)
        assert calls == []
        db.rollback()
        assert admission._read_available_run_character(references, fixture.character.id) is fixture.character
        assert admission._resolve_run_owner(fixture.character, None) == fixture.user.id
        with pytest.raises(CharacterOwnershipError):
            admission._resolve_run_owner(fixture.character, 'other')
        assert calls == []
        kwargs = dict(user_id=fixture.user.id, character=fixture.character)
        assert admission._resolve_run_credential(references, credential_id=credential.id, **kwargs) is credential
        assert calls == [('explicit', db, credential.id)]
        db.add(LlmCredential(id='owner-shared', owner_id=fixture.user.id, character_id=None, provider='google', purpose='agent', model='test', auth_profile_id='shared', label='shared', enabled=True))
        credential.enabled = False
        with pytest.raises(CredentialNotFoundError) as missing:
            admission._resolve_run_credential(references, credential_id=None, **kwargs)
        assert str(missing.value) == f'No enabled credential is assigned to character {fixture.character.id}'
        assert calls[-1] == ('default', db, fixture.user.id, fixture.character.id)
        with Session(engine) as observer:
            assert get_default_credential(observer, fixture.user.id, character_id=fixture.character.id).id == credential.id
        db.rollback()
        assert admission._resolve_run_credential(references, credential_id=None, **kwargs) is credential
    engine.dispose()
