from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models as registered_models  # noqa: F401 - G5 will make registration explicit
from app.core.db import Base
from app.domains.identity.models import User
from app.domains.characters.models import Character
from app.domains.tree import models, repository, schemas, service
from app.domains.tree.dependencies import get_current_user, get_db
from app.runtime.tree import build_tree_references


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def owner():
    return User(
        id="tree-owner",
        email="tree-owner@example.test",
        password_hash="unused",
        display_name="Author needle",
        display_name_normalized="author needle",
        privacy_policy_version="test",
        terms_version="test",
    )


def test_search_keeps_author_comment_scope_and_tied_cursor_order(db):
    user = owner()
    instant = datetime(2026, 9, 6, tzinfo=timezone.utc)
    posts = [
        models.TreePost(
            id=key,
            category=category,
            title="Title",
            body="Body",
            author=user,
            created_at=instant,
            updated_at=instant,
            hidden_at=hidden,
        )
        for key, category, hidden in [
            ("tree-a", "free", None),
            ("tree-b", "free", None),
            ("tree-c", "free", None),
            ("tree-d", "notice", None),
            ("tree-e", "free", instant),
        ]
    ]
    posts[2].comments.append(models.TreeComment(author=user, content="comment-unique"))
    db.add_all(posts)
    db.commit()
    statements = []

    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", record)
    try:
        page = service.list_posts(
            db,
            category="free",
            query=" needle ",
            limit=2,
            references=build_tree_references(),
        )
    finally:
        event.remove(db.bind, "before_cursor_execute", record)
    assert [item.id for item in page.items] == ["tree-a", "tree-b"]
    assert page.next_cursor == "tree-b"
    # The author filter remains a correlated EXISTS in the original list SQL;
    # it does not run a preliminary user query or change the caller Session.
    assert "EXISTS" in statements[0] and "users.display_name" in statements[0]
    next_page = service.list_posts(
        db,
        category="free",
        query="needle",
        cursor=page.next_cursor,
        limit=2,
        references=build_tree_references(),
    )
    assert [item.id for item in next_page.items] == ["tree-c"]
    assert next_page.next_cursor is None
    comment_page = service.list_posts(
        db, category="free", query="comment-unique", references=build_tree_references()
    )
    assert [item.id for item in comment_page.items] == ["tree-c"]


def test_writes_keep_same_session_commit_refresh_and_deleted_profile(db, monkeypatch):
    user = owner()
    character = Character(
        id="char-tree",
        owner_id=user.id,
        name="Name",
        handle="tree-character",
        status="inactive",
        persona_summary="",
    )
    db.add_all([user, character])
    db.commit()
    db.refresh(user)
    db.refresh(character)
    seen = []
    original = build_tree_references()

    def read_character(session, character_id):
        seen.append((session, character_id))
        return original.get_character(session, character_id)

    references = replace(original, get_character=read_character)
    writes = []
    original_commit, original_refresh = db.commit, db.refresh

    def commit():
        writes.append("commit")
        original_commit()

    def refresh(instance, *args, **kwargs):
        writes.append(("refresh", type(instance)))
        return original_refresh(instance, *args, **kwargs)

    monkeypatch.setattr(db, "commit", commit)
    monkeypatch.setattr(db, "refresh", refresh)
    result = service.create_post(
        db,
        user,
        schemas.TreePostCreate(
            category="free",
            title=" Title ",
            body=" Body ",
            related_character_id=character.id,
        ),
        references=references,
    )
    assert seen == [(db, character.id)]
    assert writes == ["commit", ("refresh", models.TreePost)]
    assert (result.title, result.body) == ("Title", "Body")
    writes.clear()
    detail = service.create_comment(
        db, user, result.id, schemas.TreeCommentCreate(content=" Comment ")
    )
    assert writes == ["commit", ("refresh", models.TreeComment)]
    assert detail.comments[0].content == "Comment"
    character.deleted_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
    db.commit()
    deleted = service.get_post(db, result.id).related_character
    assert (deleted.name, deleted.handle, deleted.avatar_url) == (
        "삭제한 앵무",
        None,
        None,
    )
    assert Base.metadata.tables["tree_posts"] is models.TreePost.__table__
    assert Base.metadata.tables["tree_comments"] is models.TreeComment.__table__


def test_repository_commit_failure_does_not_refresh_or_swallow(db, monkeypatch):
    user = owner()
    db.add(user)
    db.commit()
    calls = []
    failure = RuntimeError("failed commit")

    def commit():
        calls.append("commit")
        raise failure

    monkeypatch.setattr(db, "commit", commit)
    monkeypatch.setattr(db, "refresh", lambda instance: calls.append("refresh"))
    with pytest.raises(RuntimeError) as caught:
        repository.create_tree_post(
            db,
            post_id="failed",
            user=user,
            category="free",
            title="title",
            body="body",
            related_character_id=None,
        )
    assert caught.value is failure
    assert calls == ["commit"]
    db.rollback()
    assert db.get(models.TreePost, "failed") is None


@pytest.mark.parametrize(
    "module_name", ["app.main", "app.public_main"], ids=["full", "public"]
)
def test_both_factories_wire_tree_http_with_original_dependencies(db, module_name):
    import importlib

    module = importlib.import_module(module_name)
    application = module.create_app(
        **(
            {"prepare_media_directories": False}
            if module_name == "app.public_main"
            else {}
        )
    )
    user = owner()
    db.add(user)
    db.commit()

    def same_session():
        yield db

    application.dependency_overrides[get_db] = same_session
    application.dependency_overrides[get_current_user] = lambda: user
    assert (
        application.state.tree_references().get_character
        is build_tree_references().get_character
    )
    # No lifespan work is needed to verify HTTP/session registration.
    client = TestClient(application)
    created = client.post(
        "/api/v1/tree/posts",
        json={
            "category": "free",
            "title": "Public",
            "body": "Body",
        },
    )
    assert created.status_code == 201
    application.dependency_overrides.pop(get_current_user)
    public_read = client.get("/api/v1/tree/posts", params={"category": "free"})
    assert public_read.status_code == 200
    assert [item["id"] for item in public_read.json()["items"]] == [
        created.json()["id"]
    ]
    assert (
        application.openapi()["paths"]["/api/v1/tree/posts"]["get"]["operationId"]
        == "list_tree_posts_api_v1_tree_posts_get"
    )
