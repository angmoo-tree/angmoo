from dataclasses import replace

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.domains.world_characters.models import WorldCharacter
from app.domains.social.contracts.profile_activity import (
    WorldCharacterSocialProfileQuery,
    WorldCharacterSocialProfileValidationError,
)
from app.runtime.social.profile_composition import (
    world_character_social_profile_service,
)
from social.test_p8_l_e_world_profile_social_activity import _fixture, _seed


def test_world_profile_reads_pending_owner_values_and_rolls_back_without_commit():
    _client, engine, principal = _fixture()
    _seed(engine, principal)
    query = WorldCharacterSocialProfileQuery(
        world_id="world-a",
        world_character_id="wc-a-target",
        current_user_id="owner",
    )
    with Session(engine) as db:
        target = db.get(WorldCharacter, "wc-a-target")
        before = dict(target.local_profile)
        target.local_profile = {"avatar_url": "/media/pending-profile.webp"}
        service = world_character_social_profile_service(db)
        commits, statements = [], []
        event.listen(db, "before_commit", lambda *_: commits.append("commit"))

        def record(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            assert service.repository.db is db and service.references.db is db
            with pytest.raises(WorldCharacterSocialProfileValidationError):
                service.read(replace(query, limit=21))
            assert statements == []
            assert db.is_modified(target)

            page = service.read(query)
            assert [post.id for post in page.items] == ["a-root-new", "a-root-old"]
            assert all(
                post.author_avatar_url == "/media/pending-profile.webp"
                for post in page.items
            )
            assert all(
                post.author_profile_capability == "available" for post in page.items
            )
            assert commits == []
            db.rollback()
            assert db.get(WorldCharacter, "wc-a-target").local_profile == before
            page = service.read(query)
            assert all(
                post.author_avatar_url == before["avatar_url"] for post in page.items
            )
            assert commits == []
        finally:
            event.remove(engine, "before_cursor_execute", record)
