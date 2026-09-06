from datetime import UTC, datetime
import pytest
from sqlalchemy.orm import Session
from app.domains.identity.repository.credentials import get_credential, get_default_credential
from app.domains.characters.models import Character
from app.domains.identity.models import LlmCredential
from app.domains.routines import exceptions
from app.domains.routines.service.run_identity import _validate_character_and_credential as validate
from app.domains.social.exceptions import CharacterNotFoundError
from app.runtime.resident.identity_references import SqlAlchemyRunIdentityReferences
from routine_posts.test_runtime import _seed
from social.test_resident_context_queries import _engine


def test_run_identity_reads_attached_pending_values_without_committing(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        credential = get_credential(db, 'credential-routine')
        reads = []
        def lookup(session, key):
            reads.append((session, key))
            return get_credential(session, key)
        references = SqlAlchemyRunIdentityReferences(db, credential_lookup=lookup, default_credential_lookup=get_default_credential)
        assert reads == []
        fixture.character.name = 'uncommitted identity read'
        credential.label = 'uncommitted credential read'
        character, found = validate(references, user_id=fixture.user.id, character_id=fixture.character.id, credential_id=credential.id)
        assert character is fixture.character
        assert found is credential
        assert reads == [(db, credential.id)]
        with Session(engine) as observer:
            assert observer.get(Character, fixture.character.id).name == 'Mira'
            assert observer.get(LlmCredential, credential.id).label == 'Routine test key'
        db.rollback()
        assert fixture.character.name == 'Mira'
        assert credential.label == 'Routine test key'
    engine.dispose()


def test_run_identity_preserves_error_precedence_and_stops_before_credential_read(tmp_path):
    engine = _engine(tmp_path)
    with Session(engine, expire_on_commit=False) as db:
        fixture = _seed(db)
        credential = get_credential(db, 'credential-routine')
        calls = []
        def lookup(session, key):
            calls.append((session, key))
            return get_credential(session, key)
        references = SqlAlchemyRunIdentityReferences(db, credential_lookup=lookup, default_credential_lookup=get_default_credential)
        values = dict(user_id=fixture.user.id, character_id=fixture.character.id, credential_id=credential.id)
        with pytest.raises(CharacterNotFoundError) as missing:
            validate(references, **(values | {'character_id': 'missing'}))
        assert missing.value.args == ('missing',)
        assert calls == []
        fixture.character.deleted_at = datetime.now(UTC)
        with pytest.raises(CharacterNotFoundError):
            validate(references, **(values | {'user_id': 'wrong'}))
        assert calls == []
        db.rollback()
        with pytest.raises(exceptions.CharacterOwnershipError):
            validate(references, **(values | {'user_id': 'wrong'}))
        assert calls == []
        with pytest.raises(exceptions.CredentialNotFoundError):
            validate(references, **(values | {'credential_id': 'missing'}))
        assert calls[-1] == (db, 'missing')
        with db.no_autoflush:
            credential.owner_id = 'wrong'
            credential.character_id = 'wrong'
            credential.enabled = False
            with pytest.raises(exceptions.CredentialOwnershipError) as owner:
                validate(references, **values)
            assert 'cannot use credential' in str(owner.value)
            credential.owner_id = fixture.user.id
            with pytest.raises(exceptions.CredentialOwnershipError) as assignment:
                validate(references, **values)
            assert 'is not assigned' in str(assignment.value)
            credential.character_id = None
            with pytest.raises(exceptions.CredentialDisabledError):
                validate(references, **values)
            credential.enabled = True
            assert validate(references, **values)[1] is credential
        db.rollback()
        assert credential.enabled is True
        assert credential.character_id == fixture.character.id
    engine.dispose()
