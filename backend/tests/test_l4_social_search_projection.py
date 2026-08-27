from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.core.db import Base
from app.domains.social.public import SocialSearchState, current_social_search
from app.runtime.persistence.runtime_data_path import StaticRuntimeDataPath
from app.runtime.search import EmbeddedSocialSearchProjection, SqliteFts5SearchIndex


def _factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _post(*, post_id: str, world_id: str, text: str) -> models.Post:
    return models.Post(
        id=post_id,
        author_user_id=None,
        author_character_id="character-author",
        world_id=world_id,
        author_world_character_id="world-character-author",
        author_name="Author",
        title=text,
        body=f"{text} body",
        topic_signature=text,
        search_document=f"{text}\n{text} body\n{text}",
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
    )


def test_embedded_projection_rebuilds_and_tracks_committed_post_changes(
    tmp_path,
) -> None:
    engine, factory = _factory()
    with factory() as db:
        db.add(_post(post_id="post-a", world_id="world-a", text="alchemy"))
        db.add(_post(post_id="post-b", world_id="world-b", text="alchemy"))
        db.commit()

    projection = EmbeddedSocialSearchProjection(
        index=SqliteFts5SearchIndex(StaticRuntimeDataPath(tmp_path / "Angmoo")),
        session_factory=factory,
    )
    projection.start()
    try:
        binding = current_social_search()
        assert binding.state is SocialSearchState.READY
        assert binding.index is projection.index
        assert [
            hit.document_id
            for hit in projection.index.search(
                world_id="world-a", query="alchemy", limit=10
            )
        ] == ["post-a"]

        with factory() as db:
            post = db.get(models.Post, "post-a")
            assert post is not None
            post.title = "library"
            post.body = "library notes"
            post.topic_signature = "library"
            post.search_document = "library\nlibrary notes\nlibrary"
            db.commit()

        assert projection.index.search(
            world_id="world-a", query="alchemy", limit=10
        ) == ()
        assert [
            hit.document_id
            for hit in projection.index.search(
                world_id="world-a", query="library", limit=10
            )
        ] == ["post-a"]

        with factory() as db:
            post = db.get(models.Post, "post-a")
            assert post is not None
            post.report_hidden_at = datetime(2026, 8, 27, tzinfo=UTC)
            db.commit()
        assert projection.index.search(
            world_id="world-a", query="library", limit=10
        ) == ()
        assert current_social_search().state is SocialSearchState.READY
    finally:
        projection.stop()
        engine.dispose()


def test_production_p5_has_no_canonical_contains_fallback() -> None:
    source = (
        __import__("pathlib").Path(__file__).parents[1]
        / "app"
        / "services"
        / "world_feed_search.py"
    ).read_text(encoding="utf-8")
    assert "search_document.contains" not in source
    assert ".like(" not in source


def test_rebuild_failure_is_explicitly_unavailable_and_keeps_backend_alive(
    tmp_path,
    monkeypatch,
) -> None:
    engine, factory = _factory()
    projection = EmbeddedSocialSearchProjection(
        index=SqliteFts5SearchIndex(StaticRuntimeDataPath(tmp_path / "Angmoo")),
        session_factory=factory,
    )

    def fail_rebuild(_documents):
        raise RuntimeError("synthetic canonical read failure")

    monkeypatch.setattr(projection.index, "rebuild", fail_rebuild)
    projection.start()
    try:
        binding = current_social_search()
        assert binding.index is projection.index
        assert binding.state is SocialSearchState.UNAVAILABLE
    finally:
        projection.stop()
        engine.dispose()
