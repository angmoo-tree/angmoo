from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import models, schemas
from app.api.v1.routes import tree as tree_routes
from app.core.db import Base
from app.services import tree as tree_service


def _user(user_id: str) -> models.User:
    return models.User(
        id=user_id,
        email=f"{user_id}@example.test",
        google_sub=f"google-{user_id}",
        password_hash=f"hash-{user_id}",
        display_name=user_id,
        display_name_normalized=user_id,
        privacy_policy_version="test",
        terms_version="test",
    )


def _character(character_id: str, owner_id: str) -> models.Character:
    return models.Character(
        id=character_id,
        owner_id=owner_id,
        name=character_id,
        handle=character_id,
        status="inactive",
        persona_summary="",
    )


def _dependency_names(route) -> set[str]:
    names: set[str] = set()

    def walk(dependant) -> None:
        for dependency in dependant.dependencies:
            if dependency.call is not None:
                names.add(
                    getattr(dependency.call, "__name__", type(dependency.call).__name__)
                )
            walk(dependency)

    walk(route.dependant)
    return names


def test_tree_reads_are_public_and_writes_require_authentication() -> None:
    route_access = {
        (next(iter(route.methods)), route.path): _dependency_names(route)
        for route in tree_routes.router.routes
    }

    assert "get_current_user" not in route_access[("GET", "/tree/posts")]
    assert "get_current_user" not in route_access[("GET", "/tree/posts/{post_id}")]
    assert "get_current_user" in route_access[("POST", "/tree/posts")]
    assert "get_current_user" in route_access[("POST", "/tree/posts/{post_id}/comments")]


def test_tree_list_and_detail_are_readable_without_user_context() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user("owner")
        post = models.TreePost(
            id="tree-public",
            category="free",
            title="public title",
            body="public body",
            author_user_id=owner.id,
        )
        db.add_all([owner, post])
        db.commit()

        page = tree_service.list_posts(db, category="free")
        detail = tree_service.get_post(db, post.id)

        assert [item.id for item in page.items] == ["tree-public"]
        assert detail.id == "tree-public"
        assert detail.author.id == owner.id


def test_tree_notice_and_cross_owner_character_are_rejected() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user("owner")
        intruder = _user("intruder")
        character = _character("char-owner", owner.id)
        db.add_all([owner, intruder, character])
        db.commit()

        try:
            tree_service.create_post(
                db,
                intruder,
                schemas.TreePostCreate(
                    category="notice",
                    title="notice",
                    body="body",
                ),
            )
        except tree_service.TreeNoticeWriteForbiddenError:
            pass
        else:
            raise AssertionError("ordinary users must not create notices")

        try:
            tree_service.create_post(
                db,
                intruder,
                schemas.TreePostCreate(
                    category="free",
                    title="title",
                    body="body",
                    related_character_id=character.id,
                ),
            )
        except tree_service.TreeRelatedCharacterError:
            pass
        else:
            raise AssertionError("cross-owner character reference must look not found")
