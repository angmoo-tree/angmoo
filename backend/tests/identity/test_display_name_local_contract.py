"""Local names are content; format, uniqueness and update rules remain enforced."""
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.domains.identity import schemas
from app.domains.identity.models import User
from app.domains.identity.service import auth
from app.runtime.persistence.model_registration import register_models

pytestmark = pytest.mark.usefixtures("deny_external_network")


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    register_models().create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.mark.parametrize("name", ["admin", "Administrator's diary", "official", "angmoo", "관리자", "운영자", "삭제한 캐릭터", "Deleted character", "fuck"])
@pytest.mark.parametrize("operation", ["signup", "setup", "rename"])
def test_semantic_name_is_accepted_by_real_identity_writes(db, name, operation):
    if operation == "signup":
        result = auth.create_user(db, schemas.SignupCreate(
            email="name@example.test", password="synthetic-password", display_name=name,
            privacy_policy_agreed=True, terms_agreed=True,
        ))
        owner = db.get(User, result.user.id)
    else:
        owner = User(id="owner", display_name="Before", display_name_normalized="before",
                     profile_setup_completed=operation == "rename",
                     privacy_policy_version=auth.PRIVACY_POLICY_VERSION,
                     terms_version=auth.TERMS_VERSION,
                     display_name_updated_at=datetime.now(UTC) - timedelta(days=90))
        db.add(owner)
        db.commit()
        auth.update_user_display_name(db, owner, schemas.UserDisplayNameUpdate(
            display_name=name, privacy_policy_agreed=True, terms_agreed=True,
        ))
    assert owner.display_name == name
    assert owner.display_name_normalized == auth.normalize_display_name_key(name)
    assert owner.id != "admin"  # The display value does not choose identity.


def test_duplicate_and_empty_names_still_fail(db):
    db.add(User(id="existing", display_name="admin", display_name_normalized="admin"))
    db.commit()
    with pytest.raises(auth.DisplayNameAlreadyExistsError):
        auth.create_user(db, schemas.SignupCreate(email="duplicate@example.test", password="synthetic-password",
                        display_name="admin", privacy_policy_agreed=True, terms_agreed=True))
    with pytest.raises(auth.DisplayNameInvalidError):
        auth.create_user(db, schemas.SignupCreate(email="empty@example.test", password="synthetic-password",
                        display_name="   ", privacy_policy_agreed=True, terms_agreed=True))
    with pytest.raises(ValidationError):
        schemas.UserDisplayNameUpdate(display_name="x" * 81)
