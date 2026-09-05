from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.routing import _iter_routes_with_context
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.domains.social import dependencies
from app.domains.social.router import manual_router
from app.runtime.social.composition import configure_social_runtime


def test_manual_http_factories_share_request_session_without_constructor_io():
    from app.main import create_app as hosted
    from app.public_main import create_app as local

    engine = create_engine("sqlite://")
    statements = []
    event.listen(
        engine, "before_cursor_execute", lambda *args: statements.append(args[2])
    )
    with Session(engine) as db:
        for factory in (hosted, local):
            app = factory()
            request = Request({"type": "http", "app": app})
            profile = dependencies.get_world_profile_service(request, db)
            refs = dependencies.get_manual_feed_references(request, db)
            executor = dependencies.get_source_write_executor(request, db)
            assert profile.repository.db is db
            assert profile.references.db is db
            assert refs.db is db
            assert executor._session is db
            assert statements == []
            names = [
                route.name
                for route, _ in _iter_routes_with_context(app.routes)
                if "manual-social" in getattr(route, "tags", [])
            ]
            assert names == [
                "read_world_character_social_activity",
                "read_manual_social_feed",
                "read_manual_social_post_thread",
                "write_owner_post",
                "write_owner_reply",
            ]
    engine.dispose()


def test_manual_http_origin_rejection_precedes_all_business_io():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    statements, opened = [], []
    event.listen(
        engine, "before_cursor_execute", lambda *args: statements.append(args[2])
    )
    app = FastAPI()
    configure_social_runtime(app)
    app.include_router(manual_router, prefix="/api/v1")

    def get_db():
        with Session(engine) as db:
            opened.append(db)
            yield db

    app.dependency_overrides[dependencies.get_db] = get_db
    app.dependency_overrides[dependencies.get_current_user] = lambda: SimpleNamespace(
        id="owner"
    )
    with TestClient(app, base_url="http://127.0.0.1:3000") as client:
        for method, path, payload in [
            ("GET", "/world-characters/wc/social-profile", None),
            ("GET", "/manual-social/feed", None),
            ("GET", "/manual-social/posts/post", None),
            ("POST", "/manual-social/posts", {"title": "Hello", "body": "Body"}),
            ("POST", "/manual-social/posts/post/replies", {"body": "Reply"}),
        ]:
            response = client.request(
                method,
                "/api/v1/worlds/world" + path,
                json=payload,
                headers={
                    "Origin": "https://external.invalid",
                    "Host": "external.invalid",
                    "Idempotency-Key": "origin-rejected",
                },
            )
            assert response.status_code == 403
            assert statements == []
        # The endpoint and its collaborator dependency use FastAPI's same cached
        # Session, rather than opening a second write/read transaction per request.
        assert len(opened) == 5
    engine.dispose()
